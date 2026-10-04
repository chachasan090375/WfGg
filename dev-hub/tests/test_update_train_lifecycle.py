#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import update_train_lifecycle as u
p=json.loads((ROOT/'dev-hub/config/update-train-lifecycle.v1.json').read_text())
assert p['mode']=='RECIPE_FIRST_BUILD_ON_DEMAND'
assert p['artifact_policy']['normal_state_after_qualification_and_recipe_seal']=='RECIPE_ONLY'

def recipe(mode='BINARY_EXACT'):
    r={k:'x' for k in p['recipe']['required_fields']}
    r.update({
      'train_id':'t1','source_revision':'a'*40,'source_tree':'b'*40,'parent_revision':'c'*40,
      'functional_summary':'demo','platform_value':{'reliability':80},'implementation_strategy':'OWNED_REBUILD',
      'dependencies':[],'conflicts':[],'evidence_refs':['e'],'qualification_refs':['q'],'build_route':['b'],'changed_paths':['p'],
      'artifact_digests':['sha256:'+'1'*64],
      'dependency_lock_digest':'sha256:'+'2'*64,'build_environment_digest':'sha256:'+'3'*64,'sbom_digest':'sha256:'+'4'*64,
      'reproducibility_mode':mode,
    })
    return r

sealed=u.seal_recipe(recipe(),p)
assert sealed['state']=='RECIPE_SEALED' and sealed['sealed'] is True and sealed['sealed_digest'].startswith('sha256:')
reg=u.register_recipe_only({'items':{}},'t1',sealed)
row=reg['items']['t1']
assert row['state']=='RECIPE_ONLY' and row['physical_train_present'] is False and row['rebuild_available'] is True
assert row['cache_is_source_of_truth'] is False and row['production_mutation'] is False
req=u.rebuild_request(reg,'t1')
assert req['state']=='REBUILD_REQUESTED' and req['production_authority'] is False and req['reproducibility_verification_required'] is True
result={
 'source_tree':sealed['source_tree'],'dependency_lock_digest':sealed['dependency_lock_digest'],
 'build_environment_digest':sealed['build_environment_digest'],'sbom_digest':sealed['sbom_digest'],
 'tests_passed':True,'artifact_digests':list(sealed['artifact_digests'])
}
vr=u.verify_rebuild(reg,'t1',sealed,result)
assert vr['status']=='PASS' and reg['items']['t1']['state']=='REPRODUCIBILITY_VERIFIED'
st=u.staging_request(reg,'t1')
assert st['state']=='STAGING' and st['human_promotion_gate_required'] is True and st['direct_current_switch'] is False

# Exact-binary mismatch must fail closed.
sealed2=u.seal_recipe({**recipe(),'train_id':'t2'},p)
reg2=u.register_recipe_only({'items':{}},'t2',sealed2)
bad={**result,'source_tree':sealed2['source_tree'],'artifact_digests':['sha256:'+'9'*64]}
vr2=u.verify_rebuild(reg2,'t2',sealed2,bad)
assert vr2['status']=='BLOCK' and reg2['items']['t2']['state']=='BLOCKED' and reg2['items']['t2']['promotion_allowed'] is False

# Functional deterministic mode may produce non-identical artifact bytes, but only with full contract proof.
sealed3=u.seal_recipe({**recipe('FUNCTIONAL_DETERMINISTIC'),'train_id':'t3'},p)
reg3=u.register_recipe_only({'items':{}},'t3',sealed3)
functional={
 'source_tree':sealed3['source_tree'],'dependency_lock_digest':sealed3['dependency_lock_digest'],
 'build_environment_digest':sealed3['build_environment_digest'],'sbom_digest':sealed3['sbom_digest'],
 'tests_passed':True,'functional_contract_verified':True,'artifact_digests':['sha256:'+'8'*64]
}
vr3=u.verify_rebuild(reg3,'t3',sealed3,functional)
assert vr3['status']=='PASS' and reg3['items']['t3']['state']=='REPRODUCIBILITY_VERIFIED'

# Legacy shelving remains only for old records; ACTIVE can never be shelved implicitly.
try:
    u.shelf({'items':{}},'legacy','later',sealed,True)
    raise AssertionError('active legacy shelf must block')
except ValueError as e:
    assert 'GOVERNED_ROLLBACK' in str(e)

print('CHACHA_DEV_UPDATE_TRAIN_LIFECYCLE_RECIPE_FIRST=PASS')
print('DEFAULT_STATE_AFTER_QUALIFICATION=RECIPE_ONLY')
print('REBUILD_REPRODUCIBILITY_GATE=PASS')
print('ACTIVE_ROLLBACK_RELEASE_PROTECTION=PRESERVED')
