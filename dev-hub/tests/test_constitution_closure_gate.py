import importlib.util,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('g',ROOT/'bin/constitution-closure-gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
policy=json.loads((ROOT/'config/constitution-closure-gate.v1.json').read_text());D='sha256:'+'a'*64

def verification(**kw):
    x={'schema':'chacha.dev/autonomy-constitution-verification/v1','status':'PASS','blocked_count':0,'passed_count':15,'clause_count':15,'constitution_digest':D};x.update(kw);return x
def watch(**kw):
    x={'schema':'chacha.dev/autonomy-constitution-drift-watch/v1','status':'STABLE','current_digest':D,'constitution_mutation_authorized':False,'execution_authority':False};x.update(kw);return x

def test_full_passes():assert m.gate(policy,verification(),watch())['status']=='PASS'
def test_blocked_clause_holds():assert m.gate(policy,verification(blocked_count=1,passed_count=14),watch())['status']=='HOLD'
def test_digest_change_holds():assert m.gate(policy,verification(),watch(current_digest='sha256:'+'b'*64))['status']=='HOLD'
def test_review_required_holds():assert m.gate(policy,verification(),watch(status='REVIEW_REQUIRED'))['status']=='HOLD'
if __name__=='__main__':
    for n,f in sorted(globals().items()):
        if n.startswith('test_'):f();print(n+'=PASS')
