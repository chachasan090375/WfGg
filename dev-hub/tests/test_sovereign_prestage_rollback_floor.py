#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,tempfile,os
BIN=Path(__file__).resolve().parents[1]/'bin/intendant-platform-consolidator.py'
s=importlib.util.spec_from_file_location('ipc',BIN);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x)+'\n')
def release(root,name,rev,sovereign=False,rollback=''):
 p=root/name;p.mkdir(parents=True);(p/'.revision').write_text(rev+'\n');save(p/'.release-preparation.json',{'version':'1.0','revision':rev,'rollback_revision':rollback,'promotion_acceptance_status':'PASS','promotion_final_verification':'PASS'})
 if sovereign:
  for f in ['dev-hub/bin/sovereign_state_authority.py','dev-hub/bin/d1-worker-local-runtime.mjs','dev-hub/config/sovereign-state-authority.local.v1.json','dev-hub/systemd/chacha-dev-sovereign-guardian.service','dev-hub/systemd/chacha-dev-sovereign-sentinel.service','dev-hub/systemd/chacha-dev-sovereign-assurance-exchange.service','dev-hub/systemd/chacha-dev-sovereign-learning-relay.service']:
   z=p/f;z.parent.mkdir(parents=True,exist_ok=True);z.write_text('x\n')
 return p
with tempfile.TemporaryDirectory() as td:
 t=Path(td);platform=t/'platform';rels=platform/'releases';rels.mkdir(parents=True);runtime=t/'runtime';
 r1='1'*40;r2='2'*40;r3='3'*40;cand='4'*40
 p1=release(rels,'20260101-'+r1,r1);p2=release(rels,'20260201-'+r2,r2);p3=release(rels,'20260301-'+r3,r3,True,r2)
 # Make acquisition order deterministic.
 os.utime(p1,(1000,1000));os.utime(p2,(2000,2000));os.utime(p3,(3000,3000))
 (platform/'current').symlink_to(p3,target_is_directory=True)
 save(runtime/'sovereign-state/authority.json',{'schema':'chacha.dev/sovereign-state-authority/v1','mode':'LOCAL_SQLITE','generation':1,'services':{}})
 for i,r in enumerate((r1,r2),1):save(runtime/'release-gates'/f'g{i}'/'install-pass.json',{'revision':r,'status':'PASS','direct_operator_health':'PASS','guardian_realtime':'PASS'})
 policy={'physical_release_retention':{'rollback_slots':2,'max_physical_releases_after_consolidation':3,'runtime_evidence_root':str(runtime),'protect_declared_active_release_rollback':True,'rollback_selection_strategy':'MOST_RECENT_STRONGLY_VERIFIED_DISTINCT_REVISIONS'}}
 plan=m.build_plan(platform,policy,t/'evidence',cand,'sha256:'+'a'*64)
 rows={x['revision']:x for x in plan['rows']}
 assert plan['sovereign_authority_mode']=='LOCAL_SQLITE',plan
 assert plan['sovereign_local_primary_rollback_floor_enforced'] is True,plan
 assert plan['declared_rollback_revision']=='',plan
 assert plan['declared_rollback_ineligible_revision']==r2,plan
 assert plan['future_candidate_rollback_revision']==r3,plan
 assert plan['selected_rollback_revisions']==[],plan
 assert plan['historical_archive_revisions']==[r2],plan
 assert plan['missing_verified_rollback_count']==0,plan
 assert rows[r3]['action']=='KEEP' and rows[r3]['reason']=='ACTIVE_RELEASE',rows
 assert rows[r2]['action']=='KEEP' and rows[r2]['reason']=='HISTORICAL_ARCHIVE_NOT_ROLLBACK_ELIGIBLE',rows
 assert rows[r1]['action']=='RETIRE',rows
 assert plan['keep_count']==2 and plan['retire_count']==1,plan
print('CHACHA_DEV_SOVEREIGN_PRESTAGE_ROLLBACK_FLOOR=PASS')
print('PRE_SOVEREIGN_AUTOMATIC_ROLLBACK=FORBIDDEN')
print('ACTIVE_SOVEREIGN_RELEASE_IS_FUTURE_ROLLBACK=YES')
