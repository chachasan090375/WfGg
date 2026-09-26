#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from typing import Any
import operator_directive_registry as odr

CATALOG_SCHEMA="chacha.dev/operator-directive-sink-catalog/v1"
REPORT_SCHEMA="chacha.dev/operator-directive-impact-report/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def analyze(repo:Path,directives:dict[str,Any],catalog:dict[str,Any])->dict[str,Any]:
    if catalog.get("schema")!=CATALOG_SCHEMA:raise ValueError("DIRECTIVE_SINK_CATALOG_INVALID")
    sinks=catalog.get("sinks") if isinstance(catalog.get("sinks"),dict) else {}
    impacts=[];missing=[]
    for row in directives.get("active_global_directives") or []:
        did=str(row.get("directive_id") or "")
        targets=[]
        for sink in row.get("required_sinks") or []:
            paths=sinks.get(str(sink))
            if not isinstance(paths,list):
                missing.append({"directive_id":did,"sink":sink,"reason":"UNKNOWN_SINK"})
                targets.append({"sink":sink,"status":"MISSING","paths":[]})
                continue
            path_rows=[];ok=True
            for rel in paths:
                p=repo/str(rel);exists=p.exists()
                path_rows.append({"path":str(rel),"exists":exists})
                ok=ok and exists
            if not ok:missing.append({"directive_id":did,"sink":sink,"reason":"SINK_PATH_MISSING"})
            targets.append({"sink":sink,"status":"PRESENT" if ok else "MISSING","paths":path_rows})
        impacts.append({"directive_id":did,"scope":row.get("scope"),"category":row.get("category"),
                        "backfill_required":bool(row.get("backfill_required")),"targets":targets})
    return {"schema":REPORT_SCHEMA,"generated_at":now_iso(),
            "active_global_digest":directives.get("active_global_digest"),
            "active_global_directive_count":directives.get("active_global_directive_count"),
            "impacts":impacts,"missing_target_count":len(missing),"missing_targets":missing,
            "status":"PASS" if not missing else "BLOCKED","automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--directive-policy",type=Path,required=True)
    ap.add_argument("--sink-catalog",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--strict",action="store_true")
    a=ap.parse_args()
    directives=odr.snapshot(load(a.directive_policy))
    out=analyze(a.repo_root.resolve(),directives,load(a.sink_catalog))
    save(a.output,out)
    print("CHACHA_DEV_DIRECTIVE_IMPACT_ANALYZER="+out["status"])
    print("MISSING_TARGET_COUNT="+str(out["missing_target_count"]))
    print("CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 2 if a.strict and out["status"]!="PASS" else 0

if __name__=="__main__":raise SystemExit(main())
