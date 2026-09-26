#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,time
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/operator-directive-registry-policy/v1"
SNAPSHOT_SCHEMA="chacha.dev/operator-directive-registry/v1"
ACTIVE_STATUSES={"ACTIVE"}
GLOBAL_SCOPES={"PLATFORM_GLOBAL","SAFETY_GOVERNANCE","ARCHITECTURE"}

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def digest(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def validate(policy:dict[str,Any])->list[dict[str,Any]]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("OPERATOR_DIRECTIVE_POLICY_INVALID")
    rows=policy.get("directives") or []
    if not isinstance(rows,list):raise ValueError("OPERATOR_DIRECTIVES_NOT_LIST")
    seen=set();out=[]
    for row in rows:
        if not isinstance(row,dict):raise ValueError("OPERATOR_DIRECTIVE_ROW_INVALID")
        did=str(row.get("directive_id") or "").strip()
        if not did:raise ValueError("OPERATOR_DIRECTIVE_ID_REQUIRED")
        if did in seen:raise ValueError("OPERATOR_DIRECTIVE_DUPLICATE:"+did)
        seen.add(did)
        status=str(row.get("status") or "").upper()
        scope=str(row.get("scope") or "").upper()
        category=str(row.get("category") or "").upper()
        requirement=str(row.get("normalized_requirement") or "").strip()
        sinks=[str(x) for x in row.get("required_sinks") or [] if str(x).strip()]
        if not status or not scope or not category or not requirement:
            raise ValueError("OPERATOR_DIRECTIVE_FIELDS_REQUIRED:"+did)
        if status in ACTIVE_STATUSES and not sinks:
            raise ValueError("ACTIVE_DIRECTIVE_SINKS_REQUIRED:"+did)
        out.append({**row,"directive_id":did,"status":status,"scope":scope,
                    "category":category,"normalized_requirement":requirement,
                    "required_sinks":sorted(set(sinks))})
    return out

def snapshot(policy:dict[str,Any])->dict[str,Any]:
    rows=validate(policy)
    active=[r for r in rows if r["status"] in ACTIVE_STATUSES]
    active_global=[r for r in active if r["scope"] in GLOBAL_SCOPES or r["category"] in GLOBAL_SCOPES]
    payload={
      "schema":SNAPSHOT_SCHEMA,"generated_at":now_iso(),
      "policy_version":policy.get("version"),"directive_count":len(rows),
      "active_directive_count":len(active),"active_global_directive_count":len(active_global),
      "directives":rows,"active_directives":active,
      "active_global_directives":active_global,
      "active_global_ids":sorted(r["directive_id"] for r in active_global),
      "automatic_external_spend_eur":0
    }
    payload["active_global_digest"]=digest(payload["active_global_directives"])
    payload["registry_digest"]=digest(payload["directives"])
    return payload

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=snapshot(load(a.policy));save(a.output,out)
    print("CHACHA_DEV_OPERATOR_DIRECTIVE_REGISTRY=PASS")
    print("ACTIVE_GLOBAL_DIRECTIVE_COUNT="+str(out["active_global_directive_count"]))
    print("ACTIVE_GLOBAL_DIGEST="+str(out["active_global_digest"]))
    print("CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":raise SystemExit(main())
