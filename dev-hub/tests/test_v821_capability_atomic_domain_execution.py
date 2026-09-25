#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

factory=loadmod("v821_factory",ROOT/"dev-hub/bin/domain-factory-runner.py")
ready=loadmod("v821_ready",ROOT/"dev-hub/bin/domain-toolchain-readiness.py")

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding="utf-8")

# Domain Factory: multi-capability packages must be decomposed into one task per runtime capability.
with tempfile.TemporaryDirectory(prefix="v821-factory-") as raw:
    base=Path(raw);planning=base/"planning";out=base/"out";planning.mkdir()
    project="v821-project"
    plan={
      "schema":"chacha.dev/domain-plan/v1","project_id":project,
      "packages":[
        {"id":"domain:product","kind":"primary","domain":"product","runtime_required":True,
         "branch_id":project+":product:primary","agent_id":"product-agent",
         "capabilities":["requirements-analysis","domain-modeling"]},
        {"id":"domain:conversation-interface","kind":"primary","domain":"conversation-interface","runtime_required":True,
         "branch_id":project+":conversation-interface:primary","agent_id":"conversation-interface-agent",
         "capabilities":["human-conversation-rendering"]},
        {"id":"domain:knowledge-research","kind":"primary","domain":"knowledge-research","runtime_required":True,
         "branch_id":project+":knowledge-research:primary","agent_id":"technology-watch-agent",
         "capabilities":["web-research"]}
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
    ]: write(planning/name,value)

    result=factory.build(ROOT,planning,out)
    assert result["status"]=="READY",result
    graph=json.loads((out/"domain-execution-graph.json").read_text())
    tasks=graph["tasks"]
    assert len(tasks)==2,tasks
    assert all(len(t["capabilities"])==1 for t in tasks),tasks
    assert {t["capabilities"][0] for t in tasks}=={"requirements-analysis","domain-modeling"},tasks
    assert all(t["kind"]=="domain-capability" for t in tasks)
    internal=graph["internal_work_items"]
    assert any(x.get("schema")=="chacha.dev/internal-domain-features/v1" and
               "human-conversation-rendering" in (x.get("features") or []) for x in internal),internal
    assert any(x.get("schema")=="chacha.dev/internal-domain-capability/v1" and
               x.get("capability")=="web-research" and x.get("provider")=="technology-radar"
               for x in internal),internal

# Readiness: optional agent tools do not block; candidate selection is capability-first.
with tempfile.TemporaryDirectory(prefix="v821-ready-") as raw:
    base=Path(raw);repo=base/"repo";planning=base/"planning";fac=base/"factory";out=base/"ready.json"
    cfg=repo/"dev-hub/config";binp=repo/"dev-hub/bin";binp.mkdir(parents=True)
    write(fac/"domain-execution-graph.json",{
      "schema":"chacha.dev/task-graph/v1","project":"p","tasks":[
        {"id":"cap:x","capabilities":["cap-x"],"metadata":{"package_id":"domain:x"}},
        {"id":"cap:y","capabilities":["cap-y"],"metadata":{"package_id":"domain:y"}}
      ]
    })
    write(planning/"agent-topology.json",{
      "schema":"chacha.dev/agent-topology/v1","decisions":[
        {"package_id":"domain:x","agent_id":"x-agent","manifest":{"tools":["optional-designed-provider"]}},
        {"package_id":"domain:y","agent_id":"y-agent","manifest":{"tools":[]}}
      ]
    })
    write(cfg/"capability-registry.v1.json",{
      "schema":"chacha.dev/capability-registry/v1","capabilities":{
        "cap-x":{"providers":[
          {"id":"p-designed","status":"ADOPT"},
          {"id":"p-ready","status":"PILOT"}
        ]},
        "cap-y":{"providers":[{"id":"p-needs-enable","status":"ADOPT"}]}
      }
    })
    write(cfg/"provider-adapters.v1.json",{
      "schema":"chacha.dev/provider-adapters/v1",
      "providers":{
        "p-designed":{"adapter":"a-designed","execution":"vps"},
        "p-ready":{"adapter":"a-ready","execution":"vps"},
        "p-needs-enable":{"adapter":"a-needs-enable","execution":"vps"},
        "optional-designed-provider":{"adapter":"a-optional","execution":"vps"}
      },
      "adapters":{
        "a-designed":{"status":"DESIGNED","executable":None},
        "a-ready":{"status":"ENABLED","executable":"/bin/true"},
        "a-needs-enable":{"status":"DESIGNED","executable":None},
        "a-optional":{"status":"DESIGNED","executable":None}
      }
    })
    write(cfg/"provider-health-probes.v1.json",{
      "schema":"chacha.dev/provider-health-probes/v1","providers":{
        "p-ready":{"probe":"runtime-command"}
      }
    })
    write(cfg/"domain-toolchain-semantics.v1.json",{
      "schema":"chacha.dev/domain-toolchain-semantics/v1","encapsulated_provider_tools":{}
    })
    r=ready.evaluate(repo,planning,fac,out)
    assert r["next_stage"]=="ADAPTER_ENABLEMENT_REQUIRED",r
    rows={x["task_id"]:x for x in r["tasks"]}
    assert rows["cap:x"]["selected_provider"]=="p-ready",rows["cap:x"]
    assert rows["cap:x"]["gate"]=="PROVIDER_HEALTH_PROBE_REQUIRED",rows["cap:x"]
    assert rows["cap:y"]["selected_provider"]=="p-needs-enable",rows["cap:y"]
    assert r["adapter_enablement_required"]==["p-needs-enable"],r
    assert "optional-designed-provider" not in r["adapter_enablement_required"],r

    # Any non-atomic scheduler task must fail closed before provider execution.
    write(fac/"domain-execution-graph.json",{
      "schema":"chacha.dev/task-graph/v1","project":"p","tasks":[
        {"id":"bad","capabilities":["cap-x","cap-y"],"metadata":{"package_id":"domain:x"}}
      ]
    })
    r2=ready.evaluate(repo,planning,fac,out)
    assert r2["next_stage"]=="TASK_GRAPH_DECOMPOSITION_REQUIRED",r2
    assert r2["graph_errors"],r2

print("CHACHA_DEV_V821_CAPABILITY_ATOMIC_TASKS=PASS")
print("CHACHA_DEV_V821_DOMAIN_FEATURES_STAY_INTERNAL=PASS")
print("CHACHA_DEV_V821_ENCAPSULATED_PROVIDER_STAYS_INTERNAL=PASS")
print("CHACHA_DEV_V821_OPTIONAL_AGENT_TOOL_NOT_BLOCKING=PASS")
print("CHACHA_DEV_V821_BEST_PROVIDER_PATH_SELECTED=PASS")
print("CHACHA_DEV_V821_MULTI_PROVIDER_TASK_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V821_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
