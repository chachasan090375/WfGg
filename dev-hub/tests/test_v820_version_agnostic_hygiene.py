#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,os,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))

def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);assert s and s.loader
    s.loader.exec_module(m);return m

con=mod('con',BIN/'intendant-platform-consolidator.py')
hyg=mod('hyg',BIN/'intendant-hygiene-cycle.py')
state=mod('state',BIN/'release_state_reconciler.py')

with tempfile.TemporaryDirectory(prefix='v820-v42-') as td:
    td=Path(td);platform=td/'platform';releases=platform/'releases';runtime=td/'runtime'
    releases.mkdir(parents=True);(runtime/'release-gates').mkdir(parents=True)
    rows=[('39.0.0','a'*40),('40.0.0','b'*40),('41.0.0','c'*40),('42.0.0','d'*40)]
    paths=[]
    for idx,(ver,rev) in enumerate(rows):
        p=releases/(f'r{idx}-{rev}');p.mkdir();paths.append(p)
        (p/'.revision').write_text(rev+'\n')
        prep={'schema':'chacha.dev/release-preparation/v1','version':ver,'revision':rev,
              'activation_status':'STAGED_NOT_ACTIVE' if idx==3 else 'SUPERSEDED'}
        (p/'.release-preparation.json').write_text(json.dumps(prep))
        os.utime(p,(1000+idx,1000+idx))
    (platform/'current').symlink_to(paths[-1],target_is_directory=True)

    for idx in (1,2):
        ver,rev=rows[idx]
        proof={'revision':rev,'release':str(paths[idx]),'status':'PASS',
               'direct_operator_health':'PASS','guardian_realtime':'PASS',
               'installed_at':f'2026-01-0{idx+1}T00:00:00Z'}
        (runtime/'release-gates'/f'v{idx}-install-pass.json').write_text(json.dumps(proof))

    policy=json.load(open(ROOT/'dev-hub/config/platform-consolidation.v1.json'))
    policy['physical_release_retention']['runtime_evidence_root']=str(runtime)
    policy['physical_release_retention']['verification_evidence_root']=str(td/'evidence')
    policy['physical_release_retention']['fallback_verified_rollback_revisions']=[]
    plan=con.build_plan(platform,policy,td/'evidence')
    assert plan['active_version']=='42.0.0',plan
    assert plan['active_revision']=='d'*40,plan
    assert plan['selected_rollback_revisions']==['c'*40,'b'*40],plan
    assert plan['selected_rollback_versions']==['41.0.0','40.0.0'],plan
    assert plan['missing_verified_rollback_count']==0,plan
    assert plan['keep_count']==3 and plan['retire_count']==1,plan
    assert hyg.current_version(platform)=='42.0.0'

    active_proof={'revision':'d'*40,'release':str(paths[-1]),'status':'PASS',
                  'direct_operator_health':'PASS','guardian_realtime':'PASS',
                  'installed_at':'2026-01-04T00:00:00Z'}
    (runtime/'release-gates'/'active-install-pass.json').write_text(json.dumps(active_proof))
    before=state.reconcile(platform,runtime/'release-gates',False)
    assert before['reconciliation_required'] is True and before['applied'] is False,before
    applied=state.reconcile(platform,runtime/'release-gates',True)
    assert applied['applied'] is True,applied
    after=state.reconcile(platform,runtime/'release-gates',False)
    assert after['reconciliation_required'] is False,after
print('CHACHA_DEV_DYNAMIC_RELEASE_RETENTION=PASS')
print('CHACHA_DEV_FUTURE_MAJOR_VERSION_FIXTURE=PASS')
print('CHACHA_DEV_RELEASE_STATE_RECONCILIATION=PASS')
print('CHACHA_DEV_NO_PLATFORM_MAJOR_DEPENDENCY=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
