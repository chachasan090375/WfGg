#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

bridge=mod("acb_v626",BIN/"acceptance-confidence-bridge.py")
orch=mod("orch_v626",BIN/"autonomous-project-orchestrator.py")

with tempfile.TemporaryDirectory(prefix="v626-acceptance-confidence-") as td:
    td=Path(td)
    acceptance=td/"acceptance.json";lineage=td/"lineage.json"
    outbox=td/"outbox";state=td/"state";markers=td/"markers"
    result=td/"bridge-result.json"

    acceptance.write_text(json.dumps({
      "schema":"chacha.dev/acceptance-result/v1","accepted":True,"delivery_allowed":True,
      "criteria":[
        {"criterion_id":"functional","dimension":"functional","required":True,"owner":"graphics-agent","state":"PASS","evidence":"test"},
        {"criterion_id":"quality","dimension":"quality","required":True,"owner":"qa","state":"PASS","evidence":"test"}
      ],"return_to_factories":{}
    }),encoding="utf-8")
    lineage.write_text(json.dumps({
      "schema":"chacha.dev/component-lineage/v1",
      "components":[
        {"kind":"agent","component_id":"graphics-agent","version":"7"},
        {"kind":"branch","component_id":"graphics-primary","version":"3"}
      ]
    }),encoding="utf-8")

    policy=json.load(open(CFG/"acceptance-confidence.v1.json",encoding="utf-8"))
    a=json.load(open(acceptance,encoding="utf-8"));l=json.load(open(lineage,encoding="utf-8"))
    first=bridge.bridge(repo_root=ROOT,acceptance=a,lineage=l,project_id="p1",deployment_id="d1",
                        source_id="acceptance-confidence-bridge",policy=policy,
                        marker_root=markers,outbox_root=outbox,state_root=state)
    assert first["status"]=="QUEUED",first
    delta=json.load(open(first["outbox"],encoding="utf-8"))
    assert delta["evaluation"]["verified"] is True,delta
    assert delta["evaluation"]["outcome"]=="PASS",delta
    assert delta["lineage"]==l,delta
    assert delta["privacy"]["raw_user_content"] is False,delta

    second=bridge.bridge(repo_root=ROOT,acceptance=a,lineage=l,project_id="p1",deployment_id="d1",
                         source_id="acceptance-confidence-bridge",policy=policy,
                         marker_root=markers,outbox_root=outbox,state_root=state)
    assert second["status"]=="DEDUPLICATED",second
    assert second["delta_id"]==first["delta_id"],(first,second)
    assert len(list(outbox.glob("*.json")))==1,list(outbox.glob("*.json"))

    rejected={**a,"accepted":False,"delivery_allowed":False,
              "criteria":[{"criterion_id":"functional","required":True,"state":"FAIL","owner":"graphics-agent"}],
              "return_to_factories":{"graphics-agent":["functional"]}}
    skipped=bridge.bridge(repo_root=ROOT,acceptance=rejected,lineage=l,project_id="p2",deployment_id="d2",
                          source_id="acceptance-confidence-bridge",policy=policy,
                          marker_root=markers,outbox_root=outbox,state_root=state)
    assert skipped["status"]=="SKIPPED_NOT_ACCEPTED",skipped
    assert skipped["project_level_rejection_penalized_all_components"] is False,skipped
    assert len(list(outbox.glob("*.json")))==1,list(outbox.glob("*.json"))

    # Acceptance engine integration must invoke the bridge automatically when exact lineage is supplied.
    contract=td/"contract.json";evidence=td/"evidence.json";acceptance_out=td/"acceptance-engine-result.json";confidence_out=td/"confidence.json"
    contract.write_text(json.dumps({"criteria":[
      {"criterion_id":"functional","dimension":"functional","required":True,"owner":"graphics-agent"}
    ]}),encoding="utf-8")
    evidence.write_text(json.dumps({"criteria":[
      {"criterion_id":"functional","state":"PASS","evidence":"runtime-proof"}
    ]}),encoding="utf-8")
    p=subprocess.run([sys.executable,str(BIN/"acceptance-engine.py"),
      "--contract",str(contract),"--evidence",str(evidence),"--output",str(acceptance_out),
      "--component-lineage",str(lineage),"--confidence-project-id","p3","--confidence-deployment-id","d3",
      "--confidence-output",str(confidence_out),"--confidence-marker-root",str(td/"m3"),
      "--confidence-outbox-root",str(td/"o3"),"--confidence-state-root",str(td/"s3")],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    res=json.load(open(acceptance_out,encoding="utf-8"))
    assert res["accepted"] is True,res
    assert res["component_confidence_learning"]["status"]=="QUEUED",res
    assert "CHACHA_DEV_V626_ACCEPTANCE_TO_COMPONENT_CONFIDENCE=PASS" in p.stdout,p.stdout

    # Real orchestrator Guardian evidence must now include the V6.25 confidence advisor.
    council=td/"council.json"
    advisors={
      "technology-watch-pre":"PASS","technology-watch-final":"PASS","central-memory-assimilation":"PASS",
      "component-confidence":"PASS","central-memory-recall":"PASS","reuse-memory":"PASS",
      "architecture-memory":"PASS","architecture-portfolio":"PASS","branch-foundry":"PASS",
      "agent-foundry":"PASS","capability-foundry":"PASS","constraint-policy":"PASS"
    }
    council.write_text(json.dumps({"dispatch_allowed":True,"decisions":[{"mandatory_advisors":advisors}]}),encoding="utf-8")
    ev=orch._council_guardian_evidence(council)
    assert ev["component_confidence"] is True,ev
    assert ev["central_memory_assimilation"] is True,ev
    assert ev["central_memory_recall"] is True,ev

policy=json.load(open(CFG/"acceptance-confidence.v1.json",encoding="utf-8"))
assert policy["positive_learning"]["require_full_acceptance"] is True
assert policy["positive_learning"]["require_exact_component_lineage"] is True
assert policy["positive_learning"]["duplicate_acceptance_digest_is_idempotent"] is True
assert policy["negative_learning"]["project_level_rejection_does_not_penalize_all_components"] is True
assert policy["safety"]["technology_revalidation_required"] is True
assert policy["safety"]["architecture_council_final_authority"] is True
assert policy["economics"]["automatic_external_spend_eur"]==0

contracts=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
assert any(x["contract_id"]=="role:acceptance-confidence-bridge" for x in contracts["contracts"])
assert any(x["contract_id"]=="component:acceptance-confidence-bridge" for x in contracts["contracts"])
coverage=json.load(open(CFG/"guardian-coverage-manifest.v1.json",encoding="utf-8"))
assert any(x["component_id"]=="acceptance-confidence-bridge" for x in coverage["expected_components"])

print("CHACHA_DEV_V626_ACCEPTANCE_FULL_PASS_TO_CONFIDENCE=PASS")
print("CHACHA_DEV_V626_ACCEPTANCE_CONFIDENCE_IDEMPOTENCY=PASS")
print("CHACHA_DEV_V626_REJECTED_PROJECT_NO_BROAD_COMPONENT_PENALTY=PASS")
print("CHACHA_DEV_V626_ACCEPTANCE_ENGINE_AUTO_BRIDGE=PASS")
print("CHACHA_DEV_V626_REAL_ORCHESTRATOR_CONFIDENCE_GUARDIAN_EVIDENCE=PASS")
print("CHACHA_DEV_V626_TECHNOLOGY_REVALIDATION_REMAINS_REQUIRED=PASS")
print("CHACHA_DEV_V626_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
