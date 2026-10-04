#!/usr/bin/env python3
import importlib.util,json,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))
def loadmod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ic=loadmod('ic',BIN/'intendant-platform-consolidator.py')
gpp=loadmod('gpp',BIN/'governed-platform-promotion.py')
gpp.exact_release_verification=lambda release_root,meta:{'schema':'chacha.dev/exact-git-release-verification/v1','status':'PASS','test_stub':True,'automatic_external_spend_eur':0}

def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x)+'\n')
def release(root,name,rev,version='1.0.0',rollback_revision=''):
 p=root/name;p.mkdir(parents=True);(p/'.revision').write_text(rev+'\n')
 save(p/'.release-preparation.json',{'version':version,'rollback_revision':rollback_revision})
 (p/'dev-hub/config').mkdir(parents=True);return p

def expect(fn,needle):
 try:fn();raise AssertionError('expected '+needle)
 except Exception as e:assert needle in str(e),(needle,e)

with tempfile.TemporaryDirectory() as td:
 t=Path(td);platform=t/'platform';rels=platform/'releases';rels.mkdir(parents=True);runtime=t/'runtime';runtime.mkdir()
 r1='1'*40;r2='2'*40;r3='3'*40;cand='4'*40
 p1=release(rels,'20260101-'+r1,r1);p2=release(rels,'20260201-'+r2,r2);p3=release(rels,'20260301-'+r3,r3,rollback_revision=r2)
 (platform/'current').symlink_to(p3,target_is_directory=True)
 for i,(r,p) in enumerate(((r1,p1),(r2,p2)),1):
  save(runtime/'release-gates'/f'g{i}'/'install-pass.json',{'revision':r,'status':'PASS','direct_operator_health':'PASS','guardian_realtime':'PASS','observed_at':f'2026-0{i}-01T00:00:00Z'})
 policy={'physical_release_retention':{'rollback_slots':2,'max_physical_releases_after_consolidation':3,'rollback_selection_strategy':'MOST_RECENT_STRONGLY_VERIFIED_DISTINCT_REVISIONS','runtime_evidence_root':str(runtime),'verification_evidence_root':str(t/'evidence'),'protect_declared_active_release_rollback':True}}
 normal=ic.build_plan(platform,policy,t/'evidence')
 assert normal['keep_count']==3 and normal['retire_count']==0,normal
 assert normal['promotion_staging_slot_reserved'] is False
 print('CHACHA_DEV_PROMOTION_NORMAL_RETENTION_UNCHANGED=PASS')
 staged=ic.build_plan(platform,policy,t/'evidence',cand,'sha256:'+'a'*64)
 rows={x['revision']:x for x in staged['rows']}
 assert staged['promotion_staging_slot_reserved'] is True and staged['effective_rollback_slots']==1,staged
 assert staged['keep_count']==2 and staged['retire_count']==1,staged
 assert rows[r3]['action']=='KEEP' and rows[r2]['action']=='KEEP' and rows[r1]['action']=='RETIRE',rows
 assert staged['selected_rollback_revisions']==[r2],staged
 print('CHACHA_DEV_PROMOTION_PRESTAGE_SLOT_RESERVATION=PASS')


# Active release metadata from newer promotions may carry rollback_path without rollback_revision.
# The declared rollback path must remain protected and win the single staging rollback slot.
with tempfile.TemporaryDirectory() as td:
 t=Path(td);platform=t/'platform';rels=platform/'releases';rels.mkdir(parents=True);runtime=t/'runtime';runtime.mkdir()
 r1='1'*40;r2='2'*40;r3='3'*40;cand='4'*40
 p1=release(rels,'20260101-'+r1,r1);p2=release(rels,'20260201-'+r2,r2);p3=release(rels,'20260301-'+r3,r3)
 save(p3/'.release-preparation.json',{'version':'1.0.0','rollback_path':str(p2.resolve())})
 (platform/'current').symlink_to(p3,target_is_directory=True)
 for i,r in enumerate((r1,r2),1):
  save(runtime/'release-gates'/f'g{i}'/'install-pass.json',{'revision':r,'status':'PASS','direct_operator_health':'PASS','guardian_realtime':'PASS','observed_at':f'2026-0{i}-01T00:00:00Z'})
 policy={'physical_release_retention':{'rollback_slots':2,'max_physical_releases_after_consolidation':3,'rollback_selection_strategy':'MOST_RECENT_STRONGLY_VERIFIED_DISTINCT_REVISIONS','runtime_evidence_root':str(runtime),'verification_evidence_root':str(t/'evidence'),'protect_declared_active_release_rollback':True}}
 staged=ic.build_plan(platform,policy,t/'evidence',cand,'sha256:'+'b'*64)
 rows={x['revision']:x for x in staged['rows']}
 assert staged['declared_rollback_revision']==r2,staged
 assert staged['declared_rollback_protected'] is True,staged
 assert staged['selected_rollback_revisions']==[r2],staged
 assert rows[r2]['action']=='KEEP' and rows[r2]['reason']=='DECLARED_ROLLBACK',rows
 assert rows[r1]['action']=='RETIRE',rows
 print('CHACHA_DEV_PROMOTION_ROLLBACK_PATH_PROTECTION=PASS')


# Historical runtime gate files may be pruned, but a prior finalized governed promotion
# remains durable proof that a physical release is a valid rollback candidate.
with tempfile.TemporaryDirectory() as td:
 t=Path(td);platform=t/'platform';rels=platform/'releases';rels.mkdir(parents=True);runtime=t/'runtime';runtime.mkdir()
 r1='1'*40;r2='2'*40;r3='3'*40;cand='4'*40
 p1=release(rels,'20260101-'+r1,r1);p2=release(rels,'20260201-'+r2,r2);p3=release(rels,'20260301-'+r3,r3)
 save(p1/'.release-preparation.json',{'version':'1.0.0','promotion_acceptance_status':'PASS','promotion_final_verification':'PASS'})
 save(p2/'.release-preparation.json',{'version':'1.0.0','promotion_acceptance_status':'PASS','promotion_final_verification':'PASS'})
 save(p3/'.release-preparation.json',{'version':'1.0.0','rollback_path':str(p2.resolve()),'promotion_acceptance_status':'PASS','promotion_final_verification':'PASS'})
 (platform/'current').symlink_to(p3,target_is_directory=True)
 policy={'physical_release_retention':{'rollback_slots':2,'max_physical_releases_after_consolidation':3,'rollback_selection_strategy':'MOST_RECENT_STRONGLY_VERIFIED_DISTINCT_REVISIONS','runtime_evidence_root':str(runtime),'verification_evidence_root':str(t/'evidence'),'protect_declared_active_release_rollback':True}}
 staged=ic.build_plan(platform,policy,t/'evidence',cand,'sha256:'+'c'*64)
 rows={x['revision']:x for x in staged['rows']}
 assert staged['declared_rollback_protected'] is True,staged
 assert staged['selected_rollback_revisions']==[r2],staged
 assert rows[r2]['reason']=='DECLARED_ROLLBACK' and rows[r1]['action']=='RETIRE',rows
 assert staged['architecture_council_final_authority'] is False
 assert staged['architecture_council_recommendation_authority'] is True
 print('CHACHA_DEV_PROMOTION_FINALIZED_RELEASE_ROLLBACK_EVIDENCE=PASS')
 # Candidate must not exist before reservation plan.
 release(rels,'20260401-'+cand,cand)
 expect(lambda:ic.build_plan(platform,policy,t/'evidence',cand,'sha256:'+'a'*64),'PROMOTION_STAGING_CANDIDATE_ALREADY_MATERIALIZED')
 print('CHACHA_DEV_PROMOTION_PRESTAGE_REQUIRES_UNMATERIALIZED_CANDIDATE=PASS')

with tempfile.TemporaryDirectory() as td:
 t=Path(td);approval=t/'approval.json';cand='4'*40;tree='5'*40
 save(approval,{'schema':'chacha.dev/production-approval/v1','scope':'platform-promotion-release-slot-reservation','approved':True,'approved_by':'operator','revision':cand,'tree':tree})
 rev,dig=ic.promotion_staging_approval(approval);assert rev==cand and dig.startswith('sha256:')
 save(t/'bad.json',{'schema':'chacha.dev/production-approval/v1','scope':'wrong','approved':True,'approved_by':'operator','revision':cand,'tree':tree})
 expect(lambda:ic.promotion_staging_approval(t/'bad.json'),'PROMOTION_STAGING_APPROVAL_SCOPE_INVALID')
 print('CHACHA_DEV_PROMOTION_PRESTAGE_EXACT_OPERATOR_APPROVAL=PASS')

# Activation must fail closed before current mutation if four physical releases exist.
with tempfile.TemporaryDirectory() as td:
 t=Path(td);runtime=t/'runtime';runtime.mkdir();rels=t/'releases';rels.mkdir();old=rels/'old';old.mkdir();rel=rels/'candidate';rel.mkdir();o1=rels/'other1';o1.mkdir();o2=rels/'other2';o2.mkdir();current=t/'current';current.symlink_to(old,target_is_directory=True)
 for i,pth in enumerate((old,rel,o1,o2)): (pth/'.revision').write_text((str(i+1)*40)+'\n')
 (rel/'dev-hub/config').mkdir(parents=True);save(rel/'dev-hub/config/emergency-stop.v1.json',{'schema':'chacha.dev/emergency-stop/v1','state_file':str(t/'stop.json')});save(t/'stop.json',{'active':False})
 meta={'candidate_revision':'a'*40,'candidate_tree':'b'*40,'human_production_approval_present':True,'platform_qualification':'PASS','guardian_pre_action':'PASS','sentinel_exact_revision':'PASS','rollback_path':str(old),'automatic_external_spend_eur':0};save(rel/'.release-preparation.json',meta)
 import promotion_transaction as ptx
 acq=ptx.acquire(runtime,'promotion-overage','owner','a'*40,300)
 expect(lambda:gpp.activate(rel,current,runtime,t/'activation.json','promotion-overage',acq['lease_token']),'RELEASE_RETENTION_OVERAGE_PRE_ACTIVATION')
 assert current.resolve()==old.resolve()
 print('CHACHA_DEV_PROMOTION_OVERAGE_BLOCKS_BEFORE_CURRENT_SWITCH=PASS')

policy=json.load(open(ROOT/'dev-hub/config/platform-promotion-transaction.v1.json'))
assert policy['invariants']['pre_materialization_release_slot_reservation_required_when_release_count_at_limit'] is True
assert policy['invariants']['activation_fails_closed_on_release_retention_overage'] is True
assert policy['guardian_pre_contract']['canonical_permission']=='workspace-write'
assert policy['guardian_pre_contract']['direct_production_deploy_probe_is_diagnostic_only'] is True
print('CHACHA_DEV_PROMOTION_PRESTAGE_POLICY=PASS')
print('CHACHA_DEV_PROMOTION_PRESTAGE_RELEASE_SLOT=PASS')
