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
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");evo=load(CFG/"agent-evolution.v1.json")
adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json");domains=load(CFG/"domain-orchestration.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35

visual=["graphics-specialist","animation-specialist","ui-layout-specialist","translation-specialist","publication-specialist"]
targets=visual+["technology-radar-agent"]
assert domains["domains"]["ui-layout"]["roles"]==["ui-layout-specialist"],domains["domains"]["ui-layout"]
assert "development" in domains["domains"]["ui-layout"]["reviews"],domains["domains"]["ui-layout"]
assert project["agents"][0]["agent_id"]=="technology-radar-agent"
assert project["agents"][0]["scope"]=="PROJECT_ONLY" and project["agents"][0]["central_brain_role"] is False
assert routing["scope_exclusions"]["technology-radar-agent"]["scope"]=="PROJECT_ONLY"
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v658-test"}

with tempfile.TemporaryDirectory(prefix="v658-specialists-") as td:
    rt=Path(td)
    # Real-shape project-local adapter promotion evidence: structural production truth only.
    promotion={
      "schema":"chacha.dev/adapter-promotion-evidence/v1","adapter":"radar-runtime-adapter",
      "observed_at":"2026-09-18T18:52:59Z","evidence":{
        "runtime-contract-pass":{"status":"PASS","source":"github-actions:test:contract","observed_at":"2026-09-18T18:52:59Z",
          "details":{"contract_status":"SUCCESS","offline_contract_tests":"PASS"}},
        "sandbox-only":{"status":"PASS","source":"github-actions:test:sandbox","observed_at":"2026-09-18T18:52:59Z",
          "details":{"production_radar_mutation":"NO","registry_mutation":"NO","radar_sentinel_guard":"PASS","collector_sentinel_guard":"PASS"}},
        "provisioning-pass":{"status":"PASS","source":"adapter-provisioning-receipt:test","observed_at":"2026-09-18T18:52:59Z",
          "details":{"probe_status":"PASS","source_digest":"sha256:"+"a"*64,"installed_digest":"sha256:"+"a"*64}}
      }}
    save(rt/"adapter-promotions/radar-runtime-adapter/20260918T185259Z/promotion-evidence.json",promotion)

    for aid in targets:
        raw=runner.run(aid,ROOT,"rev-v658",adapter_cfg)
        assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["production_truth_eligible"] is False,raw
        assert raw["canonical_observation_bus_writes"] is False and raw["automatic_external_spend_eur"]==0,raw
        assert raw["oracle_complete"] is True,(aid,raw)
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v658.json"
        pr=promoter.promote(raw,"rev-v658",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)

    metrics=afo.build_metrics(inv,rt,fleet_policy)
    for aid in visual:
        sc=aec.score(aid,metrics[aid],evo);pl=aec.plan(aid,sc,evo)
        assert sc["production_measurement_coverage_pct"]==0.0,(aid,sc)
        assert sc["benchmark_measurement_coverage_pct"]==80.0,(aid,sc)
        assert sc["measurement_coverage_pct"]==80.0,(aid,sc)
        assert sc["production_weighted_maturity_pct"]==24.0,(aid,sc)
        assert sc["evidence_maturity_label"]=="BENCHMARK_HEAVY",(aid,sc)
        assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)
        assert pl["evidence_maturity"]["candidate_evidence_mature"] is False and pl["candidate"]["owner"] is None,(aid,pl)

    radar=metrics["technology-radar-agent"];sc=aec.score("technology-radar-agent",radar,evo);pl=aec.plan("technology-radar-agent",sc,evo)
    assert radar["signals"]["project_adapter_evidence"]==1,radar["signals"]
    assert sc["production_measurement_coverage_pct"]==20.0,sc
    assert sc["benchmark_measurement_coverage_pct"]==60.0,sc
    assert sc["measurement_coverage_pct"]==80.0,sc
    assert sc["production_weighted_maturity_pct"]==32.0,sc
    assert set(sc["production_measured_dimensions"])=={"authority_discipline","evidence_quality"},sc
    assert sc["evidence_maturity_label"]=="BENCHMARK_HEAVY",sc
    assert sc["recommendation"]!="MEASURE_FIRST",sc
    assert pl["evidence_maturity"]["candidate_evidence_mature"] is False and pl["candidate"]["owner"] is None,pl

print("CHACHA_DEV_V658_GRAPHICS_EXECUTABLE_CONTRACT=PASS")
print("CHACHA_DEV_V658_ANIMATION_EXECUTABLE_CONTRACT=PASS")
print("CHACHA_DEV_V658_UI_LAYOUT_ROLE_ALIGNMENT=PASS")
print("CHACHA_DEV_V658_TRANSLATION_EXECUTABLE_CONTRACT=PASS")
print("CHACHA_DEV_V658_PUBLICATION_EXECUTABLE_CONTRACT=PASS")
print("CHACHA_DEV_V658_PROJECT_LOCAL_RADAR_READONLY_ADAPTER=PASS")
print("CHACHA_DEV_V658_RADAR_STRUCTURAL_PRODUCTION_EVIDENCE=PASS")
print("CHACHA_DEV_V658_RADAR_ACCURACY_FROM_PROMOTION=NO")
print("CHACHA_DEV_V658_PLATFORM_ROUTING_FOR_RADAR=FORBIDDEN")
print("CHACHA_DEV_V658_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED")
print("CHACHA_DEV_V658_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
