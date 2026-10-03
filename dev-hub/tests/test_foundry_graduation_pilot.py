import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/foundry-graduation-pilot.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
G=Path('/opt/chacha-dev/runtime/worktrees/foundry-shadow-graduation-gate-v1')
def fixture():
 td=Path(tempfile.mkdtemp());c=td/'change.json';c.write_text(json.dumps({'schema':'chacha.dev/golden-path-artifact-evidence/v1','status':'PASS','details':{'workspace_commit':'a'*40,'workspace_tree':'b'*40,'rollback':{'strategy':'git-revert'}}}));ev=[]
 for i in range(2):p=td/f'e{i}.json';p.write_text(json.dumps({'schema':f'e{i}','status':'PASS'}));ev.append(p)
 return c,ev
def test_isolated_graduation_passes_without_execution():
 c,e=fixture();o=M.pilot(G/'dev-hub/bin/foundry-shadow-graduation-gate.py',G/'dev-hub/config/foundry-shadow-graduation-gate.v1.json',c,e);assert o['status']=='PASS' and o['promotion_performed'] is False
def test_insufficient_evidence_blocks():
 c,e=fixture();o=M.pilot(G/'dev-hub/bin/foundry-shadow-graduation-gate.py',G/'dev-hub/config/foundry-shadow-graduation-gate.v1.json',c,e[:1]);assert o['status']=='BLOCK'
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
