import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/roadmap-release-train-planner.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/roadmap-release-train-planner.v1.json').read_text())
BASE='a'*40
ROAD={'schema':'chacha.dev/autonomy-gap-roadmap/v1','gaps':[{'id':'red','status':'RED','progress':20},{'id':'orange','status':'ORANGE','progress':50},{'id':'green','status':'GREEN','progress':100}]}
def c(cid,gap,files,base=BASE,status='PASS'):
    return {'schema':'chacha.dev/roadmap-train-candidate/v1','chantier_id':cid,'gap_id':gap,'base_revision':base,'candidate_revision':('b' if cid=='c1' else 'c')*40,'changed_files':files,'evidence_status':status}

def test_red_before_orange():
    o=M.plan(POL,ROAD,[c('c2','orange',['b']),c('c1','red',['a'])],BASE);assert [x['chantier_id'] for x in o['selected']]==['c1','c2']
def test_overlap_is_skipped():
    o=M.plan(POL,ROAD,[c('c1','red',['same']),c('c2','orange',['same'])],BASE);assert len(o['selected'])==1 and o['skipped'][0]['reason']=='FILE_OVERLAP'
def test_wrong_base_is_skipped():
    o=M.plan(POL,ROAD,[c('c1','red',['a'],'d'*40)],BASE);assert o['status']=='HOLD' and o['skipped'][0]['reason']=='BASELINE_MISMATCH'
def test_green_gap_not_selected():
    o=M.plan(POL,ROAD,[c('c1','green',['a'])],BASE);assert o['status']=='HOLD'
def test_planner_never_authorizes_promotion():
    o=M.plan(POL,ROAD,[c('c1','red',['a'])],BASE);assert o['promotion_authorized'] is False and o['freeze_authorized'] is False

if __name__=='__main__':
    for n,v in sorted(globals().items()):
        if n.startswith('test_'):v();print(n+'=PASS')
