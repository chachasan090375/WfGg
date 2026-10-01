import importlib.util,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('g',ROOT/'bin/learning-closure-gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
policy=json.loads((ROOT/'config/learning-closure-gate.v1.json').read_text())

def coverage(**kw):
    x={'schema':'chacha.dev/learning-coverage-report/v1','status':'PASS','coverage_percent':100.0,'gap_count':0,'missing_context_count':0};x.update(kw);return x
def route(**kw):
    x={'schema':'chacha.dev/cognitive-route-learning-summary/v1','status':'PASS','router_mutation_authorized':False,'registry_mutation_authorized':False};x.update(kw);return x
def confidence(**kw):
    x={'schema':'chacha.dev/model-capability-confidence/v1','status':'PASS','execution_authority':False,'entries':[{'state':'VERIFIED'},{'state':'VERIFIED'},{'state':'VERIFIED'}]};x.update(kw);return x

def test_full_evidence_passes():assert m.gate(policy,coverage(),route(),confidence())['status']=='PASS'
def test_gap_holds():assert m.gate(policy,coverage(gap_count=1,coverage_percent=90),route(),confidence())['status']=='HOLD'
def test_advisory_not_terminal():assert m.gate(policy,coverage(status='PASS_WITH_ADVISORY',missing_context_count=1),route(),confidence())['status']=='HOLD'
def test_mutation_authority_holds():assert m.gate(policy,coverage(),route(router_mutation_authorized=True),confidence())['status']=='HOLD'
def test_confidence_needs_three_verified():assert m.gate(policy,coverage(),route(),confidence(entries=[{'state':'VERIFIED'}]))['status']=='HOLD'
if __name__=='__main__':
    for n,f in sorted(globals().items()):
        if n.startswith('test_'):f();print(n+'=PASS')
