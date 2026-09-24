#!/usr/bin/env python3
from __future__ import annotations
import hashlib,importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")
def stable(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def sha_text(x):return hashlib.sha256(x.encode()).hexdigest()
def sha_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

att=loadmod("v660_attestor",BIN/"independent-accuracy-attestor.py")
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
policy=load(CFG/"agent-fleet-observatory.v1.json");evo=load(CFG/"agent-evolution.v1.json")
adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v660-test"}

with tempfile.TemporaryDirectory(prefix="v660-accuracy-") as td:
    rt=Path(td);ghdir=rt/"github";ghdir.mkdir(parents=True)
    sentinel_runs=[]
    for i in (1,2,3):
        run=rt/"golden-path-runs"/f"run-{i}";planning=run/"planning";ext=run/"external-assurance";mat=run/"materialization/evidence"
        planning.mkdir(parents=True);ext.mkdir(parents=True);mat.mkdir(parents=True)
        evidence_file=mat/"main-flow.json";evidence_file.write_text(json.dumps({"run":i,"status":"PASS"},sort_keys=True)+"\n")
        eref=str(evidence_file)+"#sha256:"+sha_file(evidence_file)
        contract={
          "schema":"chacha.dev/functional-contract/v1","contract_id":f"functional-{i}",
          "criteria":[{"criterion_id":"main-flow","dimension":"functional","required":True,"owner":"product","verification":"evidence"}]
        }
        acceptance_evidence={"criteria":[{"criterion_id":"main-flow","state":"PASS","evidence":eref}]}
        acceptance={
          "schema":"chacha.dev/acceptance-result/v1","accepted":True,
          "criteria":[{"criterion_id":"main-flow","dimension":"functional","required":True,"owner":"product","state":"PASS","evidence":eref}],
          "return_to_factories":{},"delivery_allowed":True,"local_acceptance_candidate":True,
          "final_delivery_allowed":False,"final_delivery_gate":"seven-agent-final-compromise","final_delivery_receipt_required":True
        }
        rev=f"{i:040x}";project_id=f"golden-{i}";digest=sha_text(stable(contract))
        guardian={
          "schema":"chacha.dev/guardian-functional-acceptance-receipt/v1","receipt_id":f"guardian-{i}",
          "project_id":project_id,"revision":rev,"contract_id":contract["contract_id"],"contract_digest":digest,
          "verdict":"PASS","severity":"INFO","reason_codes":[],"required_criteria_count":1,"passed_required_criteria_count":1,
          "directive_id":None,"original_functional_contract_pinned":True,"guardian":"external-worker",
          "functional_scope_only":True,"direct_application_mutation":False,"central_orchestrator_owns_remediation":True,
          "assurance_exchange_delivery":{"status":"DELIVERED","transport":"SERVICE_BINDING","http_status":200}
        }
        save(planning/"functional-contract.json",contract);save(ext/"acceptance-evidence.json",acceptance_evidence)
        save(ext/"acceptance.json",acceptance);save(ext/"guardian-functional-receipt.json",guardian)
        if i<=2:
            run_id=str(1000+i)
            sentinel={
              "schema":"chacha.dev/sentinel-technical-receipt/v1","receipt_id":f"sentinel-{i}","project_id":project_id,
              "repository":"chachasan090375/WfGg","revision":rev,"workflow_name":"ChaCha DEV Sentinel technical assurance",
              "workflow_run_id":run_id,"workflow_url":"","verdict":"PASS","reason_codes":[],
              "audit_digest":"sha256:"+"b"*64,"advisory_count":0,"directive_id":None,"sentinel":"external-worker",
              "technical_scope_only":True,"direct_code_mutation":False,"central_orchestrator_owns_remediation":True,
              "assurance_exchange_delivery":{"status":"DELIVERED","transport":"SERVICE_BINDING","http_status":200},
              "technical_verification_source":"D1_WORKFLOW_ATTESTATION"
            }
            gh={"id":int(run_id),"name":"ChaCha DEV Sentinel technical assurance","head_sha":rev,
                "status":"completed","conclusion":"success","repository":{"full_name":"chachasan090375/WfGg"}}
            save(ext/"sentinel-technical-receipt.json",sentinel);save(ghdir/(run_id+".json"),gh);sentinel_runs.append(run)

    # Independent attestor must reject a GitHub run that does not bind to the receipt revision.
    bad_dir=rt/"bad-github";bad_dir.mkdir()
    bad=load(ghdir/"1001.json");bad["head_sha"]="f"*40;save(bad_dir/"1001.json",bad)
    bad_run=rt/"golden-path-runs"/"run-1"
    assert (bad_run/"external-assurance/sentinel-technical-receipt.json").is_file()
    assert (bad_dir/"1001.json").is_file()
    bad_case=att.sentinel_case(bad_run,bad_dir,False,rt/"bad-sources")
    assert bad_case is not None,{"receipt":load(bad_run/"external-assurance/sentinel-technical-receipt.json"),"github_files":[p.name for p in bad_dir.iterdir()]}
    assert bad_case["passed"] is False,bad_case

    outroot=rt/"agent-evolution/independent-accuracy-attestations/v660-test"
    attestations=att.build(rt,outroot,ghdir,False)
    assert attestations["guardian"]["case_count"]==3 and attestations["guardian"]["passed_case_count"]==3,attestations["guardian"]
    assert attestations["sentinel"]["case_count"]==2 and attestations["sentinel"]["passed_case_count"]==2,attestations["sentinel"]
    assert attestations["acceptance-engineer"]["case_count"]==3 and attestations["acceptance-engineer"]["passed_case_count"]==3,attestations["acceptance-engineer"]
    for aid,x in attestations.items():
        assert x["accuracy_value"]==100.0,(aid,x)
        assert x["production_truth_eligible"] is True and x["decision_authority"] is False,(aid,x)
        assert x["direct_mutation"] is False and x["canonical_observation_bus_mutation"] is False,(aid,x)

    for aid in ("guardian","sentinel","acceptance-engineer"):
        raw=runner.run(aid,ROOT,"rev-v660",adapter_cfg)
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v660.json"
        pr=promoter.promote(raw,"rev-v660",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)

    metrics=afo.build_metrics(inv,rt,policy)
    expected_cases={"guardian":3,"sentinel":2,"acceptance-engineer":3}
    for aid,n in expected_cases.items():
        m=metrics[aid];sc=aec.score(aid,m,evo);pl=aec.plan(aid,sc,evo)
        assert m["signals"]["operational_accuracy_evidence"]==0,(aid,m["signals"])
        assert m["signals"]["independent_accuracy_attestation_present"] is True,(aid,m["signals"])
        assert m["signals"]["independent_accuracy_attestation_cases"]==n,(aid,m["signals"])
        assert sc["production_measurement_coverage_pct"]==40.0,(aid,sc)
        assert sc["benchmark_measurement_coverage_pct"]==40.0,(aid,sc)
        assert sc["measurement_coverage_pct"]==80.0,(aid,sc)
        assert sc["production_weighted_maturity_pct"]==40.0,(aid,sc)
        assert set(sc["production_measured_dimensions"])=={"accuracy","authority_discipline","evidence_quality","handoff_quality"},(aid,sc)
        assert sc["dimension_evidence"]["accuracy"].get("evidence_scope") is None,(aid,sc)
        assert sc["dimensions"]["accuracy"]==100,(aid,sc)
        assert pl["evidence_maturity"]["candidate_evidence_mature"] is True,(aid,pl)
        assert pl["self_evolution"]["active_self_mutation"] is False and pl["self_evolution"]["self_promotion"] is False,(aid,pl)
        assert pl["assurance"]["architecture_council_final_authority"] is True,(aid,pl)
        if pl["candidate"]["owner"] is not None:
            assert pl["candidate"]["owner"]=="agent-foundry" and pl["candidate"]["isolated"] is True,(aid,pl)

print("CHACHA_DEV_V660_GUARDIAN_INDEPENDENT_ACCURACY=PASS")
print("CHACHA_DEV_V660_SENTINEL_GITHUB_INDEPENDENT_ACCURACY=PASS")
print("CHACHA_DEV_V660_ACCEPTANCE_RECOMPUTED_ACCURACY=PASS")
print("CHACHA_DEV_V660_PRODUCTION_ACCURACY_DIMENSIONS=3")
print("CHACHA_DEV_V660_SELF_MUTATION=NO")
print("CHACHA_DEV_V660_SELF_PROMOTION=NO")
print("CHACHA_DEV_V660_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V660_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
