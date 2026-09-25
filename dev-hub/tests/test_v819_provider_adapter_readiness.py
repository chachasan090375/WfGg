#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

runner=loadmod("v819_runner",ROOT/"dev-hub/bin/domain-factory-runner.py")
inspector=loadmod("v819_readiness",ROOT/"dev-hub/bin/provider-adapter-readiness.py")

with tempfile.TemporaryDirectory(prefix="v819-") as td:
    td=Path(td);planning=td/"planning";planning.mkdir();out=td/"factory"
    project="exec-project-v819"
    plan={
      "schema":"chacha.dev/domain-plan/v1",
      "packages":[{
        "id":"domain:product","kind":"primary","domain":"product","runtime_required":True,
        "branch_id":project+":product:primary","agent_id":"product-domain-architect",
        "capabilities":["requirements-analysis"]
      }]
    }
    council={"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True,"blocked":[]}
    contract={
      "schema":"chacha.dev/dynamic-component-role-contract/v1","component_kind":"branch",
      "contract_id":"branch:"+project+":product:primary","template_contract_id":"role:__branch__",
      "issued_by":"branch-foundry","component_id":project+":product:primary","project_id":project,
      "domain":"product","package_id":"domain:product",
      "allowed_actions":["INVOKE_COMPONENT","DISPATCH_TASK","REPORT_TASK_RESULT"],
      "forbidden_actions":["PRODUCTION_DEPLOY"],
      "allowed_permissions":["read","plan","workspace-write"],
      "allowed_capabilities":["requirements-analysis"],
      "production_permissions_allowed":False,"automatic_external_spend_eur":0,
      "version":"v1-test","contract_digest":"test"
    }
    components={"schema":"chacha.dev/dynamic-component-role-contract-batch/v1","contracts":[contract]}
    agents={"schema":"chacha.dev/dynamic-agent-role-contract-batch/v1","contracts":[]}
    for name,value in [
      ("final-plan.json",plan),("architecture-decision-council.json",council),
      ("component-role-contracts.json",components),("agent-role-contracts.json",agents)
    ]:
        (planning/name).write_text(json.dumps(value),encoding="utf-8")

    result=runner.build(ROOT,planning,out)
    assert result["status"]=="READY",result
    assert result["project_id"]==project,result
    graph=json.loads((out/"domain-execution-graph.json").read_text())
    assert graph["project"]==project,graph
    req=json.loads((out/"provider-health-requirements.json").read_text())
    assert req["project_id"]==project,req

    req2=td/"requirements.json"
    req2.write_text(json.dumps({
      "schema":"chacha.dev/provider-health-requirements/v1","project_id":project,
      "providers":[
        {"provider":"github-actions","capabilities":["ci"],"health_required":True},
        {"provider":"http-smoke","capabilities":["smoke-test-web"],"health_required":True},
        {"provider":"exa-mcp","capabilities":["web-research"],"health_required":True}
      ]
    }),encoding="utf-8")
    ready_path=td/"readiness.json"
    report=inspector.inspect(ROOT,req2,ready_path)
    by={x["provider"]:x for x in report["providers"]}
    assert by["github-actions"]["state"]=="HEALTH_PROBE_REQUIRED",by
    assert by["http-smoke"]["state"] in {"HEALTH_PROBE_REQUIRED","ADAPTER_EXECUTABLE_MISSING"},by
    assert by["exa-mcp"]["state"]=="PROVIDER_BINDING_MISSING",by
    assert report["next_stage"]=="PROVIDER_ADAPTER_BUILD_REQUIRED",report
    assert report["provider_health_not_inferred_from_adapter_presence"] is True

controller=(ROOT/"dev-hub/bin/central-interface-controller.py").read_text(encoding="utf-8")
for marker in [
  'prior_next=="PROVIDER_HEALTH_REQUIRED"',
  'provider-adapter-readiness.py',
  '"continuation_mode":"PROVIDER_ADAPTER_READINESS"',
  '"PROVIDER_ADAPTER_BUILD_REQUIRED"'
]:
    assert marker in controller,marker

print("CHACHA_DEV_V819_EXECUTION_PROJECT_ID_INFERRED=PASS")
print("CHACHA_DEV_V819_EXTERNAL_PROVIDER_HEALTH_PROBE=PASS")
print("CHACHA_DEV_V819_LOCAL_ADAPTER_READINESS_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V819_MISSING_PROVIDER_BINDING_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V819_HEALTH_NOT_INFERRED_FROM_ADAPTER=PASS")
print("CHACHA_DEV_V819_CONTINUE_NO_BOOTSTRAP_LOOP=PASS")
print("CHACHA_DEV_V819_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
