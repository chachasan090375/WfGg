#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DEFAULT_INDEX=Path("/opt/chacha-dev/runtime/assurance-exchange/recommendation-index.json")

def load_index(path:Path=DEFAULT_INDEX)->dict[str,Any]:
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else {}
    except Exception:return {}
def recommendations(*,project_id:str|None=None,index_path:Path=DEFAULT_INDEX)->list[dict[str,Any]]:
    idx=load_index(index_path);rows=idx.get("items") if isinstance(idx.get("items"),list) else []
    out=[]
    for row in rows:
        if not isinstance(row,dict):continue
        if project_id and str(row.get("project_id") or "")!=str(project_id):continue
        if str(row.get("status") or "") not in {"OPEN","DELIVERED"}:continue
        out.append(row)
    rank={"BLOCKER":3,"OPTIMIZE":2,"OBSERVE":1}
    out.sort(key=lambda x:(-rank.get(str(x.get("priority") or ""),0),str(x.get("created_at") or "")))
    return out
def inject_context(context:dict[str,Any],*,project_id:str|None,index_path:Path=DEFAULT_INDEX)->dict[str,Any]:
    out=dict(context or {});rows=recommendations(project_id=project_id,index_path=index_path)
    if rows:
        out["assurance_exchange_recommendations"]=rows
        out["assurance_exchange_blocker_count"]=sum(1 for x in rows if x.get("priority")=="BLOCKER")
        out["assurance_exchange_optimize_count"]=sum(1 for x in rows if x.get("priority")=="OPTIMIZE")
        out["assurance_exchange_direct_mutation_allowed"]=False
        out["assurance_exchange_remediation_owner"]="central-orchestrator"
    return out
