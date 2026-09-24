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
adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v659-test"}

with tempfile.TemporaryDirectory(prefix="v659-operational-") as td:
    rt=Path(td)
    for i in (1,2):
        base=rt/"golden-path-runs"/f"run-{i}"/"external-assurance"
        rev=(str(i)*40)[:40];project_id=f"golden-{i}"
        guardian={
          "schema":"chacha.dev/guardian-functional-acceptance-receipt/v1",
          "receipt_id":f"guardian-{i}","project_id":project_id,"revision":rev,
          "contract_id":f"functional-{i}","contract_digest":"a"*64,"verdict":"PASS","severity":"INFO","reason_codes":[],
          "required_criteria_count":9,"passed_required_criteria_count":9,"directive_id":None,
          "original_functional_contract_pinned":True,"guardian":"external-worker","functional_scope_only":True,
          "direct_application_mutation":False,"central_orchestrator_owns_remediation":True,
          "assurance_exchange_delivery":{"status":"DELIVERED","transport":"SERVICE_BINDING","http_status":200},
          "checked_at":"2026-09-23T14:51:17Z"}
        sentinel={
          "schema":"chacha.dev/sentinel-technical-receipt/v1",
          "receipt_id":f"sentinel-{i}","project_id":project_id,"repository":"chachasan090375/WfGg","revision":rev,
          "workflow_name":"ChaCha DEV Sentinel technical assurance","workflow_run_id":str(1000+i),
          "verdict":"PASS","reason_codes":[],"audit_digest":"sha256:"+"b"*64,"advisory_count":0,"directive_id":None,
          "sentinel":"external-worker","technical_scope_only":True,"direct_code_mutation":False,
          "central_orchestrator_owns_remediation":True,
          "assurance_exchange_delivery":{"status":"DELIVERED","transport":"SERVICE_BINDING","http_status":200},
          "technical_verification_source":"D1_WORKFLOW_ATTESTATION","checked_at":"2026-09-23T14:51:18Z"}
        evref=f"/tmp/evidence-{i}.json#sha256:"+"c"*64
        acceptance={
          "schema":"chacha.dev/acceptance-result/v1","accepted":True,
          "criteria":[{"criterion_id":"main-flow","dimension":"functional","required":True,"owner":"product","state":"PASS","evidence":evref}],
          "return_to_factories":{},"delivery_allowed":True,"local_acceptance_candidate":True,
          "final_delivery_allowed":False,"final_delivery_gate":"seven-agent-final-compromise","final_delivery_receipt_required":True}
        acceptance_evidence={"criteria":[{"criterion_id":"main-flow","state":"PASS","evidence":evref}]}
        save(base/"guardian-functional-receipt.json",guardian)
        save(base/"sentinel-technical-receipt.json",sentinel)
        save(base/"acceptance.json",acceptance)
        save(base/"acceptance-evidence.json",acceptance_evidence)

    # Invalid self-like receipts must be ignored.
    bad=rt/"golden-path-runs"/"bad"/"external-assurance"
    save(bad/"guardian-functional-receipt.json",{"schema":"chacha.dev/guardian-functional-acceptance-receipt/v1","guardian":"internal","verdict":"PASS"})
    save(bad/"sentinel-technical-receipt.json",{"schema":"chacha.dev/sentinel-technical-receipt/v1","sentinel":"external-worker","technical_verification_source":"SELF","verdict":"PASS"})

    for aid in ("guardian","sentinel","acceptance-engineer"):
        raw=runner.run(aid,ROOT,"rev-v659",adapter_cfg)
        assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["production_truth_eligible"] is False,raw
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v659.json"
        pr=promoter.promote(raw,"rev-v659",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)

    metrics=afo.build_metrics(inv,rt,fleet_policy)
    for aid in ("guardian","sentinel"):
        sc=aec.score(aid,metrics[aid],evo);pl=aec.plan(aid,sc,evo)
        assert metrics[aid]["signals"]["operational_accuracy_evidence"]==2,(aid,metrics[aid]["signals"])
        assert metrics[aid]["signals"]["operational_structural_evidence"]==2,(aid,metrics[aid]["signals"])
        assert sc["production_measurement_coverage_pct"]==40.0,(aid,sc)
        assert sc["benchmark_measurement_coverage_pct"]==40.0,(aid,sc)
        assert sc["measurement_coverage_pct"]==80.0,(aid,sc)
        assert sc["production_weighted_maturity_pct"]==40.0,(aid,sc)
        assert set(sc["production_measured_dimensions"])=={"accuracy","authority_discipline","evidence_quality","handoff_quality"},(aid,sc)
        assert sc["evidence_maturity_label"]=="MIXED_EVIDENCE",(aid,sc)
        assert pl["evidence_maturity"]["candidate_evidence_mature"] is True,(aid,pl)
        assert pl["candidate"]["owner"] is None,(aid,pl)

    aid="acceptance-engineer";sc=aec.score(aid,metrics[aid],evo);pl=aec.plan(aid,sc,evo)
    assert metrics[aid]["signals"]["operational_accuracy_evidence"]==0,metrics[aid]["signals"]
    assert metrics[aid]["signals"]["operational_structural_evidence"]==2,metrics[aid]["signals"]
    assert sc["production_measurement_coverage_pct"]==30.0,sc
    assert sc["benchmark_measurement_coverage_pct"]==50.0,sc
    assert sc["measurement_coverage_pct"]==80.0,sc
    assert sc["production_weighted_maturity_pct"]==36.0,sc
    assert set(sc["production_measured_dimensions"])=={"authority_discipline","evidence_quality","handoff_quality"},sc
    assert sc["dimension_evidence"]["accuracy"].get("evidence_scope")=="BENCHMARK_ONLY",sc
    assert sc["evidence_maturity_label"]=="MIXED_EVIDENCE",sc
    assert pl["evidence_maturity"]["candidate_evidence_mature"] is False,pl
    assert pl["candidate"]["owner"] is None,pl

print("CHACHA_DEV_V659_GUARDIAN_EXTERNAL_PRODUCTION_EVIDENCE=PASS")
print("CHACHA_DEV_V659_SENTINEL_ATTESTED_PRODUCTION_EVIDENCE=PASS")
print("CHACHA_DEV_V659_ACCEPTANCE_STRUCTURAL_PRODUCTION_EVIDENCE=PASS")
print("CHACHA_DEV_V659_ACCEPTANCE_ACCURACY_INFERENCE=NO")
print("CHACHA_DEV_V659_PRODUCTION_PRECEDENCE=PASS")
print("CHACHA_DEV_V659_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED")
print("CHACHA_DEV_V659_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
