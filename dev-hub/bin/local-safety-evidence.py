"""Independent local sampler: fixtures, no service requests or production writes."""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
sys.dont_write_bytecode=True
import tempfile
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path

def selected_functions(path, names, scope):
    tree=ast.parse(path.read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if len(nodes)!=len(names):raise ValueError('OBSERVED_FUNCTION_MISSING')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return scope

def load_module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def source_binding(repo):
    names=['dev-hub/bin/stop_state.py','dev-hub/bin/autonomous-project-orchestrator.py',
           'dev-hub/bin/run-controller.py','dev-hub/bin/guardian-stop-latch-reconciler.py']
    hashes={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in names}
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    modified=bool(subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip())
    return {'source_revision':revision,'source_files':hashes,'working_tree_modified':modified}

def sample(repo):
    binary=repo/'dev-hub/bin'
    stop=load_module(binary/'stop_state.py','observed_stop')
    stops=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for name,content in [('missing',None),('corrupted','not-json'),('invalid_type','{"active":"false"}'),
                             ('active','{"active":true}'),('clear','{"active":false}')]:
            path=root/name
            if content is not None:path.write_text(content)
            stops.append({'name':name,**stop.inspect_stop(path),'blocked':stop.blocks_execution(path)})
        class Unreadable:
            def read_text(self, **kwargs):raise PermissionError('fixture')
        stops.append({'name':'unreadable',**stop.inspect_stop(Unreadable()),'blocked':stop.blocks_execution(Unreadable())})
    # Observe both consumers, not only the shared helper.
    old_path=list(sys.path);sys.path.insert(0,str(binary))
    try:
        for name in ['autonomous-project-orchestrator.py','run-controller.py']:
            scope={'Path':Path,'blocks_execution':stop.blocks_execution}
            selected_functions(binary/name,{'emergency_stop_active'},scope)
            if name.startswith('autonomous'):
                with tempfile.TemporaryDirectory() as td:
                    if not scope['emergency_stop_active'](Path(td)/'absent'):raise ValueError('ORCHESTRATOR_STOP_FAIL_OPEN')
            else:
                # Redirect the reader's default only inside the local imported helper.
                import stop_state
                saved=stop_state.blocks_execution
                stop_state.blocks_execution=lambda: stop.blocks_execution(Path('/fixture-missing-stop'))
                try:
                    if not scope['emergency_stop_active']():raise ValueError('RUN_CONTROLLER_STOP_FAIL_OPEN')
                finally:stop_state.blocks_execution=saved
    finally:sys.path[:]=old_path
    actions=[]
    for name in ['success','nonzero','timeout','spawn_error','pre_denied','post_denied']:
        phases=[];ids=[];outcome='NONE';calls=0
        def gate(script,args,phase,action_id,execution_result=None):
            nonlocal outcome
            phases.append(phase);ids.append(action_id)
            if execution_result is not None:outcome=execution_result['execution_status']
            if (name=='pre_denied' and phase=='PRE_ACTION') or (name=='post_denied' and phase=='POST_ACTION'):
                raise RuntimeError('fixture refusal')
            return {'verdict':'PASS','simulated':True}
        def child(*args,**kwargs):
            nonlocal calls
            calls+=1
            if name=='timeout':raise subprocess.TimeoutExpired('fixture',120)
            if name=='spawn_error':raise FileNotFoundError('fixture')
            return types.SimpleNamespace(returncode=7 if name=='nonzero' else 0,stdout='fixture',stderr='')
        scope={'Path':Path,'uuid':uuid,'sys':sys,'os':os,
               'subprocess':types.SimpleNamespace(run=child,PIPE=subprocess.PIPE,TimeoutExpired=subprocess.TimeoutExpired),
               'guardian_stage':gate,'_GUARDIAN_CONTEXT':{'run_id':'fixture'},'_STAGE_ROLE':{},
               '_observe_stage':lambda *args:None,'ulr':types.SimpleNamespace(observe_platform=lambda **kwargs:None)}
        selected_functions(binary/'autonomous-project-orchestrator.py',{'run'},scope)
        returned=False;error=None
        try:scope['run'](Path('fixture.py'),[]);returned=True
        except Exception as exc:error=type(exc).__name__
        actions.append({'name':name,'phases':phases,'action_ids':ids,'child_calls':calls,
                        'result_returned':returned,'post_outcome':outcome,'error':error})
    reconciler=load_module(binary/'guardian-stop-latch-reconciler.py','observed_reconciler')
    inventories=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);client=root/'client.py';policy=root/'policy.json'
        client.write_text('import json\nfrom pathlib import Path\nprint(Path(__file__).with_name("batch.json").read_text())\n')
        policy.write_text('{}')
        for name,items in [('below_limit',[{'alert_id':str(i),'severity':'INFO'} for i in range(99)]),
                           ('at_limit',[{'alert_id':str(i),'severity':'INFO'} for i in range(100)]),('malformed',[None])]:
            (root/'batch.json').write_text(json.dumps({'items':items}))
            accepted=False;error=None
            try:reconciler.call_client(client,policy,'alerts','OPEN');accepted=True
            except Exception as exc:error=str(exc)
            inventories.append({'name':name,'accepted':accepted,'error':error})
    return {'schema':'chacha.dev/local-safety-evidence/v1','scope':'LOCAL_FIXTURES_ONLY',
            'production_authorized':False,'observed_at':datetime.now(timezone.utc).isoformat(),
            **source_binding(repo),'stop_cases':stops,'action_cases':actions,'inventory_cases':inventories}

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();evidence=sample(args.repo_root.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(evidence,indent=2)+'\n')
    print('LOCAL_EVIDENCE='+str(args.output))

if __name__=='__main__':main()
