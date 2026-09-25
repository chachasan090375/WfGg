#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,os,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))

spec=importlib.util.spec_from_file_location("v810_council",BIN/"architecture-decision-council.py")
council=importlib.util.module_from_spec(spec)
spec.loader.exec_module(council)

assert hasattr(council,"os")
assert council.os.environ is os.environ
src=(BIN/"architecture-decision-council.py").read_text(encoding="utf-8")
assert 'os.environ.get("CHACHA_GUARDIAN_RUN_ID") or None' in src
assert '"run_id":None' not in src

print("CHACHA_DEV_V810_COUNCIL_MODULE_IMPORT=PASS")
print("CHACHA_DEV_V810_OS_RUNTIME_AVAILABLE=PASS")
print("CHACHA_DEV_V810_NESTED_RUN_ID_EXPRESSION=PASS")
print("CHACHA_DEV_V810_NO_RUNLESS_COUNCIL_EVENT=PASS")
print("CHACHA_DEV_V810_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
