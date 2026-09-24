#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_evolution_controller as aec
import agent_fleet_observatory as afo

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

routing=load(CFG/"agent-routing.v1.json")
seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
evo=load(CFG/"agent-evolution.v1.json")
policy=load(CFG/"agent-fleet-observatory.v1.json")

assert evo["measurement"]["unknown_dimension_default_score"] is None
assert evo["measurement"]["minimum_scored_dimension_coverage_pct"]==40
inv=aec.build_inventory(routing,seven,[project])
assert inv["agent_count"]==35,inv
assert not any(a["agent_id"]=="technology-radar-agent" and a["scope"]=="PLATFORM" for a in inv["agents"])

# Missing evidence must never become an invented 50/100.
empty=aec.score("graphics-specialist",{"dimensions":{}},evo)
assert empty["recommendation"]=="MEASURE_FIRST",empty
assert empty["agent_debt"] is None,empty
assert empty["average"] is None,empty
assert empty["measurement_coverage_pct"]==0,empty
assert all(v is None for v in empty["dimensions"].values()),empty
assert any(x["route"]=="EVIDENCE_GAP_INSTRUMENTATION" for x in empty["logician_challenge"]["falsification_paths"]),empty

with tempfile.TemporaryDirectory(prefix="v647-observatory-") as td:
    runtime=Path(td)
    # Task graph maps generic task roles to canonical agents.
    graph={"schema":"chacha.dev/task-graph/v1","project":"synthetic-project","tasks":[
      {"id":"test:ok","owner_role":"testing","kind":"test"},
      {"id":"test:fail","owner_role":"testing","kind":"test"},
      {"id":"release:ok","owner_role":"release","kind":"release"}
    ]}
    save(runtime/"plans/synthetic-project/tasks.task-graph.json",graph)

    run={"schema":"chacha.dev/run-record/v1","project":"synthetic-project","waves":[{"index":1,"tasks":[
      {"task_id":"test:ok","status":"SUCCEEDED","attempts":1,"provider_bindings":[{"capability":"unit-test-js"}],
       "guardian_pre":{"verdict":"PASS"},"guardian_post":{"verdict":"PASS"}},
      {"task_id":"test:fail","status":"FAILED","attempts":2,"provider_bindings":[{"capability":"e2e-test-web"}],
       "guardian_pre":{"verdict":"PASS"},"guardian_post":{"verdict":"WARNING"}},
      {"task_id":"release:ok","status":"SUCCEEDED","attempts":1,"provider_bindings":[{"capability":"ci"}],
       "guardian_pre":{"verdict":"PASS"},"guardian_post":{"verdict":"PASS"}}
    ]}]}
    save(runtime/"runs/synthetic-project/run-1/run-record.json",run)

    ok={"schema":"chacha.dev/task-result/v1","project":"synthetic-project","task_id":"test:ok","status":"OK",
        "evidence":[{"source":"synthetic"}],"verification":{"status":"VERIFIED"}}
    fail={"schema":"chacha.dev/task-result/v1","project":"synthetic-project","task_id":"test:fail","status":"FAILED",
          "evidence":[{"source":"synthetic-failure"}],"verification":{"status":"VERIFIED"}}
    rel={"schema":"chacha.dev/task-result/v1","project":"synthetic-project","task_id":"release:ok","status":"OK",
         "evidence":[{"source":"synthetic-release"}],"verification":{"status":"VERIFIED"}}
    save(runtime/"transactions/synthetic-project/a/verified-task-result.json",ok)
    save(runtime/"transactions/synthetic-project/b/verified-task-result.json",fail)
    save(runtime/"transactions/synthetic-project/c/verified-task-result.json",rel)

    conf={"schema":"chacha.dev/component-confidence-snapshot/v1","items":[
      {"component_kind":"agent","component_id":"test-engineer","state":"TRUSTED"}
    ]}
    save(runtime/"knowledge/component-confidence.json",conf)

    report=afo.build_report(ROOT,runtime,policy,evo,routing,seven,[project])
    assert report["agent_count"]==35,report["agent_count"]
    testrow=next(x for x in report["agents"] if x["agent_id"]=="test-engineer")
    sc=testrow["scorecard"]
    assert sc["dimensions"]["accuracy"]==50.0,sc
    assert sc["dimensions"]["robustness"]==50.0,sc
    assert sc["dimensions"]["efficiency"]==round(100*2/3,1),sc
    assert sc["dimensions"]["authority_discipline"]==93.8,sc
    assert sc["dimensions"]["learning_quality"]==95.0,sc
    assert sc["dimensions"]["calibration"] is None,sc
    assert sc["measurement_coverage_pct"]>=50,sc
    assert sc["recommendation"] in {"SHADOW_CANDIDATE","BLOCK_AND_REVIEW","OPTIMIZE"},sc

    graphics=next(x for x in report["agents"] if x["agent_id"]=="graphics-specialist")
    assert graphics["scorecard"]["recommendation"]=="MEASURE_FIRST",graphics
    assert graphics["scorecard"]["agent_debt"] is None,graphics
    assert any(x["agent_id"]=="graphics-specialist" for x in report["measurement_queue"]),report["measurement_queue"]
    assert any(x["agent_id"]=="test-engineer" for x in report["optimization_queue"]),report["optimization_queue"]
    assert report["unknown_dimension_default_score"] is None
    assert report["agent_self_scoring_authority"] is False
    assert report["automatic_external_spend_eur"]==0

print("CHACHA_DEV_V647_AGENT_INVENTORY_35=PASS")
print("CHACHA_DEV_V647_UNKNOWN_DIMENSION_DEFAULT=NONE")
print("CHACHA_DEV_V647_MEASURE_FIRST_WITHOUT_EVIDENCE=PASS")
print("CHACHA_DEV_V647_TASK_ROLE_ATTRIBUTION=PASS")
print("CHACHA_DEV_V647_VERIFIED_ACCURACY_SIGNAL=PASS")
print("CHACHA_DEV_V647_RUNTIME_ROBUSTNESS_SIGNAL=PASS")
print("CHACHA_DEV_V647_EFFICIENCY_RETRY_SIGNAL=PASS")
print("CHACHA_DEV_V647_GUARDIAN_AUTHORITY_SIGNAL=PASS")
print("CHACHA_DEV_V647_COMPONENT_CONFIDENCE_SIGNAL=PASS")
print("CHACHA_DEV_V647_OPTIMIZATION_AND_MEASUREMENT_QUEUES=PASS")
print("CHACHA_DEV_V647_AGENT_SELF_SCORING_AUTHORITY=NO")
print("CHACHA_DEV_V647_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V647_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
