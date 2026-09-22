#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
from typing import Any

DEFAULT_INDEX=Path("/opt/chacha-dev/runtime/guardian/remediation-index.json")

def load_index(path:Path=DEFAULT_INDEX)->dict[str,Any]:
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else {}
    except Exception:
        return {}

def current_directive(*,actor:str,subject_role:str,project_id:str|None,index_path:Path=DEFAULT_INDEX)->dict[str,Any]|None:
    idx=load_index(index_path)
    items=idx.get("items") if isinstance(idx.get("items"),list) else []
    project=str(project_id or "")
    matches=[]
    for d in items:
        if not isinstance(d,dict):continue
        if str(d.get("status") or "") not in {"OPEN","DELIVERED"}:continue
        dp=str(d.get("project_id") or "")
        if dp and project and dp!=project:continue
        target=str(d.get("target_actor") or d.get("target_role") or "")
        if target in {str(subject_role or ""),str(actor or "")}:
            matches.append(d)
    if not matches:return None
    rank={"CRITICAL":3,"BLOCK":2,"WARNING":1}
    matches.sort(key=lambda d:(-rank.get(str(d.get("severity") or ""),0),str(d.get("created_at") or "")))
    return matches[0]

def inject_context(context:dict[str,Any],*,actor:str,subject_role:str,project_id:str|None,index_path:Path=DEFAULT_INDEX)->dict[str,Any]:
    out=dict(context or {})
    d=current_directive(actor=actor,subject_role=subject_role,project_id=project_id,index_path=index_path)
    if d:
        out["remediation_directive_id"]=str(d.get("directive_id") or "")
        out["guardian_required_action"]=str(d.get("required_action") or "")
        out["guardian_rule_codes"]=[str(x) for x in (d.get("rule_codes") or [])]
    return out
