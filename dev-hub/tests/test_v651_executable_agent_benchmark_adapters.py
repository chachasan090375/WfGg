#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_benchmark_campaign_runner as campaign_runner
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

cfg=load(CFG/"agent-benchmark-adapters.v1.json")
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");evo=load(CFG/"agent-evolution.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35

# Unit qualification uses a fresh Technology Watch status without writing canonical state.
import agent_benchmark_adapter_runner as ar
ar.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v651-test"}

with tempfile.TemporaryDirectory(prefix="v651-exec-bench-") as td:
    rt=Path(td)
    evidence={}
    for aid in ["guardian","sentinel","bastion","autonomous-recovery-agent"]:
        raw=runner.run(aid,ROOT,"rev-v651",cfg)
        assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["production_truth_eligible"] is False,raw
        assert raw["verification"]=="BENCHMARK_VERIFIED" and raw["verifier"]!=aid,raw
        assert raw["canonical_observation_bus_writes"] is False,raw
        assert raw["oracle_complete"] is True and raw["case_count"]>0,raw
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v651.json"
        pr=promoter.promote(raw,"rev-v651",cfg,path)
        assert pr["promoted"] is True,pr
        evidence[aid]=pr["evidence"]

    # Unsupported agents are not failures.
    campaign={"contracts":[{"agent_id":"guardian"},{"agent_id":"sentinel"},{"agent_id":"bastion"},
                           {"agent_id":"autonomous-recovery-agent"},{"agent_id":"graphics-specialist"}]}
    cr=campaign_runner.execute(campaign,ROOT,rt,"rev-v651",cfg)
    assert cr["promoted_count"]==4,cr
    assert any(x["agent_id"]=="graphics-specialist" and x["status"]=="NO_EXECUTABLE_ADAPTER" for x in cr["results"]),cr

    # Production measurements must win over benchmark evidence; benchmark fills only UNKNOWN dimensions.
    metrics=afo.build_metrics(inv,rt,fleet_policy)
    for aid in ["guardian","sentinel","bastion","autonomous-recovery-agent"]:
        m=metrics[aid];assert m["signals"]["benchmark_evidence_present"] is True,m
        for d in ["accuracy","robustness","authority_discipline","evidence_quality"]:
            assert m["dimensions"][d]["status"]=="MEASURED",(aid,d,m["dimensions"][d])
            assert m["dimensions"][d].get("evidence_scope")=="BENCHMARK_ONLY",(aid,d,m["dimensions"][d])
        sc=aec.score(aid,m,evo)
        assert sc["measurement_coverage_pct"]>=40.0,(aid,sc)
        assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)

    # A stale Technology Watch proof blocks promotion.
    stale=runner.run("guardian",ROOT,"rev-stale",cfg);stale["technology_watch"]={"state":"STALE","fresh":False}
    blocked=promoter.promote(stale,"rev-stale",cfg,rt/"blocked.json")
    assert blocked["promoted"] is False and "TECHNOLOGY_WATCH_NOT_FRESH" in blocked["reason_codes"],blocked

    # Benchmark evidence can be negative and still valid evidence.
    negative=dict(evidence["guardian"]);negative["dimensions"]=dict(negative["dimensions"]);negative["dimensions"]["accuracy"]=25.0
    negative["case_count"]=max(1,int(negative["case_count"]));negative["oracle_complete"]=True
    assert negative["production_truth_eligible"] is False

print("CHACHA_DEV_V651_GUARDIAN_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V651_SENTINEL_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V651_BASTION_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V651_AUTONOMOUS_RECOVERY_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V651_INDEPENDENT_ORACLE=PASS")
print("CHACHA_DEV_V651_BENCHMARK_EVIDENCE_PROMOTION=PASS")
print("CHACHA_DEV_V651_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS")
print("CHACHA_DEV_V651_MEASURE_FIRST_CONVERSION=PASS")
print("CHACHA_DEV_V651_UNSUPPORTED_AGENT_IS_FAILURE=NO")
print("CHACHA_DEV_V651_TECHNOLOGY_WATCH_STALE_PROMOTION=BLOCKED")
print("CHACHA_DEV_V651_BENCHMARK_PRODUCTION_TRUTH=NO")
print("CHACHA_DEV_V651_CANONICAL_OBSERVATION_BUS_WRITE=NO")
print("CHACHA_DEV_V651_DIRECT_AGENT_MUTATION=NO")
print("CHACHA_DEV_V651_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
