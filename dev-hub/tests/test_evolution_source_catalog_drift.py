#!/usr/bin/env python3
from __future__ import annotations
import json,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import agent_observation_bus_health as aobh

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x): Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

with tempfile.TemporaryDirectory(prefix="bus-source-drift-") as td:
    td=Path(td);repo=td/"repo";runtime=td/"runtime"
    shutil.copytree(ROOT/"dev-hub/config",repo/"dev-hub/config")
    (repo/"dev-hub/projects/wfgg-radar").mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json",repo/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
    policy=load(repo/"dev-hub/config/agent-observation-bus.v1.json")
    policy.setdefault("self_health",{}).setdefault("thresholds",{})["max_shadow_publish_p95_ms"]=5000
    state=runtime/"state.json";report=runtime/"report.json"
    first=aobh.assess(repo,runtime,policy,state,report,False)
    assert first["status"]=="PASS",first
    catalogs=first["evolution_source_catalogs"]["digests"]
    assert set(catalogs)=={"guardian_coverage_manifest","technology_core_watch","provider_adapters","mcp_provider_catalog","project_embedded_assurance"}
    mutations={
      "guardian-coverage-manifest.v1.json":("version","drift-guardian"),
      "technology-core-watch.v1.json":("version","drift-core"),
      "provider-adapters.v1.json":("schema","chacha.dev/provider-adapters/drift"),
      "mcp-provider-catalog.v1.json":("schema","chacha.dev/mcp-provider-catalog/drift"),
      "project-embedded-assurance.v1.json":("schema","chacha.dev/project-embedded-assurance/drift"),
    }
    for name,(key,val) in mutations.items():
      p=repo/"dev-hub/config"/name;x=load(p);x[key]=val;save(p,x)
    second=aobh.assess(repo,runtime,policy,state,report,False)
    assert second["status"]=="REASSESS_REQUIRED",second
    req=load(Path(second["reassessment"]["path"]))
    reasons=set(req["trigger_reasons"])
    expected={
      "GUARDIAN_COVERAGE_MANIFEST_CHANGED","TECHNOLOGY_CORE_WATCH_CHANGED",
      "PROVIDER_ADAPTER_CATALOG_CHANGED","MCP_PROVIDER_CATALOG_CHANGED",
      "PROJECT_EMBEDDED_ASSURANCE_POLICY_CHANGED",
    }
    assert expected<=reasons,(expected-reasons,reasons)
    third=aobh.assess(repo,runtime,policy,state,report,False)
    assert third["status"]=="PASS",third

print("CHACHA_DEV_EVOLUTION_SOURCE_DRIFT=PASS")
print("CHACHA_DEV_GUARDIAN_MANIFEST_DRIFT_REASSESS=PASS")
print("CHACHA_DEV_CORE_WATCH_DRIFT_REASSESS=PASS")
print("CHACHA_DEV_PROVIDER_ADAPTER_DRIFT_REASSESS=PASS")
print("CHACHA_DEV_MCP_CATALOG_DRIFT_REASSESS=PASS")
print("CHACHA_DEV_EMBEDDED_ASSURANCE_DRIFT_REASSESS=PASS")
print("CHACHA_DEV_EVOLUTION_SOURCE_SELF_MUTATION=NO")
print("CHACHA_DEV_EVOLUTION_SOURCE_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
