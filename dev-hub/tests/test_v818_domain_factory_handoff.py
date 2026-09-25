#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

runner=loadmod("v818_runner",ROOT/"dev-hub/bin/domain-factory-runner.py")

with tempfile.TemporaryDirectory(prefix="v818-domain-factory-") as td:
    td=Path(td);planning=td/"planning";out=td/"out";planning.mkdir()
    project="test-domain-factory"
    plan={
      "schema":"chacha.dev/domain-plan/v1","project_id":project,
      "packages":[
        {"id":"domain:product","kind":"primary","domain":"product","runtime_required":True,
         "branch_id":project+":product:primary","agent_id":"product-domain-architect",
         "capabilities":["requirements-analysis"]},
        {"id":"domain:conversation-interface","kind":"primary","domain":"conversation-interface","runtime_required":True,
         "branch_id":project+":conversation-interface:primary","agent_id":"conversation-interface-agent",
         "capabilities":["human-conversation-rendering"]}
      ]
    }
    council={"schema":"chacha.dev/architecture-decision-council/v1","project_id":project,
             "dispatch_allowed":True,"blocked":[]}
    contracts=[]
    for pkg in plan["packages"]:
        contracts.append({
          "schema":"chacha.dev/dynamic-component-role-contract/v1",
          "component_kind":"branch","contract_id":"branch:"+pkg["branch_id"],
          "template_contract_id":"role:__branch__","issued_by":"branch-foundry",
          "component_id":pkg["branch_id"],"project_id":project,
          "domain":pkg["domain"],"package_id":pkg["id"],
          "allowed_actions":["INVOKE_COMPONENT","DISPATCH_TASK","REPORT_TASK_RESULT"],
          "forbidden_actions":["PRODUCTION_DEPLOY"],
          "allowed_permissions":["read","plan","workspace-write"],
          "allowed_capabilities":pkg["capabilities"],
          "production_permissions_allowed":False,
          "automatic_external_spend_eur":0,
          "version":"v1-test","contract_digest":"deadbeef"
        })
    components={"schema":"chacha.dev/dynamic-component-role-contract-batch/v1","project_id":project,"contracts":contracts}
    agents={"schema":"chacha.dev/dynamic-agent-role-contract-batch/v1","project_id":project,"contracts":[]}
    for name,value in [
      ("final-plan.json",plan),("architecture-decision-council.json",council),
      ("component-role-contracts.json",components),("agent-role-contracts.json",agents)
    ]:
        (planning/name).write_text(json.dumps(value),encoding="utf-8")

    result=runner.build(ROOT,planning,out)
    assert result["status"]=="READY",result
    assert result["package_count"]==2 and result["ready_package_count"]==2,result
    graph=json.loads((out/"domain-execution-graph.json").read_text())
    tasks={x["id"]:x for x in graph["tasks"]}
    assert tasks["package:domain:product"]["capabilities"]==["requirements-analysis"]
    conv=tasks["package:domain:conversation-interface"]
    assert conv["capabilities"]==[],conv
    assert conv["metadata"]["domain_features"]==["human-conversation-rendering"],conv

    req=json.loads((out/"provider-health-requirements.json").read_text())
    providers={x["provider"]:x for x in req["providers"]}
    assert "chacha-dev-architect" in providers,providers
    assert "human-conversation-rendering" not in json.dumps(req),req

    rec=json.loads((out/"contract-reconciliation.json").read_text())
    assert rec["assembly_allowed"] is True,rec

controller=(ROOT/"dev-hub/bin/central-interface-controller.py").read_text(encoding="utf-8")
for marker in [
  'prior_next=="DOMAIN_FACTORIES"',
  'domain-factory-runner.py',
  '"continuation_mode":"DOMAIN_FACTORY_HANDOFF"',
  '"domain_factories_completed":True',
  '"PROVIDER_HEALTH_REQUIRED"'
]:
    assert marker in controller,marker

print("CHACHA_DEV_V818_DOMAIN_PACKAGES_MATERIALIZED=PASS")
print("CHACHA_DEV_V818_DYNAMIC_CONTRACTS_RECONCILED=PASS")
print("CHACHA_DEV_V818_DOMAIN_FEATURE_NOT_RUNTIME_PROVIDER=PASS")
print("CHACHA_DEV_V818_PROVIDER_HEALTH_GATE_PRESERVED=PASS")
print("CHACHA_DEV_V818_CONTINUE_NO_BOOTSTRAP_LOOP=PASS")
print("CHACHA_DEV_V818_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
