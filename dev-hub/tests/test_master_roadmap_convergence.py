#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
M=json.loads((ROOT/"dev-hub/config/master-roadmap.v1.json").read_text())
assert M["authority"]["autonomy_gap_roadmap_role"]=="DERIVED_SPECIALIZED_VIEW_ONLY"
assert M["baseline"]["historical_unreconciled_candidate_is_descendant_of_current_production"] is False
assert M["baseline"]["production_ancestry_reconciled"] is True
by={x["id"]:x for x in M["legacy_audit"]}
assert by["v5-reference-architecture"]["classification"]=="RETAIN_EXTEND"
assert by["project-planner-v1"]["classification"]=="MIGRATE"
assert by["technical-design-router-v1"]["classification"]=="RETAIN_EXTEND"
assert by["domain-orchestration-v6"]["classification"]=="MIGRATE"
assert by["object-factory-v770"]["classification"].startswith("RETAIN")
assert by["structural-architecture-gates"]["classification"]=="CONVERGE_BRANCH"
assert by["canonical-path-standalone"]["classification"]=="SUPERSEDED_SEMANTICS_RETAINED"
assert by["remote-operator-mcp"]["classification"]=="PARALLEL_TRACK"
assert by["autonomy-gap-roadmap"]["decision"].find("derived view")>=0
assert by["wfgg-radar-and-other-product-projects"]["classification"]=="VALIDATION_PROJECT_ONLY"
rec={x["id"]:x for x in M["production_convergence_order"]}
assert rec["RECURSIVE_SPECIALIZATION_FOUNDATION"]["state"]=="SHADOW_FOUNDATION_IMPLEMENTED_PENDING_EXACT_SHA_CI"
assert rec["FEASIBILITY_AND_SOLUTION_COMPOSER"]["state"]=="SHADOW_IMPLEMENTED_PENDING_EXACT_SHA_CI"
assert rec["ARTIFACT_AND_SPECIALIST_BINDING_PARALLEL_BUILD"]["state"].startswith("SHADOW_IMPLEMENTED_LOCAL_QUALIFICATION_PASS")
assert rec["RESOURCE_AWARE_EXECUTION"]["state"].startswith("SHADOW_PLANNER_IMPLEMENTED_LOCAL_QUALIFICATION_PASS")
assert rec["VIRTUAL_OS_DEVICE_LAB"]["state"]=="SHADOW_PLANNER_IMPLEMENTED_REAL_QNAP_INVENTORY_PASS"
orders=[x["order"] for x in M["production_convergence_order"]]
assert orders==list(range(len(orders)))
assert M["production_convergence_order"][0]["id"]=="BASELINE_RECONCILIATION"
repl={x["rule"]:x["replacement"] for x in M["obsolete_or_replaced_rules"]}
assert "Agent Foundry precedes every domain execution" in repl
assert "Only one write-capable specialist may mutate a project at a time" in repl

convoys=M.get("historical_release_convoys",[])
convoy=next((x for x in convoys if x.get("id")=="historical-roadmap-trains-06-12"),None)
assert convoy is not None
assert convoy["individual_promotion_receipts"] is False
assert convoy["current_resolution"]=="ABSORBED_IN_CONVERGED_BASELINE"
assert convoy["converged_baseline_sha"]=="f58d76f034b7e5ec423e312d78f8ca92b8d92111"
assert convoy["convoy_closure_sha"]=="d0e3283efc677ef359006ea6632f125820597730"
assert [x["train"] for x in convoy["trains"]]==[6,7,8,9,10,11,12]


trains={x.get("id"):x for x in M.get("historical_release_trains",[])}
assert trains["historical-roadmap-train-03"]["promotion_state"]=="PROMOTED_AND_ANCESTOR_OF_CURRENT_PRODUCTION"
assert trains["historical-roadmap-train-03"]["promoted_revision"]=="3d403f60fe1a5c836b6fb84ddef24b7d74378307"
assert trains["historical-roadmap-train-03"]["current_production_descends_from_train03"] is True
assert trains["historical-roadmap-train-04"]["promotion_state"]=="NOT_PROMOTED"
assert trains["historical-roadmap-train-04"]["qualified_candidate_revision"]=="3197446894758202d9f879f881fda4f8a61f980f"
assert trains["historical-roadmap-train-05"]["promotion_state"]=="NOT_PROMOTED"
assert trains["historical-roadmap-train-05"]["depends_on_promotion"] is True
assert trains["historical-roadmap-train-05"]["production_mutation"] is False

print("CHACHA_DEV_MASTER_ROADMAP_CONVERGENCE=PASS")
print("AUTONOMY_ROADMAP_ROLE=DERIVED_VIEW")
print("PRODUCTION_BASELINE_RECONCILIATION=PASS")
