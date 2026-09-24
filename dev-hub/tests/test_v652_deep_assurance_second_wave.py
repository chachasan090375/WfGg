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

cfg=load(CFG/"agent-benchmark-adapters.v1.json")
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");evo=load(CFG/"agent-evolution.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35

priority=["guardian","sentinel","bastion","autonomous-recovery-agent"]
second=["security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer"]
all_agents=priority+second
assert set(all_agents).issubset(set(cfg["supported_agents"])),cfg["supported_agents"].keys()
assert cfg["evidence"]["independent_oracle_id"]=="v652-independent-benchmark-oracle"

runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v652-test"}

with tempfile.TemporaryDirectory(prefix="v652-deep-bench-") as td:
    rt=Path(td)
    promoted={}
    for aid in all_agents:
        raw=runner.run(aid,ROOT,"rev-v652",cfg)
        assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["production_truth_eligible"] is False,raw
        assert raw["verification"]=="BENCHMARK_VERIFIED" and raw["verifier"]=="v652-independent-benchmark-oracle",raw
        assert raw["repeat_count"]==2 and raw["deep_calibration"] is True,raw
        assert raw["canonical_observation_bus_writes"] is False and raw["automatic_external_spend_eur"]==0,raw
        for d in ["accuracy","robustness","authority_discipline","evidence_quality","drift_resistance","efficiency"]:
            assert d in raw["dimensions"],(aid,d,raw["dimensions"])
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v652.json"
        pr=promoter.promote(raw,"rev-v652",cfg,path);assert pr["promoted"] is True,(aid,pr)
        assert pr["evidence"].get("promoted_at"),pr
        promoted[aid]=pr["evidence"]

    # Fleet Observatory uses V6.52 promoted evidence and keeps it BENCHMARK_ONLY.
    metrics=afo.build_metrics(inv,rt,fleet_policy)
    for aid in all_agents:
        m=metrics[aid]
        for d in ["accuracy","robustness","authority_discipline","evidence_quality","drift_resistance","efficiency"]:
            assert m["dimensions"][d]["status"]=="MEASURED",(aid,d,m["dimensions"][d])
            assert m["dimensions"][d].get("evidence_scope")=="BENCHMARK_ONLY",(aid,d,m["dimensions"][d])
        sc=aec.score(aid,m,evo)
        assert sc["measurement_coverage_pct"]>=60.0,(aid,sc)
        assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)

    # Campaign runner supports the whole first + second wave; unsupported remains non-failure.
    camp={"contracts":[{"agent_id":x} for x in all_agents+["graphics-specialist"]]}
    run=campaign_runner.execute(camp,ROOT,rt,"rev-v652",cfg)
    assert run["promoted_count"]==9,run
    assert any(x["agent_id"]=="graphics-specialist" and x["status"]=="NO_EXECUTABLE_ADAPTER" for x in run["results"]),run

    # Explicit oracle identity is now a hard gate.
    bad=dict(promoted["guardian"]);bad["schema"]="chacha.dev/agent-benchmark-raw-evidence/v1";bad["verifier"]="other-oracle"
    blocked=promoter.promote(bad,"rev-v652",cfg,rt/"bad-oracle.json")
    assert blocked["promoted"] is False and "INDEPENDENT_ORACLE" in blocked["reason_codes"],blocked

    # Freshest promoted evidence wins among benchmark revisions, but production still has precedence.
    older=dict(promoted["guardian"]);older["promoted_at"]="2026-09-23T00:00:00Z";older["dimensions"]=dict(older["dimensions"]);older["dimensions"]["drift_resistance"]=0.0
    newer=dict(promoted["guardian"]);newer["promoted_at"]="2026-09-24T23:59:59Z";newer["dimensions"]=dict(newer["dimensions"]);newer["dimensions"]["drift_resistance"]=100.0
    p1=rt/"agent-evolution/benchmark-evidence/guardian/older.json";p2=rt/"agent-evolution/benchmark-evidence/guardian/newer.json"
    p1.write_text(json.dumps(older)+"\n");p2.write_text(json.dumps(newer)+"\n")
    refreshed=afo.build_metrics(inv,rt,fleet_policy)["guardian"]
    assert refreshed["dimensions"]["drift_resistance"]["value"]==100.0,refreshed["dimensions"]["drift_resistance"]

    stale=runner.run("guardian",ROOT,"rev-stale",cfg);stale["technology_watch"]={"state":"STALE","fresh":False}
    sb=promoter.promote(stale,"rev-stale",cfg,rt/"stale.json")
    assert sb["promoted"] is False and "TECHNOLOGY_WATCH_NOT_FRESH" in sb["reason_codes"],sb

print("CHACHA_DEV_V652_PRIORITY_AGENT_DEEP_CALIBRATION=PASS")
print("CHACHA_DEV_V652_SECURITY_REVIEWER_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V652_RECOVERY_ENGINEER_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V652_PLATFORM_CLOUD_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V652_DATA_ARCHITECT_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V652_RELEASE_ENGINEER_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V652_DRIFT_RESISTANCE_MEASURED=PASS")
print("CHACHA_DEV_V652_EFFICIENCY_MEASURED=PASS")
print("CHACHA_DEV_V652_MEASUREMENT_COVERAGE_60=PASS")
print("CHACHA_DEV_V652_EXPLICIT_ORACLE_IDENTITY_GATE=PASS")
print("CHACHA_DEV_V652_LATEST_PROMOTED_BENCHMARK_SELECTION=PASS")
print("CHACHA_DEV_V652_PRODUCTION_TRUTH=NO")
print("CHACHA_DEV_V652_CANONICAL_OBSERVATION_BUS_WRITE=NO")
print("CHACHA_DEV_V652_UNSUPPORTED_AGENT_IS_FAILURE=NO")
print("CHACHA_DEV_V652_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
