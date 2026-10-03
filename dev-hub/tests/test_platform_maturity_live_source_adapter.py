import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/platform-maturity-live-source-adapter.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/platform-maturity-live-source-adapter.v1.json').read_text())
def files(score=95,ha=90,const='STABLE'):
 td=Path(tempfile.mkdtemp());r=td/'r.json';c=td/'c.json';h=td/'h.json';r.write_text(json.dumps({'schema':'chacha.dev/autonomy-gap-roadmap/v1','reassessment_source':'LIVE_POLICY_EVIDENCE','score_percent':score,'gaps':[{'id':'resilience-ha','progress':ha}]}));c.write_text(json.dumps({'status':const}));h.write_text(json.dumps({'status':'PASS'}));return r,c,h
def test_builds_weighted_scorecard():
 r,c,h=files();o=M.build(POL,r,c,h);assert o['status']=='PASS' and len(o['dimensions'])==3 and sum(x['weight'] for x in o['dimensions'])==100
def test_unstable_constitution_blocks():
 r,c,h=files(const='REVIEW_REQUIRED')
 try:M.build(POL,r,c,h);assert False
 except ValueError:pass
def test_non_live_roadmap_blocks():
 r,c,h=files();x=json.loads(r.read_text());x['reassessment_source']='STATIC';r.write_text(json.dumps(x))
 try:M.build(POL,r,c,h);assert False
 except ValueError:pass
def test_adapter_has_no_execution_authority():
 r,c,h=files();assert M.build(POL,r,c,h)['adapter_execution_authority'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
