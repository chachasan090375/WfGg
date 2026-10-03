#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
C=json.loads((ROOT/"dev-hub/config/creation-runtime-fabric.v1.json").read_text())
assert C["production_activation"] is False
assert C["external_spend_eur"]==0
assert C["infrastructure_feasibility_auditor"]["mandatory_before_solution_composition"] is True
assert C["infrastructure_feasibility_auditor"]["verdicts"]==["FIT","FIT_WITH_CONSTRAINTS","NOT_FIT"]
assert C["solution_composer"]["must_consume_feasibility_verdict"] is True
assert C["recursive_specialization"]["tree_for_functional_structure_graph_for_dependencies"] is True
assert C["artifact_fabric"]["bidirectional_chat_api"] is True
assert C["artifact_fabric"]["persistent_across_conversations"] is True
assert C["resource_aware_parallel_orchestrator"]["adaptive_concurrency"] is True
assert C["resource_aware_parallel_orchestrator"]["contract_first_parallelism"] is True
lab=C["virtual_device_os_lab"]
assert "qnap_nas" in lab["host_roles"]
assert "apple_native_runner" in lab["host_roles"]
assert lab["host_roles"]["apple_native_runner"]["automatic_paid_cloud_use"] is False
assert C["governance"]["guardian_required"] is True
assert C["governance"]["sentinel_required"] is True
print("CHACHA_DEV_CREATION_RUNTIME_FABRIC=PASS")
print("PRODUCTION_ACTIVATION=NO")
print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
