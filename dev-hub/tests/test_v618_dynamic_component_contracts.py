#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

dcc=loadmod("dcc",BIN/"dynamic_component_contracts.py")
mgr=loadmod("mgr",BIN/"component-role-contract-manager.py")

row={
  "package_id":"domain:graphics","branch_id":"project-x:graphics:primary","domain":"graphics",
  "decision":"MATERIALIZE_EPHEMERAL_BRANCH","runtime_required":True,
  "orchestrator_strategy":"DEDICATED_EPHEMERAL","architecture":{"preview":"ephemeral"},
}
branch=dcc.build_branch_contract(row=row,project_id="project-x",capabilities=["image-generation","layout-design"])
assert branch["schema"]=="chacha.dev/dynamic-component-role-contract/v1"
assert branch["component_kind"]=="branch"
assert branch["contract_id"]=="branch:project-x:graphics:primary"
assert branch["template_contract_id"]=="role:__branch__"
assert branch["issued_by"]=="branch-foundry"
assert branch["project_id"]=="project-x"
assert branch["domain"]=="graphics"
assert branch["package_id"]=="domain:graphics"
assert set(branch["allowed_capabilities"])=={"image-generation","layout-design"}
assert "workspace-write" in branch["allowed_permissions"]
assert "production-deploy" not in branch["allowed_permissions"]
assert branch["production_permissions_allowed"] is False

orch=dcc.build_orchestrator_contract(
  component_id="project-x:graphics:primary:orchestrator",
  project_id="project-x",domain="graphics",package_id="domain:graphics",
  capabilities=["image-generation","layout-design"],source="branch-foundry")
assert orch["component_kind"]=="orchestrator"
assert orch["contract_id"]=="orchestrator:project-x:graphics:primary:orchestrator"
assert orch["template_contract_id"]=="role:__dynamic-orchestrator__"
assert orch["issued_by"]=="branch-foundry"
assert "FINAL_ARCHITECTURE_DECISION" in orch["forbidden_actions"]

pre={"schema":"chacha.dev/domain-plan/v1","packages":[{
  "id":"domain:graphics","domain":"graphics","capabilities":["image-generation","layout-design"]
}]}
top={"schema":"chacha.dev/branch-topology/v1","project_id":"project-x","decisions":[row]}
cap={"schema":"chacha.dev/capability-foundry-plan/v1","plans":[]}
batch=mgr.collect(pre,top,cap)
assert len(batch)==2,batch
assert {x["component_kind"] for x in batch}=={"branch","orchestrator"}

# Memory-only branch must not create an execution contract.
top2={"schema":"chacha.dev/branch-topology/v1","project_id":"project-x","decisions":[{
  **row,"branch_id":"project-x:graphics:memory","decision":"MEMORY_ONLY","runtime_required":False,
  "orchestrator_strategy":"SHARED"
}]}
assert mgr.collect(pre,top2,cap)==[]

# Generated project-local domain orchestrator receives a contract even if strategy is shared.
top3={"schema":"chacha.dev/branch-topology/v1","project_id":"project-x","decisions":[{
  **row,"branch_id":"project-x:new-domain:primary","domain":"new-domain",
  "orchestrator_strategy":"SHARED"
}]}
pre3={"schema":"chacha.dev/domain-plan/v1","packages":[{
  "id":"domain:graphics","domain":"new-domain","capabilities":["novel-capability"]
}]}
cap3={"plans":[{"owner_domain":"new-domain","create_domain":True}]}
batch3=mgr.collect(pre3,top3,cap3)
assert {x["component_kind"] for x in batch3}=={"branch","orchestrator"},batch3
assert next(x for x in batch3 if x["component_kind"]=="orchestrator")["issued_by"]=="capability-foundry"

worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
for marker in [
  "/v1/dynamic-components/register",
  "dynamic_component_contracts",
  "DYNAMIC_COMPONENT_CONTRACT_NOT_FOUND",
  "CAPABILITY_OUTSIDE_COMPONENT_MISSION",
  "DYNAMIC_COMPONENT_PROJECT_SCOPE_MISMATCH",
  "dynamic_component_permission_escalation",
  "dynamic_component_production_permission_forbidden",
  "dynamic_component_policy_escalation_allowed:false"
]:
    assert marker in worker,marker

client=(BIN/"guardian-client.py").read_text(encoding="utf-8")
assert "register-component-contract" in client

runctl=(BIN/"run-controller.py").read_text(encoding="utf-8")
assert 'task.get("component_id")' in runctl
assert 'task.get("guardian_component_contract_id")' in runctl
assert 'task.get("guardian_component_contract_version")' in runctl

orchsrc=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"component-role-contract-manager.py":"component-contract-registry"' in orchsrc
assert 'component_contract_args+=["--register"]' in orchsrc
assert '"dynamic_component_contract_count"' in orchsrc

roles=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
ids={x["contract_id"] for x in roles["contracts"]}
assert "role:__branch__" in ids
assert "role:__dynamic-orchestrator__" in ids
assert "role:component-contract-registry" in ids
assert roles["principles"]["dynamic_component_contracts_cannot_escalate_template_privileges"] is True

coverage=json.load(open(CFG/"guardian-coverage-manifest.v1.json",encoding="utf-8"))
assert any(x["component_id"]=="component-contract-registry" for x in coverage["expected_components"])

print("CHACHA_DEV_V618_BRANCH_CONTRACT_DERIVATION=PASS")
print("CHACHA_DEV_V618_DYNAMIC_ORCHESTRATOR_CONTRACT_DERIVATION=PASS")
print("CHACHA_DEV_V618_MEMORY_ONLY_NO_RUNTIME_CONTRACT=PASS")
print("CHACHA_DEV_V618_PROJECT_LOCAL_ORCHESTRATOR_CONTRACT=PASS")
print("CHACHA_DEV_V618_GUARDIAN_COMPONENT_SCOPE_ENFORCEMENT=PASS")
print("CHACHA_DEV_V618_RUN_CONTROLLER_COMPONENT_CONTRACT_BINDING=PASS")
print("CHACHA_DEV_V618_NO_DYNAMIC_COMPONENT_PRIVILEGE_ESCALATION=PASS")
