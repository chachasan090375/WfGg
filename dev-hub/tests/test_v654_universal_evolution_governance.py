#!/usr/bin/env python3
from __future__ import annotations
import json,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_fleet_observatory as afo
import agent_evolution_controller as aec
import agent_evolution_profile as aep
import agent_observation_bus_health as aobh

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");evo=load(CFG/"agent-evolution.v1.json")
adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json");profile_policy=load(CFG/"agent-evolution-profile.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v654-test"}

fourth=["acceptance-engineer","contract-integrator","integration-architect","ergonomist"]
with tempfile.TemporaryDirectory(prefix="v654-profile-") as td:
    rt=Path(td)
    # Fourth wave real adapters.
    for aid in fourth:
        raw=runner.run(aid,ROOT,"rev-v654",adapter_cfg)
        assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["production_truth_eligible"] is False,(aid,raw)
        assert raw["verification"]=="BENCHMARK_VERIFIED",(aid,raw)
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v654.json"
        pr=promoter.promote(raw,"rev-v654",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)
    report=afo.build_report(ROOT,rt,fleet_policy,evo,routing,seven,[project])
    for aid in fourth:
        row=next(x for x in report["agents"] if x["agent_id"]==aid)
        assert row["scorecard"]["measurement_coverage_pct"]>=80.0,(aid,row["scorecard"])
        assert row["scorecard"]["production_measurement_coverage_pct"]==0.0,(aid,row["scorecard"])
        assert row["plan"]["evidence_maturity"]["candidate_evidence_mature"] is False,(aid,row["plan"])
        assert row["plan"]["candidate"]["owner"] is None,(aid,row["plan"])
    # Universal lightweight profiles cover every inventory member without inventing a score.
    idx=aep.build_index(report,routing,seven,[project],adapter_cfg,evo,profile_policy)
    assert idx["profile_count"]==35,idx["profile_count"]
    assert idx["profile_is_performance_score"] is False
    assert all(p["profile_is_performance_score"] is False for p in idx["profiles"])
    assert all(p["evolution"]["active_self_mutation"] is False and p["evolution"]["self_promotion"] is False for p in idx["profiles"])
    byid={p["identity"]["agent_id"]:p for p in idx["profiles"]}
    assert byid["curator"]["measurement"]["strategy"]=="PROFILE_ONLY",byid["curator"]
    assert byid["intendant"]["measurement"]["strategy"]=="PROFILE_ONLY",byid["intendant"]
    radar=byid["technology-radar-agent"]
    assert radar["identity"]["scope"]=="PROJECT" and radar["evolution"]["scope"]=="PROJECT_LOCAL",radar
    assert radar["evolution"]["platform_global_promotion_forbidden"] is True,radar
    assert byid["technology-watch-agent"]["measurement"]["next_action"]=="RUN_EXECUTABLE_BENCHMARK",byid["technology-watch-agent"]
    outroot=rt/"agent-evolution/profiles";aep.write_profiles(outroot,idx)
    assert (outroot/"index.json").is_file()
    # Bus health fingerprints the profile policy and must request reassessment if that policy later changes.
    minrepo=rt/"repo";shutil.copytree(ROOT/"dev-hub/config",minrepo/"dev-hub/config")
    (minrepo/"dev-hub/projects/wfgg-radar").mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json",minrepo/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
    buspolicy=load(CFG/"agent-observation-bus.v1.json");state=rt/"bus-state.json";health=rt/"bus-health.json"
    first=aobh.assess(minrepo,rt/"bus-runtime",buspolicy,state,health,False)
    assert first["status"]=="PASS",first
    pp=minrepo/"dev-hub/config/agent-evolution-profile.v1.json";pv=load(pp);pv["version"]="1.0.1-test";pp.write_text(json.dumps(pv)+"\n")
    second=aobh.assess(minrepo,rt/"bus-runtime",buspolicy,state,health,False)
    assert second["status"]=="REASSESS_REQUIRED",second
    assert "AGENT_EVOLUTION_PROFILE_POLICY_CHANGED" in (load(Path(second["reassessment"]["path"]))["trigger_reasons"]),second

print("CHACHA_DEV_V654_UNIVERSAL_PROFILE_35=PASS")
print("CHACHA_DEV_V654_PROFILE_IS_PERFORMANCE_SCORE=NO")
print("CHACHA_DEV_V654_PROJECT_RADAR_SCOPE=PROJECT_LOCAL")
print("CHACHA_DEV_V654_CURATOR_INTENDANT_PROFILE_ONLY=PASS")
print("CHACHA_DEV_V654_ACCEPTANCE_ENGINEER_ADAPTER=PASS")
print("CHACHA_DEV_V654_CONTRACT_INTEGRATOR_ADAPTER=PASS")
print("CHACHA_DEV_V654_INTEGRATION_ARCHITECT_ADAPTER=PASS")
print("CHACHA_DEV_V654_ERGONOMIST_ADAPTER=PASS")
print("CHACHA_DEV_V654_FOURTH_WAVE_CANDIDATE_MATERIALIZATION=BLOCKED")
print("CHACHA_DEV_V654_BUS_PROFILE_POLICY_REASSESSMENT=PASS")
print("CHACHA_DEV_V654_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
