import importlib.util,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('g',ROOT/'bin/self-evolution-closure-gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
policy=json.loads((ROOT/'config/self-evolution-closure-gate.v1.json').read_text())

def train(**kw):
    x={'schema':'chacha.dev/roadmap-train-planning-pilot/v1','status':'PASS','freeze_performed':False,'composition_performed':False,'promotion_performed':False};x.update(kw);return x
def foundry(**kw):
    x={'schema':'chacha.dev/foundry-graduation-pilot/v1','status':'PASS','pilot_execution_performed':False,'promotion_performed':False,'production_mutation':False};x.update(kw);return x
def evolution(**kw):
    x={'schema':'chacha.dev/universal-evolution-governance-policy/v1','principles':{'active_self_mutation':False,'self_promotion':False,'automatic_external_spend_eur':0}};x.update(kw);return x

def test_full_chain_passes():assert m.gate(policy,train(),foundry(),evolution())['status']=='PASS'
def test_train_mutation_holds():assert m.gate(policy,train(composition_performed=True),foundry(),evolution())['status']=='HOLD'
def test_foundry_mutation_holds():assert m.gate(policy,train(),foundry(production_mutation=True),evolution())['status']=='HOLD'
def test_self_promotion_holds():
    e=evolution();e['principles']['self_promotion']=True;assert m.gate(policy,train(),foundry(),e)['status']=='HOLD'
if __name__=='__main__':
    for n,f in sorted(globals().items()):
        if n.startswith('test_'):f();print(n+'=PASS')
