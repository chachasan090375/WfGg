#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/read-only-research-brief/v1"
STOP={"le","la","les","de","des","du","un","une","et","ou","pour","sur","dans","avec","je","tu","il","elle","on","nous","vous","qui","que","quoi","comment","the","a","an","of","to","for","and","or","in","with"}

def tokens(q:str)->set[str]:
    return {x for x in re.findall(r"[\wÀ-ÿ.+-]{2,}",q.casefold()) if x not in STOP}

def flatten(v:Any)->str:
    if isinstance(v,dict):return " ".join(str(k)+" "+flatten(x) for k,x in v.items())
    if isinstance(v,list):return " ".join(flatten(x) for x in v[:80])
    return str(v or "")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def research(query:str,snapshot:Path,limit:int=8)->dict[str,Any]:
    base={"schema":SCHEMA,"query":query,"results":[],"read_only":True,
          "fresh_refresh_triggered":False,"network_call_performed":False,
          "general_web_provider":"UNBOUND","external_provider_invoked":False,
          "general_web_research_available":False,"automatic_external_spend_eur":0}
    if not snapshot.is_file():
        return {**base,"status":"LOCAL_SNAPSHOT_UNAVAILABLE","reason":"CACHED_TECHNOLOGY_SNAPSHOT_MISSING"}
    try:x=load(snapshot)
    except Exception:
        return {**base,"status":"LOCAL_SNAPSHOT_INVALID","reason":"CACHED_TECHNOLOGY_SNAPSHOT_INVALID"}
    q=tokens(query);ranked=[];pools=[]
    for key in ("provider_candidates","eligible_provider_candidates","branch_blueprints"):
        rows=x.get(key)
        if isinstance(rows,list):pools.extend((key,row) for row in rows if isinstance(row,dict))
    tax=x.get("technology_taxonomy")
    if isinstance(tax,dict):
        for domain,row in (tax.get("domain_categories") or {}).items():
            if isinstance(row,dict):pools.append(("technology_taxonomy",{"domain":domain,**row}))
    for source,row in pools:
        text=flatten(row).casefold();score=sum(1 for t in q if t in text)
        if score:ranked.append((score,source,row))
    ranked.sort(key=lambda z:z[0],reverse=True)
    results=[]
    for score,source,row in ranked[:max(1,min(20,limit))]:
        safe={}
        for k in ("id","domain","capability","status","health","scope","cost_class","zero_external_spend",
                  "known_provider_ids","capabilities","orchestrator","roles","reviews"):
            if k in row:safe[k]=row[k]
        results.append({"score":score,"source":source,"data":safe})
    return {**base,"status":"PASS","results":results,
            "snapshot_digest":x.get("snapshot_digest"),"snapshot_generated_at":x.get("generated_at"),
            "reason":"GENERAL_WEB_PROVIDER_NOT_BOUND"}

def save(path:Path,x:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--query",required=True)
    ap.add_argument("--snapshot",type=Path,required=True)
    ap.add_argument("--limit",type=int,default=8)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=research(a.query,a.snapshot,a.limit);save(a.output,out);print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V813_RESEARCH_BROKER=PASS")
    print("CHACHA_DEV_V813_AUTOMATIC_EXTERNAL_SPEND_EUR=0")

if __name__=="__main__":main()
