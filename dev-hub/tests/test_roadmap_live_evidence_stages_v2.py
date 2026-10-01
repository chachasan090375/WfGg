import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/roadmap_live_reassessment.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/roadmap-live-reassessment.v1.json').read_text())

def roots():
 td=Path(tempfile.mkdtemp());rel=td/'release';run=td/'runtime';rel.mkdir();run.mkdir();(rel/'.revision').write_text('a'*40);return rel,run

def touch(rel,path):p=rel/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('x')
def evidence(run,path,revision=None):
 p=run/path;p.parent.mkdir(parents=True,exist_ok=True);x={'status':'PASS'}
 if revision:x['platform_revision']=revision
 p.write_text(json.dumps(x))

def test_multiple_runtime_evidence_all_required():
 rel,run=roots();stage={'required_runtime_jsons':[{'path':'a.json','field':'status','equals':'PASS'},{'path':'b.json','field':'status','equals':'PASS'}]};evidence(run,'a.json');assert not M.stage_ok(stage,rel,run);evidence(run,'b.json');assert M.stage_ok(stage,rel,run)
def test_revision_bound_runtime_evidence():
 rel,run=roots();stage={'required_runtime_jsons':[{'path':'ha.json','field':'status','equals':'PASS','release_revision_field':'platform_revision'}]};evidence(run,'ha.json','b'*40);assert not M.stage_ok(stage,rel,run);evidence(run,'ha.json','a'*40);assert M.stage_ok(stage,rel,run)
def test_provider_shadow_stage_never_green():
 st=[x for x in POL['rules']['provider-independence']['stages'] if x['target_progress']==85][0];assert st['status']=='ORANGE' and 'NOT_ACTIVE' in st['state']
def test_ha_rehearsal_caps_below_100():
 st=[x for x in POL['rules']['resilience-ha']['stages'] if x['target_progress']==90][0];assert st['status']=='ORANGE'
def test_new_green_stages_need_runtime_proof():
 for gap in ('incident-remediation','foundries','learning','persistent-missions','self-evolution','constitution'):
  top=max(POL['rules'][gap]['stages'],key=lambda x:x['target_progress']);assert top['target_progress']==100 and top.get('required_runtime_jsons')

if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
