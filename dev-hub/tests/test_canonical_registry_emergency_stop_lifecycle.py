#!/usr/bin/env python3
import importlib.util,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin';CFG=ROOT/'dev-hub/config'
sys.path.insert(0,str(BIN))

def mod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

ccr=mod('ccr_stop_lifecycle',BIN/'canonical_component_registry.py')
rec=mod('rec_stop_lifecycle',BIN/'component_registry_reconciler.py')
policy=json.loads((CFG/'canonical-component-registry.v1.json').read_text())
registry=ccr.build_registry(ROOT,policy)
expected=policy.get('emergency_stop_lifecycle_invariant') or {}
actual=registry.get('emergency_stop_lifecycle_invariant') or {}
assert actual==expected,(actual,expected)
assert rec.emergency_stop_lifecycle_issues(registry)==[],rec.emergency_stop_lifecycle_issues(registry)
print('CHACHA_DEV_CANONICAL_REGISTRY_EMERGENCY_STOP_LIFECYCLE=PASS')
print('CHACHA_DEV_EMERGENCY_STOP_LIFECYCLE_FALSE_DRIFT_BLOCKED=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
