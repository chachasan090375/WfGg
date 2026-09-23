#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")

binder=loadmod("v628_binder",BIN/"task-contract-binder.py")
runctl=loadmod("v628_runctl",BIN/"run-controller.py")
ec=loadmod("v628_evidence",BIN/"evidence-collector.py")
import trusted_dispatch_learning as tdl

roles=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
agent_contract={
  "schema":"chacha.dev/dynamic-agent-role-contract/v1",
  "contract_id":"agent:p628:graphics:agent","version":"v1-agent628",
  "template_contract_id":"role:__agent__","agent_id":"p628:graphics:agent",
  "project_id":"p628","domain":"graphics","package_id":"domain:graphics",
  "allowed_capabilities":["image-generation"]
}
branch_contract={
  "schema":"chacha.dev/dynamic-component-role-contract/v1","component_kind":"branch",
  "contract_id":"branch:p628:graphics:primary","version":"v1-branch628",
  "template_contract_id":"role:__branch__","component_id":"p628:graphics:primary",
  "project_id":"p628","domain":"graphics","package_id":"domain:graphics",
  "allowed_capabilities":["layout-design"]
}
graph={
  "schema":"chacha.dev/task-graph/v1","project":"p628","transition":"BUILD->VERIFY",
  "tasks":[
    {"id":"task:agent","kind":"artifact","owner_role":"p628:graphics:agent",
     "capabilities":["image-generation"],"permission":"read","depends_on":[],
     "outputs":[{"type":"artifact","id":"test-result"}],
     "verification":{"mode":"machine","self_certification_allowed":False}},
    {"id":"task:branch","kind":"artifact","owner_role":"p628:graphics:primary",
     "capabilities":["layout-design"],"permission":"read","depends_on":[],
     "outputs":[],"verification":{"mode":"machine","self_certification_allowed":False}},
    {"id":"task:foundry","kind":"artifact","owner_role":"agent-foundry",
     "capabilities":[],"permission":"read","depends_on":[],
     "outputs":[],"verification":{"mode":"machine","self_certification_allowed":False}}
  ]
}
bound=binder.bind_graph(graph,{"contracts":[agent_contract]},{"contracts":[branch_contract]},roles)
a=bound["tasks"][0]["guardian_binding"];b=bound["tasks"][1]["guardian_binding"];f=bound["tasks"][2]["guardian_binding"]
assert a["subject_kind"]=="agent",a
assert b["subject_kind"]=="branch",b
assert f["subject_kind"]=="foundry",f
assert a["policy_contract_version"]==str(roles.get("version") or ""),a

adapters={
  "schema":"chacha.dev/provider-adapters/v1",
  "providers":{"p1":{"adapter":"connector-a","kind":"connector","execution":"vps"}},
  "adapters":{"connector-a":{"status":"ENABLED","executable":"/bin/true","supports":["read"]}}
}
pb={"capability":"image-generation","provider":"p1","fallback_used":False,"health_state":"HEALTHY"}
binding,errors=runctl.adapter_binding(pb,"read",adapters,True)
assert not errors,errors
assert binding and str(binding["binding_version"]).startswith("sha256:"),binding
assert runctl.learning_adapter_kind("connector")=="connector"
assert runctl.learning_adapter_kind("local-runtime")=="runtime"

scheduled={
  "project":"p628","transition":"BUILD->VERIFY","permission":"read","resource_class":"light",
  "requires_storage_preflight":False,"metadata":{}
}
envelope=runctl.prepare_envelope("run-v628",1,scheduled,bound["tasks"][0],[binding],{
  "approvals":{"explicit_human_permissions":[]},"dispatch":{"default_timeout_seconds":300,"max_timeout_seconds":3600}
},None)
ctx=envelope.get("learning_context")
assert ctx and ctx["schema"]=="chacha.dev/verified-evidence-learning-context/v1",ctx
rows=ctx["component_lineage"]["components"]
assert any(x["kind"]=="agent" and x["component_id"]=="p628:graphics:agent" for x in rows),rows
assert any(x["kind"]=="connector" and x["component_id"]=="connector-a" for x in rows),rows
assert ctx["deployment_id"]=="run-v628:task:agent",ctx

raw={
  "schema":"chacha.dev/task-result/v1","project":"p628","task_id":"task:agent","status":"OK",
  "producer":"connector-a","observed_at":"2026-09-23T00:00:00Z",
  "evidence":[{"kind":"report","source":"runtime-proof","digest":"sha256:"+"1"*64}],
  "verification":{"status":"UNVERIFIED","method":"none","verifier":"pending"},
  "outputs":[{"type":"artifact","id":"test-result","status":"OK"}]
}
parsed,err=runctl.parse_adapter_result(json.dumps(raw).encode(),envelope,"connector-a")
assert err is None and parsed is not None,(parsed,err)
forged=json.loads(json.dumps(raw))
forged["learning_context"]={"schema":"chacha.dev/verified-evidence-learning-context/v1"}
_,err=runctl.parse_adapter_result(json.dumps(forged).encode(),envelope,"connector-a")
assert err=="ADAPTER_LEARNING_CONTEXT_FORBIDDEN",err

with tempfile.TemporaryDirectory(prefix="v628-trusted-dispatch-") as td:
    td=Path(td);run=td/"run-v628";results=run/"results";envelopes=run/"envelopes"
    source=results/"task_agent.task-result.json";envp=envelopes/"task_agent.json"
    save(source,raw);save(envp,envelope)
    verified=json.loads(json.dumps(raw))
    verified["verification"]={"status":"VERIFIED","method":"machine","verifier":"independent","observed_at":"2026-09-23T00:01:00Z"}
    verified["learning_context"]={
      "schema":"chacha.dev/verified-evidence-learning-context/v1",
      "deployment_id":"forged","source_id":"forged","surface_kind":"forged",
      "component_lineage":{"schema":"chacha.dev/component-lineage/v1","components":[
        {"kind":"agent","component_id":"someone-else","version":"999"}]}
    }
    enriched,status,located=tdl.enrich_verified_result(
      verified=verified,source_result_path=source,graph=bound,adapters=adapters)
    assert status=="TRUSTED_DISPATCH_CONTEXT",status
    assert located==envp,(located,envp)
    assert enriched["learning_context"]==ctx,enriched
    assert enriched["learning_context"]["deployment_id"]!="forged"

    ledger=ec.init_ledger("p628")
    try:
        ec.ingest(bound,ledger,enriched)
        raise AssertionError("learning context without trusted dispatch proof was accepted")
    except SystemExit as exc:
        assert "TRUSTED_LEARNING_CONTEXT_PROOF_REQUIRED" in str(exc),exc
    updated=ec.ingest(bound,ledger,enriched,envp,adapters)
    event=updated["history"][-1]
    assert event["verification_status"]=="VERIFIED",event
    assert event["learning_eligibility"]=="EXACT_LINEAGE",event
    assert event["learning_context"]==ctx,event

    noenv=td/"external-result.json";save(noenv,raw)
    external_verified=json.loads(json.dumps(verified))
    external_verified["learning_context"]["deployment_id"]="provider-forged"
    stripped,status2,located2=tdl.enrich_verified_result(
      verified=external_verified,source_result_path=noenv,graph=bound,adapters=adapters)
    assert status2=="NO_DISPATCH_ENVELOPE",status2
    assert located2 is None
    assert "learning_context" not in stripped,stripped

cfg=json.load(open(CFG/"run-controller.v1.json",encoding="utf-8"))
assert cfg["principles"]["trusted_learning_lineage_is_controller_owned"] is True
assert cfg["principles"]["provider_cannot_self_assign_learning_context"] is True
assert cfg["verification"]["trusted_dispatch_context_attached_only_after_independent_verification"] is True

pc=json.load(open(CFG/"project-control.v1.json",encoding="utf-8"))
assert pc["principles"]["learning_lineage_is_derived_from_trusted_dispatch"] is True
assert pc["principles"]["untrusted_provider_learning_context_is_never_ingested"] is True

print("CHACHA_DEV_V628_DYNAMIC_AGENT_LINEAGE_DERIVED=PASS")
print("CHACHA_DEV_V628_DYNAMIC_BRANCH_LINEAGE_DERIVED=PASS")
print("CHACHA_DEV_V628_FOUNDRY_LINEAGE_DERIVED=PASS")
print("CHACHA_DEV_V628_CONNECTOR_LINEAGE_CONTENT_ADDRESSED=PASS")
print("CHACHA_DEV_V628_PROVIDER_SELF_ATTRIBUTION_BLOCKED=PASS")
print("CHACHA_DEV_V628_VERIFIED_RESULT_TRUSTED_CONTEXT_INJECTION=PASS")
print("CHACHA_DEV_V628_EVIDENCE_INGEST_REQUIRES_TRUSTED_PROOF=PASS")
print("CHACHA_DEV_V628_EXTERNAL_RESULT_FORGED_CONTEXT_STRIPPED=PASS")
print("CHACHA_DEV_V628_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
