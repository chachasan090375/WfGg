#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))

cfg=load(CFG/"agent-benchmark-adapters.v1.json");evo=load(CFG/"agent-evolution.v1.json")
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v653-test"}

previous=["guardian","sentinel","bastion","autonomous-recovery-agent","security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer"]
third=["agent-foundry-architect","branch-foundry-architect","capability-foundry-architect","logician","technology-watch-agent"]
assert set(previous+third)<=set(cfg["supported_agents"]),cfg["supported_agents"].keys()
assert cfg["evidence"]["independent_oracle_id"]=="v653-independent-benchmark-oracle"
assert evo["measurement"]["minimum_keep_dimension_coverage_pct"]==100

with tempfile.TemporaryDirectory(prefix="v653-third-wave-") as td:
    rt=Path(td)
    for aid in previous+third:
        raw=runner.run(aid,ROOT,"rev-v653",cfg)
        assert raw["verifier"]=="v653-independent-benchmark-oracle",(aid,raw["verifier"])
        assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["production_truth_eligible"] is False,raw
        assert raw["dimensions"]["coverage"]==100.0,(aid,raw["dimensions"])
        assert raw["dimensions"]["handoff_quality"]==100.0,(aid,raw["dimensions"])
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v653.json"
        pr=promoter.promote(raw,"rev-v653",cfg,path);assert pr["promoted"] is True,(aid,pr)

    metrics=afo.build_metrics(inv,rt,fleet_policy)
    for aid in previous:
        sc=aec.score(aid,metrics[aid],evo)
        assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
        assert sc["benchmark_measurement_coverage_pct"]>=80.0,(aid,sc)
        assert sc["production_measurement_coverage_pct"]<=20.0,(aid,sc)
        pl=aec.plan(aid,sc,evo)
        assert pl["evidence_maturity"]["benchmark_only_cannot_materialize_candidate"] is True,pl
        if pl["evidence_maturity"]["candidate_requested"]:
            assert pl["candidate"]["owner"] is None and pl["evidence_maturity"]["candidate_evidence_mature"] is False,pl

    for aid in third:
        sc=aec.score(aid,metrics[aid],evo)
        assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
        assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)

    for aid in ["agent-foundry-architect","branch-foundry-architect","capability-foundry-architect","technology-watch-agent"]:
        assert metrics[aid]["dimensions"]["learning_quality"]["status"]=="MEASURED",(aid,metrics[aid]["dimensions"]["learning_quality"])
    assert metrics["technology-watch-agent"]["dimensions"]["calibration"]["status"]=="MEASURED",metrics["technology-watch-agent"]["dimensions"]["calibration"]

    # No benchmark-only scorecard can materialize a candidate without production maturity.
    synthetic={"dimensions":{d:{"status":"MEASURED","value":100.0,"evidence_scope":"BENCHMARK_ONLY"} for d in aec.DIMENSIONS},
      "dimension_evidence":{d:{"status":"MEASURED","value":100.0,"evidence_scope":"BENCHMARK_ONLY"} for d in aec.DIMENSIONS}}
    sc=aec.score("benchmark-only-perfect",synthetic,evo);pl=aec.plan("benchmark-only-perfect",sc,evo)
    assert sc["measurement_coverage_pct"]==100.0 and sc["production_measurement_coverage_pct"]==0.0,sc
    assert pl["candidate"]["owner"] is None and pl["evidence_maturity"]["candidate_evidence_mature"] is False,pl
    assert sc["recommendation"]=="MEASURE_REAL_WORLD",sc
    assert pl["measurement_required"] is True,pl

print("CHACHA_DEV_V653_BENCHMARK_ONLY_KEEP=BLOCKED")
print("CHACHA_DEV_V653_BENCHMARK_CONTRACT_COVERAGE=PASS")
print("CHACHA_DEV_V653_BENCHMARK_HANDOFF_QUALITY=PASS")
print("CHACHA_DEV_V653_AGENT_FOUNDRY_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V653_BRANCH_FOUNDRY_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V653_CAPABILITY_FOUNDRY_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V653_LOGICIAN_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V653_TECHNOLOGY_WATCH_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V653_FOUNDRY_LEARNING_QUALITY=PASS")
print("CHACHA_DEV_V653_TECHNOLOGY_WATCH_CALIBRATION=PASS")
print("CHACHA_DEV_V653_PREVIOUS_NINE_COVERAGE_80=PASS")
print("CHACHA_DEV_V653_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED")
print("CHACHA_DEV_V653_PRODUCTION_MEASUREMENT_PRECEDENCE=PRESERVED")
print("CHACHA_DEV_V653_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
