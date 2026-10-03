import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin/platform-maturity-evidence-reconciler.py'
spec=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/platform-maturity-evidence-reconciler.v1.json').read_text())

def mk(score=90):
    td=Path(tempfile.mkdtemp());dims=[]
    for i,w in enumerate((40,30,30)):
        p=td/f'e{i}.json';p.write_text(json.dumps({'ok':True,'i':i}))
        dims.append({'id':f'd{i}','score':score-i*5,'weight':w,'evidence_path':str(p),'evidence_digest':M.digest(p)})
    return {'schema':M.SCORECARD_SCHEMA,'status':'PASS','dimensions':dims}

def test_valid_scorecard_passes():
    o=M.reconcile(POL,mk());assert o['status']=='PASS';assert o['target_percent']>80;assert o['apply_authorized'] is False

def test_missing_evidence_blocks():
    x=mk();x['dimensions'][0]['evidence_path']='/missing';assert M.reconcile(POL,x)['status']=='BLOCK'

def test_weights_must_equal_100():
    x=mk();x['dimensions'][0]['weight']=39;assert 'WEIGHT_SUM_NOT_100' in M.reconcile(POL,x)['blockers']

def test_score_can_decrease():
    hi=M.reconcile(POL,mk(95))['target_percent'];lo=M.reconcile(POL,mk(60))['target_percent'];assert lo<hi

if __name__=='__main__':
    for n,v in sorted(globals().items()):
        if n.startswith('test_'):
            v();print(n+'=PASS')
