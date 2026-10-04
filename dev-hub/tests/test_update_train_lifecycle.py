#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'dev-hub/bin'));import update_train_lifecycle as u
p=json.loads((ROOT/'dev-hub/config/update-train-lifecycle.v1.json').read_text())
r={k:'x' for k in p['recipe']['required_fields']};r['dependencies']=[];r['conflicts']=[];r['evidence_refs']=['e'];r['qualification_refs']=['q'];r['build_route']=['b'];r['changed_paths']=['p'];r['artifact_digests']=['d'];sealed=u.seal_recipe(r,p);assert sealed['sealed'] and sealed['sealed_digest'].startswith('sha256:')
reg=u.shelf({'items':{}},'t1','later',sealed,False);assert reg['items']['t1']['state']=='SHELVED' and reg['items']['t1']['reactivation_available'];assert reg['items']['t1']['physical_retirement_authorized'] is False
try:u.shelf({'items':{}},'t2','later',sealed,True);raise AssertionError('active shelf must block')
except ValueError as e:assert 'GOVERNED_ROLLBACK' in str(e)
req=u.rehydrate_request(reg,'t1');assert req['production_authority'] is False and req['current_policy_revalidation_required']
print('CHACHA_DEV_UPDATE_TRAIN_LIFECYCLE_TEST=PASS')
