#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

arc=loadmod("arc",BIN/"agent_role_contracts.py")
planner=loadmod("planner",BIN/"agent-foundry-planner.py")

pkg={
  "id":"domain:graphics","domain":"graphics","kind":"primary",
  "roles":[],"capabilities":["image-generation","layout-design"],"toolchain":["image-tool"]
}
cfg=json.load(open(CFG/"agent-foundry.v1.json",encoding="utf-8"))
decision=planner.decide_package(pkg,{"roles":{}},cfg,"v617-project")
assert decision["decision"]=="CREATE_EPHEMERAL_AGENT",decision
manifest=decision["manifest"]
contract=manifest["guardian_role_contract"]
assert contract["schema"]=="chacha.dev/dynamic-agent-role-contract/v1"
assert contract["contract_id"]=="agent:"+decision["agent_id"]
assert contract["version"].startswith("v1-")
assert contract["template_contract_id"]=="role:__agent__"
assert contract["issued_by"]=="agent-foundry"
assert contract["project_id"]=="v617-project"
assert contract["domain"]=="graphics"
assert set(contract["allowed_capabilities"])=={"image-generation","layout-design"}
assert "workspace-write" in contract["allowed_permissions"]
assert "production-deploy" not in contract["allowed_permissions"]
assert contract["production_permissions_allowed"] is False

# Content-addressed versioning must be deterministic and change with mission.
same=arc.build_contract(
  agent_id=decision["agent_id"],project_id="v617-project",domain="graphics",package_id="domain:graphics",
  capabilities=["layout-design","image-generation"],tools=["image-tool"],scope="project")
assert same["version"]==contract["version"],(same,contract)
changed=arc.build_contract(
  agent_id=decision["agent_id"],project_id="v617-project",domain="graphics",package_id="domain:graphics",
  capabilities=["layout-design","image-generation","animation"],tools=["image-tool"],scope="project")
assert changed["version"]!=contract["version"]

# Batch manager must discover exactly the generated contract without external registration in CI.
with tempfile.TemporaryDirectory(prefix="chacha-v617-") as td:
    td=Path(td)
    topology={"schema":"chacha.dev/agent-topology/v1","project_id":"v617-project","decisions":[decision]}
    top=td/"topology.json";top.write_text(json.dumps(topology),encoding="utf-8")
    out=td/"contracts.json"
    p=subprocess.run(["python3",str(BIN/"agent-role-contract-manager.py"),"--agent-topology",str(top),"--output",str(out)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    batch=json.load(open(out))
    assert batch["contract_count"]==1,batch
    assert batch["contracts"][0]["version"]==contract["version"],batch

worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
for marker in [
  "/v1/dynamic-contracts/register",
  "dynamic_role_contracts",
  "DYNAMIC_AGENT_CONTRACT_REQUIRED",
  "DYNAMIC_AGENT_CONTRACT_NOT_FOUND",
  "CAPABILITY_OUTSIDE_AGENT_MISSION",
  "DYNAMIC_AGENT_PROJECT_SCOPE_MISMATCH",
  "dynamic_contract_permission_escalation",
  "dynamic_contract_production_permission_forbidden"
]:
    assert marker in worker,marker

runctl=(BIN/"run-controller.py").read_text(encoding="utf-8")
assert '"subject_contract_id": task.get("guardian_contract_id")' in runctl
assert '"subject_contract_version": task.get("guardian_contract_version")' in runctl
assert '"capabilities": [str(x) for x in (task.get("capabilities") or [])]' in runctl

orch=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"agent-role-contract-manager.py":"agent-contract-registry"' in orch
assert 'contract_args+=["--register"]' in orch
assert '"dynamic_agent_contract_count"' in orch

roles=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
assert any(x["contract_id"]=="role:agent-contract-registry" for x in roles["contracts"])
assert roles["principles"]["dynamic_instance_contracts_cannot_escalate_template_privileges"] is True

print("CHACHA_DEV_V617_AGENT_FOUNDRY_ISSUES_PRECISE_CONTRACT=PASS")
print("CHACHA_DEV_V617_CONTENT_ADDRESSED_CONTRACT_VERSIONING=PASS")
print("CHACHA_DEV_V617_DYNAMIC_CONTRACT_MANAGER=PASS")
print("CHACHA_DEV_V617_GUARDIAN_MISSION_SCOPE_ENFORCEMENT=PASS")
print("CHACHA_DEV_V617_NO_DYNAMIC_PRIVILEGE_ESCALATION=PASS")
print("CHACHA_DEV_V617_RUN_CONTROLLER_EXACT_CONTRACT_ENFORCEMENT=PASS")
