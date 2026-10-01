import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/foundry-shadow-graduation-gate.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/foundry-shadow-graduation-gate.v1.json').read_text())
CHANGE={'schema':'chacha.dev/golden-path-artifact-evidence/v1','status':'PASS','details':{'workspace_commit':'a'*40,'workspace_tree':'b'*40,'rollback':{'strategy':'git-revert'},'promotion_authorized':False}}
def ev():
 td=Path(tempfile.mkdtemp());out=[]
 for i in range(2):
  p=td/f'e{i}.json';p.write_text(json.dumps({'schema':f'e{i}','status':'PASS'}));out.append((p,json.loads(p.read_text())))
 return out
def test_two_independent_passes_ready(): assert M.gate(POL,CHANGE,ev())['status']=='PILOT_READY'
def test_one_evidence_holds(): assert M.gate(POL,CHANGE,ev()[:1])['status']=='HOLD'
def test_bad_sha_holds():
 x=json.loads(json.dumps(CHANGE));x['details']['workspace_commit']='bad';assert M.gate(POL,x,ev())['status']=='HOLD'
def test_gate_never_authorizes_execution():
 o=M.gate(POL,CHANGE,ev());assert o['pilot_execution_authorized'] is False and o['promotion_authorized'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
