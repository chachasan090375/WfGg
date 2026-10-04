#!/usr/bin/env python3
import importlib.util,json,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin';sys.path.insert(0,str(BIN))
spec=importlib.util.spec_from_file_location('gpp_sovereign',BIN/'governed-platform-promotion.py');gpp=importlib.util.module_from_spec(spec);spec.loader.exec_module(gpp)
gpp.exact_release_verification=lambda release_root,meta:{'schema':'chacha.dev/exact-git-release-verification/v1','status':'PASS','checked_blobs':0,'test_stub':True,'automatic_external_spend_eur':0}

import promotion_transaction as ptx

def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x)+'\n')
# Remote/default authority never restarts local services.
with tempfile.TemporaryDirectory() as td:
 r=Path(td);x=gpp.sovereign_runtime_refresh(r);assert x['status']=='PASS' and x['refreshed'] is False
print('CHACHA_DEV_PROMOTION_SOVEREIGN_REMOTE_NOOP=PASS')
# LOCAL_SQLITE refresh requires exactly four loopback services and restarts all four.
with tempfile.TemporaryDirectory() as td:
 r=Path(td);save(r/'sovereign-state/authority.json',{'schema':'chacha.dev/sovereign-state-authority/v1','mode':'LOCAL_SQLITE','services':{'guardian':'http://127.0.0.1:8871','sentinel':'http://127.0.0.1:8872','assurance-exchange':'http://127.0.0.1:8873','learning-relay':'http://127.0.0.1:8874'}})
 calls=[]
 class P:
  returncode=0;stdout='';stderr=''
 class R:
  status=200
  def __enter__(self):return self
  def __exit__(self,*a):return False
  def read(self):return b'{"status":"ok","state_backend":"SQLITE_LOCAL"}'
 oldrun=gpp.subprocess.run;oldurl=gpp.urllib.request.urlopen
 gpp.subprocess.run=lambda argv,**kw:(calls.append(argv) or P())
 gpp.urllib.request.urlopen=lambda *a,**kw:R()
 try:x=gpp.sovereign_runtime_refresh(r)
 finally:gpp.subprocess.run=oldrun;gpp.urllib.request.urlopen=oldurl
 assert x['status']=='PASS' and x['refreshed'] is True and len(calls)==4,x
 assert [c[-1] for c in calls]==list(gpp.SOVEREIGN_UNITS.values()),calls
print('CHACHA_DEV_PROMOTION_SOVEREIGN_LOCAL_REFRESH=PASS')
# If refresh fails after a current switch, ACTIVATE restores the rollback symlink before failing.
with tempfile.TemporaryDirectory() as td:
 t=Path(td);runtime=t/'runtime';runtime.mkdir();rel=t/'release';old=t/'old';rel.mkdir();old.mkdir();cur=t/'current';cur.symlink_to(old,target_is_directory=True)
 (rel/'dev-hub/config').mkdir(parents=True);save(t/'stop.json',{'active':False});save(rel/'dev-hub/config/emergency-stop.v1.json',{'schema':'chacha.dev/emergency-stop/v1','state_file':str(t/'stop.json')})
 save(rel/'.release-preparation.json',{'candidate_revision':'a'*40,'candidate_tree':'b'*40,'human_production_approval_present':True,'platform_qualification':'PASS','guardian_pre_action':'PASS','sentinel_exact_revision':'PASS','rollback_path':str(old)})
 acq=ptx.acquire(runtime,'promotion-sovereign-fail','owner','a'*40,300);token=acq['lease_token'];calls=[0]
 oldrefresh=gpp.sovereign_runtime_refresh
 def flaky(_):
  calls[0]+=1
  if calls[0]==1:raise ValueError('SIMULATED_LOCAL_REFRESH_FAILURE')
  return {'status':'PASS','mode':'LOCAL_SQLITE','refreshed':True}
 gpp.sovereign_runtime_refresh=flaky
 try:
  try:gpp.activate(rel,cur,runtime,t/'activate.json','promotion-sovereign-fail',token);raise AssertionError('activation should fail')
  except ValueError as e:assert 'SOVEREIGN_RUNTIME_REFRESH_FAILED_ROLLBACK_COMPLETE' in str(e),e
 finally:gpp.sovereign_runtime_refresh=oldrefresh
 assert cur.resolve()==old.resolve() and calls[0]==2,(cur.resolve(),calls)
print('CHACHA_DEV_PROMOTION_SOVEREIGN_REFRESH_FAILURE_ROLLBACK=PASS')
