import importlib.util,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('g',ROOT/'bin/autonomy-terminal-evidence-bundle.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
policy=json.loads((ROOT/'config/autonomy-terminal-evidence-bundle.v1.json').read_text())

def learning(**kw):
    x={'schema':'chacha.dev/learning-closure-gate/v1','status':'PASS','learning_terminal_evidence_ready':True,'execution_authority':False};x.update(kw);return x
def selfe(**kw):
    x={'schema':'chacha.dev/self-evolution-closure-gate/v1','status':'PASS','self_evolution_terminal_evidence_ready':True,'execution_authority':False};x.update(kw);return x
def constitution(**kw):
    x={'schema':'chacha.dev/constitution-closure-gate/v1','status':'PASS','constitution_terminal_evidence_ready':True,'execution_authority':False};x.update(kw);return x

def test_all_pass_bundle_passes():assert m.bundle(policy,learning(),selfe(),constitution())['status']=='PASS'
def test_hold_propagates():assert m.bundle(policy,learning(status='HOLD'),selfe(),constitution())['status']=='HOLD'
def test_not_ready_holds():assert m.bundle(policy,learning(learning_terminal_evidence_ready=False),selfe(),constitution())['status']=='HOLD'
def test_bundle_has_no_authority():assert m.bundle(policy,learning(),selfe(),constitution())['production_mutation'] is False
if __name__=='__main__':
    for n,f in sorted(globals().items()):
        if n.startswith('test_'):f();print(n+'=PASS')
