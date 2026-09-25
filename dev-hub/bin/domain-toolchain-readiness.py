#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/domain-toolchain-readiness/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT="+str(path))
    return value

def save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def evaluate(repo_root:Path,planning_dir:Path,factory_dir:Path,output:Path)->dict[str,Any]:
    graph=load(factory_dir/"domain-execution-graph.json")
    topology=load(planning_dir/"agent-topology.json")
    adapters=load(repo_root/"dev-hub/config/provider-adapters.v1.json")
    probes=load(repo_root/"dev-hub/config/provider-health-probes.v1.json")
    registry=load(repo_root/"dev-hub/config/capability-registry.v1.json")
    semantics_path=repo_root/"dev-hub/config/domain-toolchain-semantics.v1.json"
    semantics=load(semantics_path) if semantics_path.is_file() else {"encapsulated_provider_tools":{}}

    if graph.get("schema")!="chacha.dev/task-graph/v1":raise SystemExit("DOMAIN_EXECUTION_GRAPH_SCHEMA_INVALID")
    if topology.get("schema")!="chacha.dev/agent-topology/v1":raise SystemExit("AGENT_TOPOLOGY_SCHEMA_INVALID")
    if adapters.get("schema")!="chacha.dev/provider-adapters/v1":raise SystemExit("PROVIDER_ADAPTER_SCHEMA_INVALID")
    if probes.get("schema")!="chacha.dev/provider-health-probes/v1":raise SystemExit("PROBE_CATALOG_SCHEMA_INVALID")
    if registry.get("schema")!="chacha.dev/capability-registry/v1":raise SystemExit("CAPABILITY_REGISTRY_SCHEMA_INVALID")

    bindings=adapters.get("providers") or {}
    adapter_defs=adapters.get("adapters") or {}
    probe_defs=probes.get("providers") or {}
    encapsulated_defs=semantics.get("encapsulated_provider_tools") or {}
    provider_ids=set()
    for cap in (registry.get("capabilities") or {}).values():
        if not isinstance(cap,dict):continue
        for row in cap.get("providers") or []:
            if isinstance(row,dict) and row.get("id"):provider_ids.add(str(row["id"]))

    decisions={str(x.get("package_id") or ""):x for x in topology.get("decisions") or [] if isinstance(x,dict)}
    package_rows=[]
    all_internal=set();all_encapsulated=set();all_encap_missing=set()
    all_probe=set();all_binding=set();all_enable=set();all_probe_def=set()

    for task in graph.get("tasks") or []:
        if not isinstance(task,dict):continue
        package_id=str((task.get("metadata") or {}).get("package_id") or "")
        decision=decisions.get(package_id) or {}
        manifest=decision.get("manifest") if isinstance(decision.get("manifest"),dict) else {}
        tools=[str(x) for x in (manifest.get("tools") or decision.get("toolchain") or [])]
        rows=[]
        for tool in tools:
            encap=encapsulated_defs.get(tool) if isinstance(encapsulated_defs,dict) else None
            if isinstance(encap,dict):
                evidence=[];complete=True
                for raw in encap.get("evidence") or []:
                    p=Path(str(raw));p=p if p.is_absolute() else repo_root/p
                    ok=p.is_file();evidence.append({"path":str(raw),"exists":ok});complete=complete and ok
                row={"tool":tool,"kind":"encapsulated-provider",
                     "owner_component":encap.get("owner_component"),
                     "direct_adapter_required":False,
                     "evidence":evidence,"evidence_complete":complete,
                     "gate":"INTERNAL_COMPONENT" if complete else "ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED"}
                if complete:all_encapsulated.add(tool)
                else:all_encap_missing.add(tool)
            elif tool in bindings:
                binding=bindings.get(tool) or {}
                adapter_id=str(binding.get("adapter") or "")
                adapter=adapter_defs.get(adapter_id) if adapter_id else None
                status=str((adapter or {}).get("status") or "UNREGISTERED")
                row={"tool":tool,"kind":"provider","adapter_id":adapter_id or None,
                     "adapter_status":status,"executable":(adapter or {}).get("executable"),
                     "probe_defined":tool in probe_defs}
                if status!="ENABLED":
                    row["gate"]="ADAPTER_ENABLEMENT_REQUIRED";all_enable.add(tool)
                elif tool not in probe_defs:
                    row["gate"]="PROVIDER_PROBE_DEFINITION_REQUIRED";all_probe_def.add(tool)
                else:
                    row["gate"]="PROVIDER_HEALTH_PROBE_REQUIRED";all_probe.add(tool)
            elif tool in provider_ids:
                row={"tool":tool,"kind":"provider","adapter_id":None,"adapter_status":"UNBOUND",
                     "probe_defined":tool in probe_defs,"gate":"PROVIDER_BINDING_REQUIRED"}
                all_binding.add(tool)
            else:
                row={"tool":tool,"kind":"internal-tool","gate":"INTERNAL_COMPONENT"}
                all_internal.add(tool)
            rows.append(row)
        package_rows.append({
          "package_id":package_id,"agent_id":decision.get("agent_id"),
          "tool_count":len(tools),"tools":rows
        })

    if all_encap_missing:
        status="BLOCKED";next_stage="ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED"
    elif all_binding:
        status="BLOCKED";next_stage="PROVIDER_BINDING_REQUIRED"
    elif all_enable:
        status="BLOCKED";next_stage="ADAPTER_ENABLEMENT_REQUIRED"
    elif all_probe_def:
        status="BLOCKED";next_stage="PROVIDER_PROBE_DEFINITION_REQUIRED"
    elif all_probe:
        status="BLOCKED";next_stage="PROVIDER_HEALTH_PROBE_REQUIRED"
    else:
        status="READY";next_stage="SCHEDULER_READY"

    result={
      "schema":SCHEMA,
      "project_id":str(graph.get("project") or ""),
      "status":status,"next_stage":next_stage,
      "package_count":len(package_rows),
      "packages":package_rows,
      "summary":{
        "internal_tool_count":len(all_internal),
        "encapsulated_provider_count":len(all_encapsulated),
        "encapsulated_provider_evidence_required_count":len(all_encap_missing),
        "provider_binding_required_count":len(all_binding),
        "adapter_enablement_required_count":len(all_enable),
        "probe_definition_required_count":len(all_probe_def),
        "health_probe_required_count":len(all_probe)
      },
      "internal_tools":sorted(all_internal),
      "encapsulated_providers":sorted(all_encapsulated),
      "encapsulated_provider_evidence_required":sorted(all_encap_missing),
      "provider_binding_required":sorted(all_binding),
      "adapter_enablement_required":sorted(all_enable),
      "probe_definition_required":sorted(all_probe_def),
      "health_probe_required":sorted(all_probe),
      "provider_execution_started":False,
      "adapter_invocation_started":False,
      "production_permissions_allowed":False,
      "automatic_external_spend_eur":0
    }
    save(output,result)
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--planning-dir",type=Path,required=True)
    ap.add_argument("--factory-dir",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    result=evaluate(a.repo_root.resolve(),a.planning_dir.resolve(),a.factory_dir.resolve(),a.output.resolve())
    print("CHACHA_DEV_V819_DOMAIN_TOOLCHAIN_READINESS="+("PASS" if result["status"]=="READY" else "BLOCKED"))
    print("NEXT_STAGE="+result["next_stage"])
    print("INTERNAL_TOOLS="+str(result["summary"]["internal_tool_count"]))
    print("ENCAPSULATED_PROVIDERS="+str(result["summary"]["encapsulated_provider_count"]))
    print("ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED="+str(result["summary"]["encapsulated_provider_evidence_required_count"]))
    print("PROVIDER_BINDING_REQUIRED="+str(result["summary"]["provider_binding_required_count"]))
    print("ADAPTER_ENABLEMENT_REQUIRED="+str(result["summary"]["adapter_enablement_required_count"]))
    print("PROVIDER_PROBE_DEFINITION_REQUIRED="+str(result["summary"]["probe_definition_required_count"]))
    print("PROVIDER_HEALTH_PROBE_REQUIRED="+str(result["summary"]["health_probe_required_count"]))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"]=="READY" else 2

if __name__=="__main__":
    raise SystemExit(main())
