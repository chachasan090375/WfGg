#!/usr/bin/env python3
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'bin/adaptive-model-registry.py'
s=importlib.util.spec_from_file_location('reg',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
REG=json.load(open(ROOT/'config/adaptive-model-registry.v1.json'))
GWS=json.load(open(ROOT/'config/adaptive-cognitive-gateways.v1.json'))

def test_default_registry_keeps_unbound_external_models_ineligible():
    x=m.compile_catalog(REG,GWS)
    assert x['routing_authority']=='CHACHA_DEV'
    slots=[q for q in x['models'] if q['model']=='unbound']
    assert slots and all(q['health_state']=='UNKNOWN' for q in slots)

def test_overlay_can_bind_health_without_changing_gateway_authority():
    o={'models':{'external-reasoning-slot':{'provider':'fixture','model':'reasoner','health_state':'HEALTHY','quota_state':'AVAILABLE','status':'PILOT'}}}
    x=m.compile_catalog(REG,GWS,o);q=next(q for q in x['models'] if q['id']=='external-reasoning-slot')
    assert q['model']=='reasoner' and q['health_state']=='HEALTHY'
    assert q['gateway']=='litellm' and GWS['gateways']['litellm']['decision_authority'] is False

def test_overlay_cannot_change_gateway():
    o={'models':{'external-reasoning-slot':{'gateway':'native-local'}}}
    try:m.compile_catalog(REG,GWS,o)
    except ValueError as e:assert 'OVERLAY_FORBIDDEN_KEYS' in str(e)
    else:raise AssertionError('gateway mutation accepted')

def test_unbound_model_cannot_claim_health():
    o={'models':{'external-code-slot':{'health_state':'HEALTHY'}}}
    try:m.compile_catalog(REG,GWS,o)
    except ValueError as e:assert 'UNBOUND_MODEL_CANNOT_BE_HEALTHY' in str(e)
    else:raise AssertionError('unbound healthy model accepted')
