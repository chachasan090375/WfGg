#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,sqlite3,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/conversation-advisory-brief/v1"
STOP={"le","la","les","de","des","du","un","une","et","ou","pour","sur","dans","avec","je","tu","il","elle","on","nous","vous","qui","que","quoi","comment","the","a","an","of","to","for","and","or","in","with"}

def tokens(q:str)->set[str]:
    return {x for x in re.findall(r"[\wÀ-ÿ.-]{2,}",q.casefold()) if x not in STOP}

def flatten(v:Any)->str:
    if isinstance(v,dict):return " ".join(str(k)+" "+flatten(x) for k,x in v.items())
    if isinstance(v,list):return " ".join(flatten(x) for x in v[:30])
    return str(v or "")

def memory_hits(query:str,path:Path,limit:int=6)->dict[str,Any]:
    if not path.is_file():return {"status":"UNAVAILABLE","items":[]}
    x=json.loads(path.read_text(encoding="utf-8"));q=tokens(query)
    rows=x.get("items") if isinstance(x.get("items"),list) else []
    ranked=[]
    for row in rows:
        if not isinstance(row,dict):continue
        text=flatten(row).casefold();s=sum(1 for t in q if t in text)
        if s:ranked.append((s,row))
    ranked.sort(key=lambda z:z[0],reverse=True)
    items=[]
    safe_keys=("project_id","component_id","kind","domain","capability","state","confidence","summary",
               "learning","candidate","recommendation","evidence_refs","source","observed_at")
    for s,row in ranked[:limit]:
        c={k:row[k] for k in safe_keys if k in row}
        if not c:
            c={"summary":flatten(row)[:900]}
        items.append({"score":s,"item":c})
    return {"status":"PASS","snapshot_digest":x.get("snapshot_digest"),"generated_at":x.get("generated_at"),"items":items}

def human_stats(db:Path)->dict[str,Any]:
    if not db.is_file():return {"status":"UNAVAILABLE","observations":0,"persona_feedback":0}
    try:
        con=sqlite3.connect(str(db));con.row_factory=sqlite3.Row
        obs=con.execute("SELECT COUNT(*) c FROM observations").fetchone()["c"]
        fb=con.execute("SELECT COUNT(*) c FROM persona_feedback").fetchone()["c"]
        domains={r["domain"]:r["c"] for r in con.execute("SELECT domain,COUNT(*) c FROM observations GROUP BY domain")}
        return {"status":"PASS","observations":obs,"persona_feedback":fb,"domains":domains}
    except Exception:return {"status":"UNAVAILABLE","observations":0,"persona_feedback":0}

def build(query:str,memory:Path,human_db:Path,research:dict[str,Any]|None=None)->dict[str,Any]:
    return {
      "schema":SCHEMA,"status":"PASS","query":query,"read_only":True,
      "memory":memory_hits(query,memory),
      "human_behavior_center":human_stats(human_db),
      "research":research or {"status":"NOT_REQUESTED"},
      "authorities":{
        "decision_authority":False,"execution_authority":False,"mutation_authority":False,
        "scheduler_called":False,"run_controller_called":False,"foundry_called":False
      },
      "generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "automatic_external_spend_eur":0
    }

def save(path:Path,x:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(tmp,path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--query",required=True)
    ap.add_argument("--memory",type=Path,default=Path("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"))
    ap.add_argument("--human-db",type=Path,default=Path("/opt/chacha-dev/runtime/knowledge/human-behavior/evidence.db"))
    ap.add_argument("--research",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    research=json.loads(a.research.read_text(encoding="utf-8")) if a.research and a.research.is_file() else None
    out=build(a.query,a.memory,a.human_db,research);save(a.output,out);print(json.dumps(out,ensure_ascii=False))
if __name__=="__main__":main()
