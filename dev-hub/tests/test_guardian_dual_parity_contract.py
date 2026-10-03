#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'dev-hub/bin/guardian-dual-parity.py').read_text()
assert "production_cutover_authorized':False" in s
assert "norm(l)==norm(r)" in s
assert "guardian_client as gc" in s
print('CHACHA_DEV_GUARDIAN_DUAL_PARITY_CONTRACT=PASS')
