#!/usr/bin/env python3
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('pc',ROOT/'dev-hub/bin/plugin_center.py');pc=importlib.util.module_from_spec(spec);spec.loader.exec_module(pc)
p=json.loads((ROOT/'dev-hub/config/plugin-center.v1.json').read_text())
manifest={"plugin_id":"adaptive-model-router","title":"Adaptive Model Router","plugin_class":"PLATFORM_PLUGIN","version":"1.0.0","source_revision":"a"*40,"source_tree":"b"*40,"functional_summary":"Route models by measured task fitness","platform_value":{"cost":1,"quality":1},"capabilities":["model-routing"],"permissions":["read"],"dependencies":[],"conflicts":[],"persistent_data":[],"recipe_digest":"sha256:"+"c"*64,"qualification_refs":["sentinel:pass"],"rollback_contract":{"mode":"disable-first"},"license_and_provenance":{"status":"PASS"}}
sealed=pc.validate_manifest(manifest,p);assert sealed['sealed'] and sealed['manifest_digest'].startswith('sha256:')
reg=pc.register({"items":{}},sealed);assert reg['items']['adaptive-model-router']['state']=='QUALIFIED_RECIPE_ONLY'
req=pc.request(reg,'adaptive-model-router','INSTALL',p);assert req['requested_state']=='INSTALL_REQUESTED' and req['production_authority'] is False
reg['items']['adaptive-model-router']['state']='ACTIVE';req=pc.request(reg,'adaptive-model-router','DISABLE',p);assert req['health_check_required'] is True
reg['items']['adaptive-model-router']['state']='DISABLED';req=pc.request(reg,'adaptive-model-router','UNINSTALL',p);assert req['preserve_recipe'] is True and req['preserve_persistent_data'] is True and req['intendant_required'] is True
locked={**manifest,"plugin_id":"guardian","title":"Guardian","plugin_class":"CORE_LOCKED"};s=pc.validate_manifest(locked,p);r=pc.register({"items":{}},s,'ACTIVE')
try: pc.request(r,'guardian','DISABLE',p);raise AssertionError('CORE_LOCKED should block')
except ValueError as e: assert 'CORE_LOCKED' in str(e)
print('CHACHA_DEV_PLUGIN_CENTER_LIFECYCLE=PASS')
print('CHACHA_DEV_PLUGIN_CENTER_CORE_LOCKED=PASS')
print('CHACHA_DEV_PLUGIN_CENTER_RECIPE_PRESERVATION=PASS')
merged={**reg};merged['items']=dict(reg['items']);merged['items']['adaptive-model-router']=dict(reg['items']['adaptive-model-router']);merged['items']['adaptive-model-router']['state']='MERGED_INTO_CORE_LOCKED'
try: pc.request(merged,'adaptive-model-router','UNINSTALL',p);raise AssertionError('core-merged plugin must block')
except ValueError as e: assert 'CORE_LOCKED' in str(e)
print('CHACHA_DEV_STRUCTURAL_CORE_UPDATE_UNINSTALL=BLOCKED_AS_REQUIRED')
print('CHACHA_DEV_PLUGIN_CENTER_AUTOMATIC_EXTERNAL_SPEND_EUR=0')

# Autonomous improvement Factory must package eligible improvements as plugins by default.
import sys
sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import autonomous_improvement_factory as aif
report={'schema':'chacha.dev/improvement-intelligence-synthesis/v1','items':[{'axis_id':'watchdog-improvement','recommendation':'IMPROVEMENT_CANDIDATE','improvement_request_authorized':True,'functional_summary':'watchdog improvement','platform_value':{'reliability':1}}]}
fpol=json.loads((ROOT/'dev-hub/config/autonomous-improvement-factory.v1.json').read_text())
row=aif.build_queue(report,fpol)['items'][0]
assert row['delivery_form']=='PLUGIN_PACKAGE' and row['plugin_manifest_required'] is True and row['recipe_first'] is True
print('CHACHA_DEV_IMPROVEMENT_DEFAULT_DELIVERY=PLUGIN_PACKAGE')
