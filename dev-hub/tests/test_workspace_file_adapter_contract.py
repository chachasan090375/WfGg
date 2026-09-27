from __future__ import annotations
import json,os,pathlib,subprocess,sys,tempfile

ROOT=pathlib.Path(__file__).resolve().parents[2]
ADAPTER=ROOT/'dev-hub/adapters/workspace-file-adapter.py'

def call(req:dict,project_root:pathlib.Path):
    env=os.environ.copy();env['CHACHA_DEV_PROJECT_ROOT']=str(project_root)
    p=subprocess.run([sys.executable,str(ADAPTER)],input=json.dumps(req),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,check=False)
    assert p.stdout.strip(),p.stderr
    return p,json.loads(p.stdout)

def base(permission='read'):
    return {
      'schema':'chacha.dev/dispatch-envelope/v1','project':'fixture-project','transition':'READY->READY','run_id':'fixture-run','wave':1,
      'task':{'id':'workspace-file:fixture','kind':'domain-capability','description':'fixture','owner_role':'workspace-artifact-engineer','permission':permission,'capabilities':['workspace-file-write'],'outputs':[{'type':'domain-capability-result','id':'fixture'}],'verification':{'mode':'independent-agent','self_certification_allowed':False,'required_evidence':['source','timestamp','digest']}},
      'bindings':[{'capability':'workspace-file-write','provider':'workspace-file-runtime','adapter':'workspace-file-adapter','fallback_used':False,'health_state':'HEALTHY'}],
      'policy_context':{'resource_class':'light','human_approval_required':False,'timeout_seconds':20},
      'workspace':None,'metadata':{}
    }

with tempfile.TemporaryDirectory(prefix='workspace-file-adapter-') as td:
    root=pathlib.Path(td)
    status=base('read');status['metadata']={'workspace_file':{'action':'status'}}
    p,x=call(status,root);assert p.returncode==0,(p.returncode,x);assert x['status']=='OK' and x['summary']=='WORKSPACE_FILE_RUNTIME_READY'
    assert list(root.rglob('*'))==[],list(root.rglob('*'))

    workspace=root/'fixture-project'/'branches'/'workspace-artifact'
    write=base('workspace-write');write['workspace']=str(workspace);write['metadata']={'workspace_file':{'action':'write-text','path':'status.txt','content':'BUILD_PATH_OK'}}
    p,x=call(write,root);assert p.returncode==0,(p.returncode,x);assert x['status']=='OK' and x['summary']=='WORKSPACE_FILE_WRITTEN'
    target=workspace/'status.txt';assert target.read_text()=='BUILD_PATH_OK';assert x['evidence'][0]['source']==str(target);assert x['verification']['status']=='UNVERIFIED'

    traversal=json.loads(json.dumps(write));traversal['metadata']['workspace_file']['path']='../escape.txt'
    p,x=call(traversal,root);assert p.returncode==2 and x['status']=='BLOCKED' and x['summary']=='WORKSPACE_FILE_PATH_UNSAFE';assert not (root/'fixture-project'/'branches'/'escape.txt').exists()

    mismatch=json.loads(json.dumps(write));mismatch['workspace']=str(root/'other-project'/'branches'/'x')
    p,x=call(mismatch,root);assert p.returncode==2 and x['summary']=='WORKSPACE_PROJECT_MISMATCH'

print('CHACHA_DEV_WORKSPACE_FILE_ADAPTER_STATUS=PASS')
print('CHACHA_DEV_WORKSPACE_FILE_ADAPTER_WRITE=PASS')
print('CHACHA_DEV_WORKSPACE_FILE_ADAPTER_CONFINEMENT=PASS')
print('CHACHA_DEV_WORKSPACE_FILE_ADAPTER_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
