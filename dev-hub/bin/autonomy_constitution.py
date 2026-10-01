#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_OBJECT_REQUIRED:"+str(p))
    return x

def sha(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def get(x:Any,path:str)->Any:
    cur=x
    for part in path.split("."):
        if not isinstance(cur,dict) or part not in cur: raise KeyError(path)
        cur=cur[part]
    return cur

def atomic(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(x,indent=2,ensure_ascii=False,sort_keys=True)+"\n");os.replace(t,p)

def check_clause(repo:Path,c:dict[str,Any])->dict[str,Any]:
    src=(repo/str(c.get("source") or "")).resolve()
    if not src.is_file():return {"id":c.get("id"),"status":"BLOCK","reason":"SOURCE_MISSING","source":str(src)}
    x=load(src);kind=c.get("kind")
    row={"id":c.get("id"),"source":str(src),"source_digest":sha(src),"kind":kind}
    try:
        if kind=="equals":
            actual=get(x,str(c.get("path") or ""));ok=(actual==c.get("expected"));row.update({"path":c.get("path"),"expected":c.get("expected"),"actual":actual,"status":"PASS" if ok else "BLOCK"})
            if not ok:row["reason"]="VALUE_MISMATCH"
        elif kind=="active-directive":
            did=str(c.get("directive_id") or "");matches=[d for d in x.get("directives") or [] if isinstance(d,dict) and d.get("directive_id")==did]
            ok=len(matches)==1 and matches[0].get("status")=="ACTIVE";row.update({"directive_id":did,"status":"PASS" if ok else "BLOCK"})
            if not ok:row["reason"]="ACTIVE_DIRECTIVE_MISSING"
        else:row.update({"status":"BLOCK","reason":"UNKNOWN_CLAUSE_KIND"})
    except Exception as e:row.update({"status":"BLOCK","reason":"EVALUATION_ERROR:"+str(e)})
    return row

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--config",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    repo=a.repo_root.resolve();cfg=load(a.config);rows=[check_clause(repo,c) for c in cfg.get("clauses") or [] if isinstance(c,dict)];blocked=[r for r in rows if r.get("status")!="PASS"]
    constitution_digest="sha256:"+hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    out={"schema":"chacha.dev/autonomy-constitution-verification/v1","status":"PASS" if not blocked else "BLOCK","constitution_schema":cfg.get("schema"),"authority_model":cfg.get("authority_model"),"clause_count":len(rows),"passed_count":len(rows)-len(blocked),"blocked_count":len(blocked),"constitution_digest":constitution_digest,"clauses":rows,"automatic_external_spend_eur":0}
    atomic(a.output,out);print(json.dumps(out,ensure_ascii=False));return 0 if not blocked else 20
if __name__=="__main__":raise SystemExit(main())
