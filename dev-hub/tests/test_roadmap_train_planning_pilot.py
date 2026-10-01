import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/roadmap-train-planning-pilot.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
P=Path('/opt/chacha-dev/runtime/worktrees/roadmap-release-train-planner-v1');BASE='a'*40
def fixture():
 td=Path(tempfile.mkdtemp());road=td/'road.json';cand=td/'c';cand.mkdir();road.write_text(json.dumps({'schema':'chacha.dev/autonomy-gap-roadmap/v1','gaps':[{'id':'g1','status':'RED','progress':20}]}));(cand/'x.json').write_text(json.dumps({'schema':'chacha.dev/roadmap-train-candidate/v1','chantier_id':'c1','gap_id':'g1','base_revision':BASE,'candidate_revision':'b'*40,'changed_files':['a.txt'],'evidence_status':'PASS'}));return road,cand
def test_real_planner_selects_candidate_without_promotion():
 r,c=fixture();o=M.pilot(P/'dev-hub/bin/roadmap-release-train-planner.py',P/'dev-hub/config/roadmap-release-train-planner.v1.json',r,c,BASE);assert o['status']=='PASS' and o['selected_count']==1 and o['promotion_performed'] is False
def test_pilot_does_not_freeze_or_compose():
 r,c=fixture();o=M.pilot(P/'dev-hub/bin/roadmap-release-train-planner.py',P/'dev-hub/config/roadmap-release-train-planner.v1.json',r,c,BASE);assert o['freeze_performed'] is False and o['composition_performed'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
