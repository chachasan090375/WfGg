#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

binder=loadmod("taskbinder",BIN/"task-contract-binder.py")
sched=loadmod("sched",BIN/"execution-scheduler.py")
runctl=loadmod("runctl",BIN/"run-controller.py")

agent_contract={
  "schema":"chacha.dev/dynamic-agent-role-contract/v1",
  "contract_id":"agent:project-x:graphics:ephemeral-agent","version":"v1-agent123456",
  "template_contract_id":"role:__agent__","agent_id":"project-x:graphics:ephemeral-agent",
  "project_id":"project-x","domain":"graphics","package_id":"domain:graphics",
  "allowed_capabilities":["image-generation","layout-design"]
}
branch_contract={
  "schema":"chacha.dev/dynamic-component-role-contract/v1","component_kind":"branch",
  "contract_id":"branch:project-x:graphics:primary","version":"v1-branch123456",
  "template_contract_id":"role:__branch__","component_id":"project-x:graphics:primary",
  "project_id":"project-x","domain":"graphics","package_id":"domain:graphics",
  "allowed_capabilities":["image-generation","layout-design"]
}
graph={
  "schema":"chacha.dev/task-graph/v1","project":"project-x","transition":"DESIGN->IMPLEMENTATION",
  "tasks":[
    {"id":"task:agent","kind":"artifact","owner_role":"project-x:graphics:ephemeral-agent",
     "capabilities":["image-generation"],"permission":"workspace-write","depends_on":[],"outputs":[],
     "verification":{"mode":"machine","self_certification_allowed":False}},
    {"id":"task:branch","kind":"artifact","owner_role":"project-x:graphics:primary",
     "capabilities":["layout-design"],"permission":"workspace-write","depends_on":[],"outputs":[],
     "verification":{"mode":"machine","self_certification_allowed":False}},
    {"id":"task:static","kind":"gate","owner_role":"qa",
     "capabilities":[],"permission":"read","depends_on":["task:agent","task:branch"],"outputs":[],
     "verification":{"mode":"independent-agent","self_certification_allowed":False}}
  ]
}
roles=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
bound=binder.bind_graph(graph,{"contracts":[agent_contract]},{"contracts":[branch_contract]},roles)
assert bound["guardian_binding"]["all_tasks_bound"] is True,bound
assert bound["guardian_binding"]["blocked_task_count"]==0,bound
assert bound["guardian_binding"]["dynamic_task_count"]==2,bound
a=bound["tasks"][0]["guardian_binding"];b=bound["tasks"][1]["guardian_binding"];s=bound["tasks"][2]["guardian_binding"]
assert a["mode"]=="DYNAMIC_AGENT" and a["dynamic_contract_id"]==agent_contract["contract_id"],a
assert b["mode"]=="DYNAMIC_COMPONENT" and b["dynamic_contract_id"]==branch_contract["contract_id"],b
assert s["mode"]=="STATIC_ROLE" and s["policy_contract_ref"],s

registry={"schema":"chacha.dev/capability-registry/v1","capabilities":{
  "image-generation":{"providers":[{"id":"p1","status":"ADOPT"}]},
  "layout-design":{"providers":[{"id":"p1","status":"ADOPT"}]}
}}
health={"schema":"chacha.dev/provider-health-snapshot/v1","providers":{"p1":{"state":"HEALTHY"}}}
policy={"schema":"chacha.dev/execution-scheduler/v1","provider_selection":{"allow_unknown":False,"allow_degraded_for_non_production":False},
        "resource_classes":{},"failover":{},"concurrency":{"max_parallel_read_tasks":8,"serialize_permissions":[]}}
prepared,blocked=sched.prepare_tasks(bound,registry,health,policy)
assert not blocked,blocked
assert prepared["task:agent"]["guardian_binding"]["binding_digest"]==a["binding_digest"]
assert prepared["task:branch"]["guardian_binding"]["binding_digest"]==b["binding_digest"]

assert runctl.guardian_binding_errors(bound["tasks"][0],prepared["task:agent"],True)==[]
tampered=dict(prepared["task:agent"])
tampered["guardian_binding"]=dict(tampered["guardian_binding"]);tampered["guardian_binding"]["domain"]="other"
assert "TASK_GUARDIAN_BINDING_DRIFT" in runctl.guardian_binding_errors(bound["tasks"][0],tampered,True)

bad=json.loads(json.dumps(bound["tasks"][0]))
bad["guardian_binding"]["binding_digest"]="sha256:deadbeef"
assert "TASK_GUARDIAN_BINDING_DIGEST_INVALID" in runctl.guardian_binding_errors(bad,prepared["task:agent"],True)

worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
for marker in [
  "TASK_GUARDIAN_BINDING_DIGEST_MISSING",
  "TASK_GUARDIAN_POLICY_CONTRACT_DRIFT",
  "task_contract_leases",
  "TASK_CONTRACT_IDENTITY_DRIFT",
  "task_contract_binding_protocol:true",
  "task_contract_identity_lease:true"
]:
    assert marker in worker,marker

cfg=json.load(open(CFG/"run-controller.v1.json",encoding="utf-8"))
assert cfg["guardian"]["task_contract_binding_required_in_execute_mode"] is True
assert cfg["principles"]["task_guardian_binding_digest_must_match_graph_and_plan"] is True

print("CHACHA_DEV_V619_EVERY_TASK_BOUND_TO_GUARDIAN_CONTRACT=PASS")
print("CHACHA_DEV_V619_DYNAMIC_AGENT_TASK_BINDING=PASS")
print("CHACHA_DEV_V619_DYNAMIC_COMPONENT_TASK_BINDING=PASS")
print("CHACHA_DEV_V619_STATIC_ROLE_TASK_BINDING=PASS")
print("CHACHA_DEV_V619_SCHEDULER_PRESERVES_BINDING=PASS")
print("CHACHA_DEV_V619_RUN_CONTROLLER_BINDING_DRIFT_BLOCK=PASS")
print("CHACHA_DEV_V619_BINDING_DIGEST_INTEGRITY=PASS")
print("CHACHA_DEV_V619_EXTERNAL_GUARDIAN_PRE_POST_CONTRACT_IDENTITY=PASS")
