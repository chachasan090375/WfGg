#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("v820",ROOT/"dev-hub/bin/domain-toolchain-readiness.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding="utf-8")

with tempfile.TemporaryDirectory(prefix="v820-encap-") as raw:
    base=Path(raw);repo=base/"repo";planning=base/"planning";factory=base/"factory";out=base/"out.json"
    cfg=repo/"dev-hub/config";binp=repo/"dev-hub/bin"
    write(factory/"domain-execution-graph.json",{
      "schema":"chacha.dev/task-graph/v1","project":"p","tasks":[{
        "id":"package:domain:x","metadata":{"package_id":"domain:x"},"capabilities":[]
      }]
    })
    write(planning/"agent-topology.json",{
      "schema":"chacha.dev/agent-topology/v1","decisions":[{
        "package_id":"domain:x","agent_id":"x-agent",
        "manifest":{"tools":["technology-radar","exa-mcp","direct-provider"]}
      }]
    })
    write(cfg/"capability-registry.v1.json",{
      "schema":"chacha.dev/capability-registry/v1",
      "capabilities":{"x":{"providers":[{"id":"technology-radar"},{"id":"exa-mcp"},{"id":"direct-provider"}]}}
    })
    write(cfg/"provider-adapters.v1.json",{
      "schema":"chacha.dev/provider-adapters/v1",
      "providers":{"direct-provider":{"adapter":"direct-adapter"}},
      "adapters":{"direct-adapter":{"status":"DESIGNED","executable":None}}
    })
    write(cfg/"provider-health-probes.v1.json",{
      "schema":"chacha.dev/provider-health-probes/v1","providers":{"direct-provider":{"probe":"runtime-command"}}
    })
    semantics={
      "schema":"chacha.dev/domain-toolchain-semantics/v1",
      "encapsulated_provider_tools":{
        "technology-radar":{"owner_component":"technology-watch-service",
          "evidence":["dev-hub/bin/technology-radar.py"]},
        "exa-mcp":{"owner_component":"technology-watch-public-corroboration",
          "evidence":["dev-hub/bin/public-corroboration.py"]}
      }
    }
    write(cfg/"domain-toolchain-semantics.v1.json",semantics)
    binp.mkdir(parents=True,exist_ok=True)
    (binp/"technology-radar.py").write_text("# proof\n",encoding="utf-8")
    (binp/"public-corroboration.py").write_text("# proof\n",encoding="utf-8")

    r=mod.evaluate(repo,planning,factory,out)
    assert r["next_stage"]=="ADAPTER_ENABLEMENT_REQUIRED",r
    assert set(r["encapsulated_providers"])=={"technology-radar","exa-mcp"},r
    assert not r["provider_binding_required"],r
    assert r["adapter_enablement_required"]==["direct-provider"],r

    (binp/"public-corroboration.py").unlink()
    r=mod.evaluate(repo,planning,factory,out)
    assert r["next_stage"]=="ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED",r
    assert r["encapsulated_provider_evidence_required"]==["exa-mcp"],r
    assert r["provider_execution_started"] is False
    assert r["adapter_invocation_started"] is False

prod=json.loads((ROOT/"dev-hub/config/domain-toolchain-semantics.v1.json").read_text(encoding="utf-8"))
assert prod["schema"]=="chacha.dev/domain-toolchain-semantics/v1"
assert prod["encapsulated_provider_tools"]["technology-radar"]["direct_adapter_required"] is False
assert prod["encapsulated_provider_tools"]["exa-mcp"]["direct_adapter_required"] is False

print("CHACHA_DEV_V820_TECHNOLOGY_RADAR_ENCAPSULATED=PASS")
print("CHACHA_DEV_V820_EXA_MCP_ENCAPSULATED=PASS")
print("CHACHA_DEV_V820_DIRECT_BINDING_NOT_REQUIRED=PASS")
print("CHACHA_DEV_V820_OWNER_EVIDENCE_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V820_DIRECT_PROVIDER_GATE_PRESERVED=PASS")
print("CHACHA_DEV_V820_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
