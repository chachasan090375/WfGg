#!/usr/bin/env python3
from __future__ import annotations
import copy,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import autonomy_roadmap_evolution_router as router
import canonical_component_registry as ccr

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
road=load(ROOT/"dev-hub/config/autonomy-gap-roadmap.v1.json")
policy=load(ROOT/"dev-hub/config/autonomy-roadmap-evolution-routing.v1.json")
canonical=ccr.build_registry(ROOT,load(ROOT/"dev-hub/config/canonical-component-registry.v1.json"))
assert set(policy["rules"])=={x["id"] for x in road["gaps"]},(set(policy["rules"]),{x["id"] for x in road["gaps"]})
with tempfile.TemporaryDirectory(prefix="roadmap-evolution-router-") as td:
    rt=Path(td)
    plan=router.build_plan(road,policy,canonical)
    assert plan["routing_complete"] is True,plan
    expected_requests=sum(1 for g in road["gaps"] if g["status"] in policy["eligible_statuses"] and policy["rules"][g["id"]]["mode"]!="HUMAN_BOUNDARY")
    assert plan["request_count"]==expected_requests,plan
    assert plan["closed_count"]==3,plan
    assert plan["human_boundary_count"]==1,plan
    assert plan["blocked_count"]==0,plan
    bygap={x["roadmap_gap_id"]:x for x in plan["requests"]}
    assert bygap["provider-independence"]["candidate_owner"]=="capability-foundry",bygap["provider-independence"]
    assert bygap["cognitive-memory-fabric"]["component_id"]=="core:learning-fabric",bygap["cognitive-memory-fabric"]
    assert all(x["candidate_owner"]=="branch-foundry" for k,x in bygap.items() if k!="provider-independence")
    assert bygap["constitution"]["routing_mode"]=="GOVERNED_REASSESS",bygap["constitution"]
    assert plan["human_boundaries"][0]["gap_id"]=="resilience-ha",plan["human_boundaries"]
    assert all(x["direct_component_mutation"] is False and x["self_promotion"] is False for x in plan["requests"])
    assert all(x["architecture_council_final_authority"] is False for x in plan["requests"])
    assert all(x["architecture_council_recommendation_authority"] is True for x in plan["requests"])
    first=router.apply_plan(rt,policy,plan)
    assert first["managed_request_file_count"]==expected_requests,first
    assert len(first["written_files"])==expected_requests,first
    second=router.apply_plan(rt,policy,plan)
    assert len(second["unchanged_files"])==expected_requests and not second["written_files"],second
    road2=copy.deepcopy(road)
    next(x for x in road2["gaps"] if x["id"]=="learning").update({"status":"GREEN","progress":100})
    plan2=router.build_plan(road2,policy,canonical)
    third=router.apply_plan(rt,policy,plan2)
    assert plan2["request_count"]==expected_requests-1,plan2
    assert any("learning" in x for x in third["removed_stale_files"]),third
    bad=copy.deepcopy(policy);bad["rules"]["learning"]={"mode":"AUTO_REASSESS","component_id":"core:not-real"}
    blocked=router.build_plan(road,bad,canonical)
    assert blocked["routing_complete"] is False and any(x.get("blocker")=="CANONICAL_COMPONENT_NOT_FOUND" for x in blocked["blocked"]),blocked
source=(ROOT/"dev-hub/bin/agent_evolution_daily_cycle.py").read_text(encoding="utf-8")
assert "autonomy_roadmap_evolution_router as arer" in source,source
assert "arer.route(root,runtime,canonical)" in source,source
assert source.index("arer.route(root,runtime,canonical)") < source.index("collect_reassessment_requests(runtime)"),source
print("CHACHA_DEV_AUTONOMY_ROADMAP_RULE_COVERAGE=PASS")
print("CHACHA_DEV_AUTONOMY_ROADMAP_TO_REASSESSMENT_QUEUE=PASS")
print("CHACHA_DEV_AUTONOMY_ROADMAP_ROUTING_IDEMPOTENT=PASS")
print("CHACHA_DEV_AUTONOMY_ROADMAP_STALE_REQUEST_CLEANUP=PASS")
print("CHACHA_DEV_AUTONOMY_ROADMAP_HUMAN_BOUNDARY=PASS")
print("CHACHA_DEV_AUTONOMY_ROADMAP_DIRECT_MUTATION=NO")
print("CHACHA_DEV_AUTONOMY_ROADMAP_SELF_PROMOTION=NO")
print("CHACHA_DEV_AUTONOMY_ROADMAP_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
