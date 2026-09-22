#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/task-contract-binding/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT="+str(path))
    return x

def canonical(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def digest(v:Any)->str:
    return "sha256:"+hashlib.sha256(canonical(v).encode()).hexdigest()

def role_contract_ref(role:str,contracts:dict[str,Any])->str:
    ids={str(x.get("contract_id")) for x in contracts.get("contracts") or [] if isinstance(x,dict)}
    exact="role:"+role
    if exact in ids:return exact
    lower=role.lower()
    if "foundry" in lower and "role:__foundry__" in ids:return "role:__foundry__"
    if (lower.endswith("-agent") or lower=="agent") and "role:__agent__" in ids:return "role:__agent__"
    if "orchestrator" in lower and "role:__orchestrator__" in ids:return "role:__orchestrator__"
    return "role:__unknown__"

def indices(agent_batch:dict[str,Any],component_batch:dict[str,Any]):
    agents={str(c.get("agent_id")):c for c in agent_batch.get("contracts") or [] if isinstance(c,dict) and c.get("agent_id")}
    comps={str(c.get("component_id")):c for c in component_batch.get("contracts") or [] if isinstance(c,dict) and c.get("component_id")}
    return agents,comps

def bind_task(task:dict[str,Any],project_id:str,agents:dict[str,Any],components:dict[str,Any],roles:dict[str,Any])->tuple[dict[str,Any],list[str]]:
    role=str(task.get("owner_role") or "orchestrator")
    meta=task.get("metadata") if isinstance(task.get("metadata"),dict) else {}
    explicit_agent=str(meta.get("agent_id") or "")
    explicit_component=str(meta.get("component_id") or "")
    errors=[]
    selected=None
    mode="STATIC_ROLE"
    subject=role
    if explicit_agent:
        selected=agents.get(explicit_agent)
        if selected is None:errors.append("EXPLICIT_AGENT_CONTRACT_NOT_FOUND:"+explicit_agent)
        else: mode="DYNAMIC_AGENT";subject=explicit_agent
    elif explicit_component:
        selected=components.get(explicit_component)
        if selected is None:errors.append("EXPLICIT_COMPONENT_CONTRACT_NOT_FOUND:"+explicit_component)
        else: mode="DYNAMIC_COMPONENT";subject=explicit_component
    elif role in agents:
        selected=agents[role];mode="DYNAMIC_AGENT";subject=role
    elif role in components:
        selected=components[role];mode="DYNAMIC_COMPONENT";subject=role

    caps=[str(x) for x in task.get("capabilities") or []]
    if selected is not None:
        if str(selected.get("project_id") or "")!=project_id:
            errors.append("CONTRACT_PROJECT_MISMATCH")
        allowed=set(map(str,selected.get("allowed_capabilities") or []))
        missing=sorted(set(caps)-allowed)
        if missing: errors.extend("CAPABILITY_OUTSIDE_BOUND_CONTRACT:"+x for x in missing)
        binding={
          "mode":mode,
          "subject_role":subject,
          "policy_contract_ref":str(selected.get("template_contract_id") or ""),
          "dynamic_contract_id":str(selected.get("contract_id") or ""),
          "dynamic_contract_version":str(selected.get("version") or ""),
          "project_id":project_id,
          "domain":str(selected.get("domain") or ""),
          "package_id":str(selected.get("package_id") or ""),
          "capabilities":caps
        }
    else:
        binding={
          "mode":"STATIC_ROLE",
          "subject_role":subject,
          "policy_contract_ref":role_contract_ref(role,roles),
          "dynamic_contract_id":None,
          "dynamic_contract_version":None,
          "project_id":project_id,
          "domain":str(meta.get("domain") or ""),
          "package_id":str(meta.get("package_id") or ""),
          "capabilities":caps
        }
    binding["binding_digest"]=digest({k:v for k,v in binding.items() if k!="binding_digest"})
    return binding,errors

def bind_graph(graph:dict[str,Any],agent_batch:dict[str,Any],component_batch:dict[str,Any],roles:dict[str,Any])->dict[str,Any]:
    if graph.get("schema")!="chacha.dev/task-graph/v1":raise SystemExit("TASK_GRAPH_SCHEMA_INVALID")
    project_id=str(graph.get("project") or "")
    agents,components=indices(agent_batch,component_batch)
    out=json.loads(json.dumps(graph))
    blocked=[]
    dyn=0
    for task in out.get("tasks") or []:
        binding,errors=bind_task(task,project_id,agents,components,roles)
        task["guardian_binding"]=binding
        if binding["mode"].startswith("DYNAMIC_"):dyn+=1
        if errors:
            task["guardian_binding_errors"]=errors
            blocked.append({"task_id":task.get("id"),"reasons":errors})
    out["guardian_binding"]={
      "schema":SCHEMA,
      "all_tasks_bound":all("guardian_binding" in t for t in out.get("tasks") or []),
      "task_count":len(out.get("tasks") or []),
      "dynamic_task_count":dyn,
      "blocked_task_count":len(blocked),
      "blocked":blocked,
      "automatic_external_spend_eur":0
    }
    out["dispatch_allowed"]=len(blocked)==0
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--agent-contracts",type=Path,required=True)
    ap.add_argument("--component-contracts",type=Path,required=True)
    ap.add_argument("--role-contracts",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=bind_graph(load(a.graph),load(a.agent_contracts),load(a.component_contracts),load(a.role_contracts))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_TASK_CONTRACT_BINDING=PASS")
    print("TASKS="+str(out["guardian_binding"]["task_count"]))
    print("DYNAMIC_TASKS="+str(out["guardian_binding"]["dynamic_task_count"]))
    print("BLOCKED="+str(out["guardian_binding"]["blocked_task_count"]))

if __name__=="__main__":main()
