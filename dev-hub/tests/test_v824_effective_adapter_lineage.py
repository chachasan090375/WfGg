#!/usr/bin/env python3
import importlib.util,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))
spec=importlib.util.spec_from_file_location('central_v824',BIN/'central-interface-controller.py')
central=importlib.util.module_from_spec(spec);spec.loader.exec_module(central)
def save(path,value): path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
with tempfile.TemporaryDirectory(prefix='v824-effective-lineage-') as td:
    td=Path(td);graph=td/'graph.json';result=td/'result.json';adapters=td/'effective-adapters.json'
    save(graph,{'schema':'chacha.dev/task-graph/v1','project':'project-x','tasks':[{'id':'task-x','verification':{'mode':'independent-agent'}}]})
    save(result,{'schema':'chacha.dev/task-result/v1','project':'project-x','task_id':'task-x'})
    save(adapters,{'schema':'chacha.dev/provider-adapters/v1','providers':{},'adapters':{}})
    record={'waves':[{'tasks':[{'task_id':'task-x','status':'SUCCEEDED','task_result':str(result)}]}]}
    captured=[]
    def trusted(repo,tool,project,operation,*extra):
        captured.append(extra)
        return 0,{'status':'OK','details':{'verification_status':'VERIFIED','trusted_learning_context':True,'learning_context_status':'TRUSTED_DISPATCH_CONTEXT'},'artifacts':[]},'', ''
    central.project_control=trusted
    out=central.verify_domain_run_results(SimpleNamespace(repo_root=ROOT,project_control=BIN/'project-control.py'),'project-x',record,graph,adapters)
    assert out['status']=='PASS',out
    args=list(captured[-1]);assert '--adapters' in args and args[args.index('--adapters')+1]==str(adapters),args
    def untrusted(repo,tool,project,operation,*extra):
        return 0,{'status':'OK','details':{'verification_status':'VERIFIED','trusted_learning_context':False,'learning_context_status':'UNTRUSTED_DISPATCH_CONTEXT:RuntimeError:TRUSTED_ADAPTER_BINDING_VERSION_INVALID:test'},'artifacts':[]},'', ''
    central.project_control=untrusted
    blocked=central.verify_domain_run_results(SimpleNamespace(repo_root=ROOT,project_control=BIN/'project-control.py'),'project-x',record,graph,adapters)
    assert blocked['status']=='BLOCKED',blocked
    assert 'TASK_VERIFICATION_FAILED:task-x' in blocked['blockers'],blocked
pc=(BIN/'project-control.py').read_text(encoding='utf-8')
for marker in [
    'verify.add_argument("--adapters", type=Path)',
    'effective_adapters_path = adapters_path.resolve() if adapters_path is not None else source_adapters_path',
    'adapters=adapters_value',
    '"--adapters", str(effective_adapters_path)',
]: assert marker in pc,marker
central_text=(BIN/'central-interface-controller.py').read_text(encoding='utf-8')
for marker in [
    '"--adapters",str(adapter_registry)',
    'details.get("learning_context_status")=="TRUSTED_DISPATCH_CONTEXT"',
    '"provider_adapter_registry":str(adapter_registry)',
]: assert marker in central_text,marker
print('CHACHA_DEV_V824_EFFECTIVE_ADAPTER_LINEAGE=PASS')
print('CHACHA_DEV_V824_TRUSTED_DISPATCH_CONTEXT_GATE=PASS')
print('CHACHA_DEV_V824_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
