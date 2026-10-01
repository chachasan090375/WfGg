#!/usr/bin/env python3
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'bin/adaptive-output-budget.py'
s=importlib.util.spec_from_file_location('budget',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
POL=json.load(open(ROOT/'config/adaptive-output-budgeting.v1.json'))

def test_native_local_is_capped_to_32():
    x=m.decide(POL,'architecture','native-local-qwen35-08b-q4',256)
    assert x['effective_max_tokens']==32 and x['budget_reduced'] is True

def test_request_is_never_expanded():
    x=m.decide(POL,'code','external-code-slot',48)
    assert x['effective_max_tokens']==48

def test_task_budget_caps_large_request():
    x=m.decide(POL,'light-conversation','external-fast',1024)
    assert x['effective_max_tokens']==64

def test_zero_spend_authority():
    x=m.decide(POL,'private-local','native-local-qwen35-08b-q4',64)
    assert x['routing_authority']=='CHACHA_DEV'
    assert x['automatic_external_spend_eur']==0
