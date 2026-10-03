#!/usr/bin/env python3
import importlib.util, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'dev-hub/bin'))
p=ROOT/'dev-hub/bin/guardian-client.py';spec=importlib.util.spec_from_file_location('gc',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import urllib.request
assert m._d1_quota_applies(urllib.request.Request('https://guardian.example.invalid/v1/check')) is True
assert m._d1_quota_applies(urllib.request.Request('http://127.0.0.1:8871/v1/check')) is False
assert m._d1_quota_applies(urllib.request.Request('http://localhost:8871/v1/check')) is False
print('CHACHA_DEV_SOVEREIGN_GUARDIAN_D1_QUOTA_DECOUPLING=PASS')
