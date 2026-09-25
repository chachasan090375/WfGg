#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("v819",ROOT/"dev-hub/bin/domain-toolchain-readiness.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding="utf-8")

with tempfile.TemporaryDirectory(prefix="v819-toolchain-") as raw:
    base=Path(raw);repo=base/"repo";planning=base/"planning";factory=base/"factory";out=base/"out.json"
    cfg=repo/"dev-hub/config"
    graph={"schema":"chacha.dev/task-graph/v1","project":"p","tasks":[{
      "id":"package:domain:x","metadata":{"package_id":"domain:x"},"capabilities":[]
    }]}
    topo={"schema":"chacha.dev/agent-topology/v1","decisions":[{
      "package_id":"domain:x","agent_id":"x-agent",
      "manifest":{"tools":["internal-tool","provider-unbound","provider-designed","provider-enabled-no-probe","provider-enabled-probed"]}
    }]}
    registry={"schema":"chacha.dev/capability-registry/v1","capabilities":{
      "cap-x":{"providers":[{"id":"provider-unbound"},{"id":"provider-designed"},{"id":"provider-enabled-no-probe"},{"id":"provider-enabled-probed"}]}
    }}
    adapters={"schema":"chacha.dev/provider-adapters/v1",
      "providers":{
        "provider-designed":{"adapter":"a-designed"},
        "provider-enabled-no-probe":{"adapter":"a-no-probe"},
        "provider-enabled-probed":{"adapter":"a-probed"}
      },
      "adapters":{
        "a-designed":{"status":"DESIGNED","executable":None},
        "a-no-probe":{"status":"ENABLED","executable":"/bin/true"},
        "a-probed":{"status":"ENABLED","executable":"/bin/true"}
      }}
    probes={"schema":"chacha.dev/provider-health-probes/v1","providers":{
      "provider-enabled-probed":{"scope":"platform","probe":"runtime-command","functional_check":"test"}
    }}
    write(factory/"domain-execution-graph.json",graph);write(planning/"agent-topology.json",topo)
    write(cfg/"capability-registry.v1.json",registry);write(cfg/"provider-adapters.v1.json",adapters)
    write(cfg/"provider-health-probes.v1.json",probes)

    r=mod.evaluate(repo,planning,factory,out)
    assert r["next_stage"]=="PROVIDER_BINDING_REQUIRED",r
    assert r["provider_binding_required"]==["provider-unbound"]
    assert "internal-tool" in r["internal_tools"]
    assert r["provider_execution_started"] is False and r["adapter_invocation_started"] is False

    topo["decisions"][0]["manifest"]["tools"].remove("provider-unbound");write(planning/"agent-topology.json",topo)
    r=mod.evaluate(repo,planning,factory,out)
    assert r["next_stage"]=="ADAPTER_ENABLEMENT_REQUIRED",r
    assert r["adapter_enablement_required"]==["provider-designed"]

    adapters["adapters"]["a-designed"]={"status":"ENABLED","executable":"/bin/true"};write(cfg/"provider-adapters.v1.json",adapters)
    r=mod.evaluate(repo,planning,factory,out)
    assert r["next_stage"]=="PROVIDER_PROBE_DEFINITION_REQUIRED",r
    assert set(r["probe_definition_required"])=={"provider-designed","provider-enabled-no-probe"}

    probes["providers"]["provider-designed"]={"scope":"platform","probe":"runtime-command","functional_check":"test"}
    probes["providers"]["provider-enabled-no-probe"]={"scope":"platform","probe":"runtime-command","functional_check":"test"}
    write(cfg/"provider-health-probes.v1.json",probes)
    r=mod.evaluate(repo,planning,factory,out)
    assert r["next_stage"]=="PROVIDER_HEALTH_PROBE_REQUIRED",r
    assert set(r["health_probe_required"])=={"provider-designed","provider-enabled-no-probe","provider-enabled-probed"}

controller=(ROOT/"dev-hub/bin/central-interface-controller.py").read_text(encoding="utf-8")
for marker in [
  'prior_next=="PROVIDER_HEALTH_REQUIRED"',
  'domain-toolchain-readiness.py',
  '"continuation_mode":"DOMAIN_TOOLCHAIN_READINESS"',
  '"provider_execution_started":False',
  '"adapter_invocation_started":False'
]:
    assert marker in controller,marker

runner=(ROOT/"dev-hub/bin/domain-factory-runner.py").read_text(encoding="utf-8")
assert '"planning_dir":str(planning)' in runner
assert '"agent_topology":str(planning/"agent-topology.json")' in runner

print("CHACHA_DEV_V819_INTERNAL_TOOL_NOT_PROVIDER=PASS")
print("CHACHA_DEV_V819_PROVIDER_BINDING_GATE=PASS")
print("CHACHA_DEV_V819_ADAPTER_ENABLEMENT_GATE=PASS")
print("CHACHA_DEV_V819_PROBE_DEFINITION_GATE=PASS")
print("CHACHA_DEV_V819_HEALTH_PROBE_GATE=PASS")
print("CHACHA_DEV_V819_CONTINUE_NO_BOOTSTRAP_LOOP=PASS")
print("CHACHA_DEV_V819_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
