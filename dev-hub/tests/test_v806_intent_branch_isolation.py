#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

fio=loadmod("v806_fio",ROOT/"dev-hub/bin/functional-intent-orchestrator.py")
cfg=json.loads((ROOT/"dev-hub/config/domain-orchestration.v1.json").read_text(encoding="utf-8"))

assert fio.keyword_matches(fio.normalize("promotion en production"),"motion") is False
assert fio.keyword_matches(fio.normalize("build backend"),"ui") is False
assert fio.keyword_matches(fio.normalize("motion design"),"motion") is True
assert fio.keyword_matches(fio.normalize("mise en page responsive"),"mise en page") is True

plan_false=fio.make_plan({"text":"Corrige la promotion production avec rollback et conversation."},cfg)
assert "animation" not in plan_false["primary_domains"],plan_false["reasons"]
assert "graphics" not in plan_false["review_domains"],plan_false["review_domains"]

plan_real=fio.make_plan({"text":"Ajoute une animation motion avec transition."},cfg)
assert "animation" in plan_real["primary_domains"],plan_real["reasons"]
assert "graphics" in plan_real["review_domains"],plan_real["review_domains"]

council=(ROOT/"dev-hub/bin/architecture-decision-council.py").read_text(encoding="utf-8")
assert 'not bool(branch.get("blocked"))' not in council
assert 'str(x.get("package_id") or "")==pid' in council

orch=(ROOT/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert 'next_stage="BRANCH_REPLAN_REQUIRED"' in orch
assert orch.index('next_stage="BRANCH_REPLAN_REQUIRED"') < orch.index('next_stage="CAPABILITY_BUILD_REQUIRED"')

print("CHACHA_DEV_V806_PROMOTION_DOES_NOT_MATCH_MOTION=PASS")
print("CHACHA_DEV_V806_BUILD_DOES_NOT_MATCH_UI=PASS")
print("CHACHA_DEV_V806_REAL_MOTION_STILL_MATCHES_ANIMATION=PASS")
print("CHACHA_DEV_V806_PACKAGE_LOCAL_BRANCH_BLOCKING=PASS")
print("CHACHA_DEV_V806_REAL_BLOCKER_ROUTING=PASS")
print("CHACHA_DEV_V806_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
