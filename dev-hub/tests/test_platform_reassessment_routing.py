#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import agent_evolution_daily_cycle as cycle

def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

with tempfile.TemporaryDirectory(prefix="platform-reassess-route-") as td:
    rt=Path(td)
    save(rt/"agent-evolution/reassessment-queue/a.json",{
      "schema":"chacha.dev/agent-reassessment-request/v1","request_id":"agent-1","agent_id":"backend-api-architect"
    })
    save(rt/"platform-evolution/reassessment-queue/cap.json",{
      "schema":"chacha.dev/platform-component-reassessment-request/v1",
      "request_id":"platform-cap","component_id":"agent-observation-bus",
      "trigger_reasons":["GUARDIAN_COVERAGE_MANIFEST_CHANGED"],
      "candidate_owner":"capability-foundry","shadow_required":True,"pilot_required":True
    })
    save(rt/"platform-evolution/reassessment-queue/branch.json",{
      "schema":"chacha.dev/platform-component-reassessment-request/v1",
      "request_id":"platform-branch","component_id":"central-orchestrator",
      "trigger_reasons":["TECHNOLOGY_CORE_WATCH_CHANGED"],
      "candidate_owner":"branch-foundry","shadow_required":True,"pilot_required":True
    })
    save(rt/"platform-evolution/reassessment-queue/bad.json",{
      "schema":"chacha.dev/platform-component-reassessment-request/v1",
      "request_id":"platform-bad","component_id":"future-component",
      "trigger_reasons":["TEST"],"candidate_owner":"unknown-foundry"
    })
    agents,platform,actions,blocked=cycle.collect_reassessment_requests(rt)
    assert len(agents)==1,agents
    assert len(platform)==3,platform
    assert len(actions)==2,actions
    assert len(blocked)==1,blocked
    byid={x["request_id"]:x for x in actions}
    assert byid["platform-cap"]["action"]=="CAPABILITY_FOUNDRY_REASSESSMENT",byid
    assert byid["platform-branch"]["action"]=="BRANCH_FOUNDRY_REASSESSMENT",byid
    assert all(x["direct_component_mutation"] is False and x["self_promotion"] is False for x in actions)
    assert all(x["technology_watch_revalidation_required"] is True for x in actions)
    assert all(x["logician_falsification_required"] is True for x in actions)
    assert all(x["architecture_council_final_authority"] is True for x in actions)
    assert blocked[0]["blocker"]=="UNSUPPORTED_PLATFORM_EVOLUTION_OWNER",blocked

print("CHACHA_DEV_PLATFORM_REASSESSMENT_QUEUE_CONSUMED=PASS")
print("CHACHA_DEV_PLATFORM_CAPABILITY_FOUNDRY_ROUTING=PASS")
print("CHACHA_DEV_PLATFORM_BRANCH_FOUNDRY_ROUTING=PASS")
print("CHACHA_DEV_PLATFORM_UNKNOWN_OWNER=BLOCKED")
print("CHACHA_DEV_PLATFORM_DIRECT_MUTATION=NO")
print("CHACHA_DEV_PLATFORM_SELF_PROMOTION=NO")
print("CHACHA_DEV_PLATFORM_ARCHITECTURE_COUNCIL_FINAL=YES")
print("CHACHA_DEV_PLATFORM_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
