#!/usr/bin/env python3
import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
imp=load('ssi',ROOT/'dev-hub/bin/sovereign-state-multi-service-import.py')
par=load('ssp',ROOT/'dev-hub/bin/sovereign-state-multi-service-parity.py')
assert set(imp.SERVICES)=={'guardian','sentinel','assurance-exchange','learning-relay'}
assert set(par.SERVICES)==set(imp.SERVICES)
assert 'technical_workflow_attestations' in imp.SERVICES['sentinel']['required']
assert 'assurance_correlations' in imp.SERVICES['assurance-exchange']['required']
assert 'specialist_authority_reviews' in imp.SERVICES['assurance-exchange']['required']
assert 'external_final_reviews' in imp.SERVICES['assurance-exchange']['required']
assert 'learning_deltas' in imp.SERVICES['learning-relay']['required']
print('CHACHA_DEV_SOVEREIGN_MULTI_SERVICE_CONTRACT=PASS')
