#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_evolution_controller as aec
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json");policy=load(CFG/"agent-evolution.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")

assert "technology-radar-agent" not in routing["roles"],routing["roles"].keys()
rules=[x for x in routing["routing_rules"] if x.get("primary_role")=="technology-watch-agent"]
assert rules,routing["routing_rules"]
assert all("radar" not in [str(v).lower() for v in x.get("match") or []] for x in rules),rules
assert routing["scope_exclusions"]["technology-radar-agent"]["project_id"]=="wfgg-radar"
assert project["agents"][0]["scope"]=="PROJECT_ONLY" and project["agents"][0]["central_brain_role"] is False,project

inv=aec.build_inventory(routing,seven,[project])
assert inv["agent_count"]==35,inv["agent_count"]
platform=[x for x in inv["agents"] if x["scope"]=="PLATFORM"]
project_agents=[x for x in inv["agents"] if x["scope"]=="PROJECT"]
assert len(platform)==34 and len(project_agents)==1,(len(platform),len(project_agents))
assert any(x["agent_id"]=="technology-radar-agent" and x["project_id"]=="wfgg-radar" for x in project_agents)

assert policy["cadence"]["lightweight_health_hours"]==24
assert policy["cadence"]["deep_agent_audit_days"]==7
assert policy["cadence"]["ecosystem_benchmark_days"]==30
assert "IMPLEMENTATION_CODE" in policy["evolution_surfaces"] and "INTERNAL_ARCHITECTURE" in policy["evolution_surfaces"] and "FUNCTIONS_AND_CAPABILITIES" in policy["evolution_surfaces"]

good={"dimensions":{k:90 for k in aec.DIMENSIONS},"technology_debt":5}
g=aec.score("test-engineer",good,policy);assert g["recommendation"]=="KEEP",g

weak={"dimensions":{k:82 for k in aec.DIMENSIONS},"technology_debt":15,"handoff_failures":1}
weak["dimensions"]["robustness"]=55
w=aec.score("backend-api-architect",weak,policy)
assert w["recommendation"] in {"SHADOW_CANDIDATE","BLOCK_AND_REVIEW"},w
routes={x["route"] for x in w["logician_challenge"]["falsification_paths"]}
assert "FAULT_INJECTION" in routes and "INCUMBENT_VS_CANDIDATE_SHADOW_COMPARISON" in routes,routes
assert w["logician_challenge"]["decision_authority"] is False

p=aec.plan("backend-api-architect",w,policy)
assert p["self_evolution"]["proposal_allowed"] is True,p
assert p["self_evolution"]["active_self_mutation"] is False,p
assert p["self_evolution"]["self_promotion"] is False,p
assert p["self_evolution"]["permission_expansion"] is False,p
assert p["candidate"]["owner"]=="agent-foundry" and p["candidate"]["isolated"] is True,p
assert p["candidate"]["incumbent_control_group"] is True,p
assert p["assurance"]["technology_watch_required"] is True,p
assert p["assurance"]["guardian_permission_diff_required"] is True,p
assert p["assurance"]["sentinel_regression_required"] is True,p
assert p["assurance"]["architecture_council_final_authority"] is True,p
assert p["promotion"]["latest_version_priority"] is False,p
assert p["automatic_external_spend_eur"]==0,p

print("CHACHA_DEV_V646_TECHNOLOGY_RADAR_PLATFORM_ROUTING=REMOVED")
print("CHACHA_DEV_V646_TECHNOLOGY_RADAR_PROJECT_SCOPE=PASS")
print("CHACHA_DEV_V646_AGENT_INVENTORY_35=PASS")
print("CHACHA_DEV_V646_REGULAR_EVOLUTION_CADENCE=PASS")
print("CHACHA_DEV_V646_AGENT_FUNCTION_ARCHITECTURE_CODE_EVOLUTION=PASS")
print("CHACHA_DEV_V646_LOGICIAN_AGENT_FALSIFICATION=PASS")
print("CHACHA_DEV_V646_ACTIVE_SELF_MUTATION=NO")
print("CHACHA_DEV_V646_SELF_PROMOTION=NO")
print("CHACHA_DEV_V646_INCUMBENT_CONTROL_GROUP=YES")
print("CHACHA_DEV_V646_GUARDIAN_PERMISSION_DIFF=REQUIRED")
print("CHACHA_DEV_V646_SENTINEL_REGRESSION=REQUIRED")
print("CHACHA_DEV_V646_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V646_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
