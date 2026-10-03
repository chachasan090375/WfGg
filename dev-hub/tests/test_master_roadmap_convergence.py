#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
M=json.loads((ROOT/"dev-hub/config/master-roadmap.v1.json").read_text())
assert M["authority"]["autonomy_gap_roadmap_role"]=="DERIVED_SPECIALIZED_VIEW_ONLY"
assert M["baseline"]["candidate_is_descendant_of_current_production"] is False
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
orders=[x["order"] for x in M["production_convergence_order"]]
assert orders==list(range(len(orders)))
assert M["production_convergence_order"][0]["id"]=="BASELINE_RECONCILIATION"
repl={x["rule"]:x["replacement"] for x in M["obsolete_or_replaced_rules"]}
assert "Agent Foundry precedes every domain execution" in repl
assert "Only one write-capable specialist may mutate a project at a time" in repl
print("CHACHA_DEV_MASTER_ROADMAP_CONVERGENCE=PASS")
print("AUTONOMY_ROADMAP_ROLE=DERIVED_VIEW")
print("PRODUCTION_BASELINE_RECONCILIATION_REQUIRED=YES")
