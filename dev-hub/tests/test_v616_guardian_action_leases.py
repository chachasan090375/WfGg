#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def text(path): return path.read_text(encoding="utf-8")

# Coverage heartbeat must prove every declared hook from the repository itself.
spec=importlib.util.spec_from_file_location("guardian_coverage",BIN/"guardian-coverage-heartbeat.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
snap=mod.build(ROOT,CFG/"guardian-coverage-manifest.v1.json")
assert snap["component_count"]>=15,snap
assert snap["all_hooks_active"] is True,[x for x in snap["components"] if not x["hook_active"]]

manifest=json.load(open(CFG/"guardian-coverage-manifest.v1.json",encoding="utf-8"))
ids={x["component_id"] for x in manifest["expected_components"]}
for required in {
  "central-orchestrator","run-controller","technology-watch",
  "agent-foundry","branch-foundry","capability-foundry",
  "architecture-decision-council","architecture-portfolio-optimizer",
  "comparative-pilot","capsule-scheduler","class:dynamic-agents","class:registered-adapters"
}:
    assert required in ids,required

worker=text(ROOT/"dev-hub/guardian/worker.js")
assert "ACTION_ID_REQUIRED" in worker
assert "POST_WITHOUT_PRE_ACTION" in worker
assert "POST_ACTION_MISSING" in worker
assert "ACTION_IDENTITY_DRIFT" in worker
assert "coverage_heartbeats" in worker
assert "expected_components" in worker
assert "COVERAGE_HEARTBEAT_STALE" in worker
assert "async scheduled(" in worker

orchestrator=text(BIN/"autonomous-project-orchestrator.py")
assert '"action_id":action_id' in orchestrator
assert 'guardian_stage(Path(script),args,"PRE_ACTION",action_id)' in orchestrator
assert 'guardian_stage(Path(script),args,"POST_ACTION",action_id)' in orchestrator
assert "GUARDIAN_STAGE_UNAVAILABLE" in orchestrator

runctl=text(BIN/"run-controller.py")
assert '"action_id": action_id' in runctl
assert "GUARDIAN_UNAVAILABLE_FAIL_CLOSED" in runctl
assert 'all_actions_fail_closed_when_unverified' in text(CFG/"run-controller.v1.json")

tech=text(BIN/"technology_watch_runtime.py")
assert '"action_id":action_id' in tech
assert '"PRE_ACTION",action_id' in tech
assert '"POST_ACTION",action_id' in tech
assert "TECHNOLOGY_WATCH_GUARDIAN_UNAVAILABLE" in tech

council=text(BIN/"architecture-decision-council.py")
assert 'guardian_subcomponent(root,"architecture-portfolio-optimizer"' in council
assert '"action_id":action_id' in council

runtime_policy=json.load(open(CFG/"guardian-runtime-policy.v1.json",encoding="utf-8"))
assert runtime_policy["all_governed_actions_require_realtime_verdict"] is True
assert runtime_policy["action_lease_required"] is True
assert runtime_policy["coverage_heartbeat_required"] is True
assert runtime_policy["low_risk_unavailable_verdict"]=="BLOCK"
assert "emergency-control-bridge" in runtime_policy["safety_exemptions"]

print("CHACHA_DEV_V616_ALL_DECLARED_HOOKS_ACTIVE=PASS")
print("CHACHA_DEV_V616_ACTION_LEASE_CONTRACT=PASS")
print("CHACHA_DEV_V616_MISSING_POST_WATCHDOG=PASS")
print("CHACHA_DEV_V616_COVERAGE_WATCHDOG=PASS")
print("CHACHA_DEV_V616_FAIL_CLOSED_REALTIME_GOVERNANCE=PASS")
print("CHACHA_DEV_V616_EMERGENCY_STOP_PATH_EXEMPT=PASS")
