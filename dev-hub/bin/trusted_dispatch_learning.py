#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any

ENVELOPE_SCHEMA="chacha.dev/dispatch-envelope/v1"
GRAPH_SCHEMA="chacha.dev/task-graph/v1"
RESULT_SCHEMA="chacha.dev/task-result/v1"
CONTEXT_SCHEMA="chacha.dev/verified-evidence-learning-context/v1"
LINEAGE_SCHEMA="chacha.dev/component-lineage/v1"

def canonical(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def digest(v:Any)->str:
    return "sha256:"+hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def locate_envelope(source_result:Path)->Path|None:
    name=source_result.name
    suffix=".task-result.json"
    if not name.endswith(suffix):return None
    candidate=source_result.parent.parent/"envelopes"/(name[:-len(suffix)]+".json")
    return candidate if candidate.is_file() else None

def adapter_binding_version(provider:str,adapter_id:str,adapters:dict[str,Any])->str:
    pdef=(adapters.get("providers") or {}).get(provider)
    adef=(adapters.get("adapters") or {}).get(adapter_id)
    if not isinstance(pdef,dict) or not isinstance(adef,dict):
        raise RuntimeError("ADAPTER_IDENTITY_NOT_REGISTERED")
    if str(pdef.get("adapter") or "")!=adapter_id:
        raise RuntimeError("PROVIDER_ADAPTER_IDENTITY_MISMATCH")
    return digest({
      "provider":provider,
      "provider_definition":pdef,
      "adapter":adapter_id,
      "adapter_definition":adef
    })

def subject_kind(binding:dict[str,Any])->str:
    explicit=str(binding.get("subject_kind") or "").strip()
    if explicit:return explicit
    mode=str(binding.get("mode") or "")
    role=str(binding.get("subject_role") or "").lower()
    if mode=="DYNAMIC_AGENT":return "agent"
    if mode=="DYNAMIC_COMPONENT":return "component"
    if "foundry" in role:return "foundry"
    if "orchestrator" in role:return "orchestrator"
    if "agent" in role:return "agent"
    if "adapter" in role or "connector" in role:return "connector"
    if "runtime" in role:return "runtime"
    return "component"

def adapter_kind(value:str)->str:
    v=value.lower()
    if "connector" in v or "mcp" in v or "provider-api" in v:return "connector"
    if "runtime" in v:return "runtime"
    return "adapter"

def task_for(graph:dict[str,Any],task_id:str)->dict[str,Any]:
    for row in graph.get("tasks") or []:
        if isinstance(row,dict) and str(row.get("id") or "")==task_id:return row
    raise RuntimeError("TASK_NOT_IN_GRAPH")

def expected_context(envelope:dict[str,Any],graph:dict[str,Any],adapters:dict[str,Any])->dict[str,Any]:
    if envelope.get("schema")!=ENVELOPE_SCHEMA:raise RuntimeError("DISPATCH_ENVELOPE_SCHEMA_INVALID")
    if graph.get("schema")!=GRAPH_SCHEMA:raise RuntimeError("TASK_GRAPH_SCHEMA_INVALID")
    project=str(envelope.get("project") or "")
    if project!=str(graph.get("project") or ""):raise RuntimeError("DISPATCH_PROJECT_MISMATCH")
    task=envelope.get("task") if isinstance(envelope.get("task"),dict) else {}
    tid=str(task.get("id") or "")
    source=task_for(graph,tid)
    source_gb=source.get("guardian_binding") if isinstance(source.get("guardian_binding"),dict) else None
    env_gb=task.get("guardian_binding") if isinstance(task.get("guardian_binding"),dict) else None
    if source_gb is None or env_gb is None:raise RuntimeError("TRUSTED_GUARDIAN_BINDING_REQUIRED")
    if canonical(source_gb)!=canonical(env_gb):raise RuntimeError("TRUSTED_GUARDIAN_BINDING_DRIFT")
    expected_binding_digest=str(env_gb.get("binding_digest") or "")
    base={k:v for k,v in env_gb.items() if k!="binding_digest"}
    if expected_binding_digest!=digest(base):raise RuntimeError("TRUSTED_GUARDIAN_BINDING_DIGEST_INVALID")

    components=[]
    subject=str(env_gb.get("subject_role") or "")
    subject_version=str(env_gb.get("dynamic_contract_version") or env_gb.get("binding_digest") or "")
    if not subject or not subject_version:raise RuntimeError("TRUSTED_SUBJECT_LINEAGE_INCOMPLETE")
    components.append({"kind":subject_kind(env_gb),"component_id":subject,"version":subject_version})

    for b in envelope.get("bindings") or []:
        if not isinstance(b,dict):continue
        provider=str(b.get("provider") or "")
        adapter=str(b.get("adapter") or "")
        if not provider or not adapter:continue
        actual=str(b.get("binding_version") or "")
        expected=adapter_binding_version(provider,adapter,adapters)
        if actual!=expected:raise RuntimeError("TRUSTED_ADAPTER_BINDING_VERSION_INVALID:"+adapter)
        components.append({
          "kind":adapter_kind(str(b.get("adapter_kind") or "")),
          "component_id":adapter,
          "version":expected
        })

    dedup=[]
    seen=set()
    for row in components:
        key=(row["kind"],row["component_id"],row["version"])
        if key not in seen:
            dedup.append(row);seen.add(key)
    run_id=str(envelope.get("run_id") or "")
    if not run_id:raise RuntimeError("TRUSTED_DISPATCH_RUN_ID_REQUIRED")
    return {
      "schema":CONTEXT_SCHEMA,
      "deployment_id":run_id+":"+tid,
      "source_id":subject,
      "surface_kind":"trusted-dispatch-result",
      "evidence_refs":["dispatch:"+run_id+":"+tid],
      "component_lineage":{"schema":LINEAGE_SCHEMA,"components":dedup}
    }

def trusted_context(source_result_path:Path,graph:dict[str,Any],adapters:dict[str,Any])->tuple[dict[str,Any]|None,str,Path|None]:
    envelope_path=locate_envelope(source_result_path)
    if envelope_path is None:return None,"NO_DISPATCH_ENVELOPE",None
    envelope=load(envelope_path)
    source=load(source_result_path)
    if source.get("schema")!=RESULT_SCHEMA:return None,"SOURCE_RESULT_SCHEMA_INVALID",envelope_path
    if source.get("project")!=envelope.get("project"):return None,"SOURCE_RESULT_PROJECT_MISMATCH",envelope_path
    if str(source.get("task_id") or "")!=str(((envelope.get("task") or {}).get("id")) or ""):
        return None,"SOURCE_RESULT_TASK_MISMATCH",envelope_path
    try:
        expected=expected_context(envelope,graph,adapters)
    except Exception as exc:
        return None,"UNTRUSTED_DISPATCH_CONTEXT:"+type(exc).__name__+":"+str(exc),envelope_path
    actual=envelope.get("learning_context")
    if not isinstance(actual,dict) or canonical(actual)!=canonical(expected):
        return None,"DISPATCH_LEARNING_CONTEXT_MISMATCH",envelope_path
    return expected,"TRUSTED_DISPATCH_CONTEXT",envelope_path

def enrich_verified_result(*,verified:dict[str,Any],source_result_path:Path,graph:dict[str,Any],
                           adapters:dict[str,Any])->tuple[dict[str,Any],str,Path|None]:
    out=json.loads(json.dumps(verified))
    out.pop("learning_context",None)
    context,status,envelope=trusted_context(source_result_path,graph,adapters)
    if context is not None:out["learning_context"]=context
    return out,status,envelope
