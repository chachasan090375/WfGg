#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/domain-toolchain-readiness/v1"
STATUS_SCORE={"ADOPT":60,"PILOT":50,"WATCH":40,"ASSESS":30,"DISCOVER":20,"DEPRECATE":10,"RETIRE":0}
GATE_SCORE={
  "INTERNAL_COMPONENT":0,
  "PROVIDER_HEALTH_PROBE_REQUIRED":1,
  "PROVIDER_PROBE_DEFINITION_REQUIRED":2,
  "ADAPTER_ENABLEMENT_REQUIRED":3,
  "PROVIDER_BINDING_REQUIRED":4,
  "ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED":5
}

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT="+str(path))
    return value

def save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def evidence_state(repo_root:Path,spec:dict[str,Any])->tuple[list[dict[str,Any]],bool]:
    evidence=[];complete=True
    for raw in spec.get("evidence") or []:
        p=Path(str(raw));p=p if p.is_absolute() else repo_root/p
        ok=p.is_file();evidence.append({"path":str(raw),"exists":ok});complete=complete and ok
    return evidence,complete

def provider_candidate(repo_root:Path,provider:dict[str,Any],bindings:dict[str,Any],adapter_defs:dict[str,Any],
                       probe_defs:dict[str,Any],encapsulated_defs:dict[str,Any])->dict[str,Any]:
    pid=str(provider.get("id") or "")
    status=str(provider.get("status") or "DISCOVER")
    encap=encapsulated_defs.get(pid) if isinstance(encapsulated_defs,dict) else None
    if isinstance(encap,dict):
        evidence,complete=evidence_state(repo_root,encap)
        return {
          "provider":pid,"provider_status":status,"kind":"encapsulated-provider",
          "owner_component":encap.get("owner_component"),
          "direct_adapter_required":False,
          "evidence":evidence,"evidence_complete":complete,
          "gate":"INTERNAL_COMPONENT" if complete else "ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED",
          "rank":STATUS_SCORE.get(status,-100)
        }

    binding=bindings.get(pid) if isinstance(bindings,dict) else None
    if not isinstance(binding,dict):
        return {
          "provider":pid,"provider_status":status,"kind":"provider",
          "adapter_id":None,"adapter_status":"UNBOUND","probe_defined":pid in probe_defs,
          "gate":"PROVIDER_BINDING_REQUIRED","rank":STATUS_SCORE.get(status,-100)
        }

    adapter_id=str(binding.get("adapter") or "")
    adapter=adapter_defs.get(adapter_id) if adapter_id else None
    adapter_status=str((adapter or {}).get("status") or "UNREGISTERED")
    execution=str(binding.get("execution") or "")
    executable=(adapter or {}).get("executable")
    row={
      "provider":pid,"provider_status":status,"kind":"provider",
      "adapter_id":adapter_id or None,"adapter_status":adapter_status,
      "execution":execution,"executable":executable,
      "probe_defined":pid in probe_defs,
      "rank":STATUS_SCORE.get(status,-100)
    }
    preenabled=adapter_status in {"PILOT","CONTRACT_OK"}
    if execution=="vps" and not executable:
        row["gate"]="ADAPTER_ENABLEMENT_REQUIRED"
        row["reason"]="vps-adapter-missing-executable"
    elif adapter_status=="ENABLED":
        if pid not in probe_defs:
            row["gate"]="PROVIDER_PROBE_DEFINITION_REQUIRED"
            row["reason"]="provider-probe-not-defined"
        else:
            row["gate"]="PROVIDER_HEALTH_PROBE_REQUIRED"
            row["reason"]="provider-ready-for-health-probe"
    elif preenabled and executable:
        if pid not in probe_defs:
            row["gate"]="PROVIDER_PROBE_DEFINITION_REQUIRED"
            row["reason"]="preenabled-provider-probe-not-defined"
        else:
            row["gate"]="PROVIDER_HEALTH_PROBE_REQUIRED"
            row["reason"]="preenabled-adapter-awaiting-health-promotion"
    else:
        row["gate"]="ADAPTER_ENABLEMENT_REQUIRED"
        row["reason"]="adapter-not-enabled"
    return row

def choose_candidate(candidates:list[dict[str,Any]])->dict[str,Any]|None:
    if not candidates:return None
    # Prefer the candidate that is closest to execution. Provider maturity breaks ties.
    return sorted(candidates,key=lambda x:(-GATE_SCORE.get(str(x.get("gate") or ""),99),
                                           int(x.get("rank") or -100),
                                           str(x.get("provider") or "")),reverse=True)[0]

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
    registry_caps=registry.get("capabilities") or {}
    decisions={str(x.get("package_id") or ""):x for x in topology.get("decisions") or [] if isinstance(x,dict)}

    task_rows=[]
    graph_errors=[]
    all_encapsulated=set();all_encap_missing=set()
    all_probe=set();all_binding=set();all_enable=set();all_probe_def=set()
    optional_agent_tools=set()

    for task in graph.get("tasks") or []:
        if not isinstance(task,dict):continue
        metadata=task.get("metadata") if isinstance(task.get("metadata"),dict) else {}
        package_id=str(metadata.get("package_id") or "")
        decision=decisions.get(package_id) or {}
        manifest=decision.get("manifest") if isinstance(decision.get("manifest"),dict) else {}
        optional_tools=[str(x) for x in (manifest.get("tools") or decision.get("toolchain") or [])]
        optional_agent_tools.update(optional_tools)
        caps=[str(x) for x in (task.get("capabilities") or [])]

        row={
          "task_id":str(task.get("id") or ""),
          "package_id":package_id,
          "agent_id":decision.get("agent_id"),
          "capabilities":caps,
          "optional_agent_tools":optional_tools,
          "provider_candidates":[],
          "selected_provider":None,
          "gate":None
        }

        if len(caps)!=1:
            row["gate"]="TASK_GRAPH_DECOMPOSITION_REQUIRED"
            row["reason"]="task-must-contain-exactly-one-runtime-capability"
            graph_errors.append({"task_id":row["task_id"],"capabilities":caps,
                                 "reason":"TASK_MUST_HAVE_EXACTLY_ONE_RUNTIME_CAPABILITY"})
            task_rows.append(row)
            continue

        cap=caps[0]
        caprow=registry_caps.get(cap)
        if not isinstance(caprow,dict):
            row["gate"]="PROVIDER_BINDING_REQUIRED";row["reason"]="capability-not-registered"
            all_binding.add(cap)
            task_rows.append(row)
            continue

        providers=[p for p in (caprow.get("providers") or [])
                   if isinstance(p,dict) and p.get("id") and p.get("status")!="RETIRE"]
        if not providers:
            row["gate"]="PROVIDER_BINDING_REQUIRED";row["reason"]="capability-has-no-provider"
            all_binding.add(cap)
            task_rows.append(row)
            continue

        candidates=[provider_candidate(repo_root,p,bindings,adapter_defs,probe_defs,encapsulated_defs) for p in providers]
        row["provider_candidates"]=candidates
        chosen=choose_candidate(candidates)
        row["selected_provider"]=chosen.get("provider") if chosen else None
        row["gate"]=chosen.get("gate") if chosen else "PROVIDER_BINDING_REQUIRED"
        row["selected_candidate"]=chosen

        gate=str(row["gate"] or "")
        provider=str(row["selected_provider"] or cap)
        if gate=="INTERNAL_COMPONENT":
            all_encapsulated.add(provider)
            # Defensive invariant: encapsulated capabilities should have been removed
            # from the scheduler graph by Domain Factory.
            graph_errors.append({"task_id":row["task_id"],"capability":cap,
                                 "reason":"ENCAPSULATED_CAPABILITY_LEAK_IN_SCHEDULER_GRAPH"})
            row["gate"]="TASK_GRAPH_DECOMPOSITION_REQUIRED"
        elif gate=="ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED":
            all_encap_missing.add(provider)
        elif gate=="PROVIDER_BINDING_REQUIRED":
            all_binding.add(provider)
        elif gate=="ADAPTER_ENABLEMENT_REQUIRED":
            all_enable.add(provider)
        elif gate=="PROVIDER_PROBE_DEFINITION_REQUIRED":
            all_probe_def.add(provider)
        elif gate=="PROVIDER_HEALTH_PROBE_REQUIRED":
            all_probe.add(provider)
        task_rows.append(row)

    if graph_errors:
        status="BLOCKED";next_stage="TASK_GRAPH_DECOMPOSITION_REQUIRED"
    elif all_encap_missing:
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
      "task_count":len(task_rows),
      "tasks":task_rows,
      "graph_errors":graph_errors,
      "summary":{
        "atomic_task_count":len(task_rows),
        "optional_agent_tool_count":len(optional_agent_tools),
        "encapsulated_provider_count":len(all_encapsulated),
        "encapsulated_provider_evidence_required_count":len(all_encap_missing),
        "provider_binding_required_count":len(all_binding),
        "adapter_enablement_required_count":len(all_enable),
        "probe_definition_required_count":len(all_probe_def),
        "health_probe_required_count":len(all_probe)
      },
      "optional_agent_tools":sorted(optional_agent_tools),
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
    print("CHACHA_DEV_V821_DOMAIN_TOOLCHAIN_READINESS="+("PASS" if result["status"]=="READY" else "BLOCKED"))
    print("NEXT_STAGE="+result["next_stage"])
    print("ATOMIC_TASKS="+str(result["summary"]["atomic_task_count"]))
    print("OPTIONAL_AGENT_TOOLS="+str(result["summary"]["optional_agent_tool_count"]))
    print("PROVIDER_BINDING_REQUIRED="+str(result["summary"]["provider_binding_required_count"]))
    print("ADAPTER_ENABLEMENT_REQUIRED="+str(result["summary"]["adapter_enablement_required_count"]))
    print("PROVIDER_PROBE_DEFINITION_REQUIRED="+str(result["summary"]["probe_definition_required_count"]))
    print("PROVIDER_HEALTH_PROBE_REQUIRED="+str(result["summary"]["health_probe_required_count"]))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"]=="READY" else 2

if __name__=="__main__":
    raise SystemExit(main())
