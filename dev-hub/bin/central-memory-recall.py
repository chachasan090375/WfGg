#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re,time
from pathlib import Path
from typing import Any

DEFAULT_MEMORY=Path("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json")
DEFAULT_POLICY=Path("dev-hub/config/central-memory-recall.v1.json")
WORD=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,80}")

def now():return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def canon(x:Any)->str:return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(x:Any)->str:return hashlib.sha256(canon(x).encode()).hexdigest()
def tokens(*values:Any)->set[str]:
    out=set()
    for v in values:
        s=canon(v).lower() if not isinstance(v,str) else v.lower()
        for w in WORD.findall(s):
            if len(w)>=3:out.add(w)
    return out
def package_context(pre:dict[str,Any])->tuple[set[str],set[str],set[str]]:
    domains=set();caps=set();ids=set()
    for p in pre.get("packages") or []:
        if not isinstance(p,dict):continue
        if p.get("domain"):domains.add(str(p["domain"]).lower())
        ids.add(str(p.get("id") or "").lower())
        caps.update(str(x).lower() for x in p.get("capabilities") or [])
    return domains,caps,{x for x in ids if x}
def item_score(item:dict[str,Any],project_id:str,query:set[str],domains:set[str],caps:set[str],policy:dict[str,Any])->int:
    r=policy["retrieval"];score=0
    if item.get("scope")=="PROJECT" and str(item.get("project_id") or "")==project_id:
        score+=int(r["project_scope_weight"])
    if item.get("scope")=="GLOBAL_CANDIDATE" and item.get("generalizable") is True:
        score+=int(r["global_generalizable_weight"])
    text=tokens(item.get("subject_kind",""),item.get("subject_id",""),item.get("signal_key",""))
    score+=len(query & text)*int(r["token_overlap_weight"])
    sig=str(item.get("signal_key") or "").lower()
    if any(d and d in sig for d in domains):score+=int(r["exact_domain_weight"])
    if any(c and c in sig for c in caps):score+=int(r["exact_capability_weight"])
    return score
def reuse_score(row:dict[str,Any],query:set[str],domains:set[str],caps:set[str],policy:dict[str,Any])->int:
    r=policy["retrieval"];score=0
    if str(row.get("version_status"))!="CURRENT_BEST":return -1
    domain=str(row.get("domain") or "").lower()
    if domain and domain in domains:score+=int(r["exact_domain_weight"])
    text=tokens(row)
    score+=len(query & text)*int(r["token_overlap_weight"])
    for c in caps:
        if c in text:score+=int(r["exact_capability_weight"])
    return score
def recall(memory:dict[str,Any],intent:dict[str,Any],pre:dict[str,Any],project_id:str,policy:dict[str,Any])->dict[str,Any]:
    domains,caps,package_ids=package_context(pre)
    query=tokens(intent,pre)|domains|caps|package_ids
    trusted=[];cautions=[];provisional=[]
    actionable=set(policy["trust"]["actionable_states"])
    warning=set(policy["trust"]["caution_states"])
    for item in memory.get("items") or []:
        if not isinstance(item,dict):continue
        state=str(item.get("state") or "")
        project_match=item.get("scope")=="PROJECT" and str(item.get("project_id") or "")==project_id
        global_ok=item.get("scope")=="GLOBAL_CANDIDATE" and item.get("generalizable") is True
        s=item_score(item,project_id,query,domains,caps,policy)
        relevant=project_match or global_ok or s>0
        if not relevant:continue
        row={"score":s,**item}
        if state in actionable and (project_match or global_ok):trusted.append(row)
        elif state in warning:cautions.append(row)
        elif state=="PROVISIONAL":provisional.append(row)
    trusted.sort(key=lambda x:(x["score"],x.get("confidence",0),x.get("latest_observed_at") or ""),reverse=True)
    cautions.sort(key=lambda x:(x["score"],x.get("latest_observed_at") or ""),reverse=True)
    provisional.sort(key=lambda x:(x["score"],x.get("latest_observed_at") or ""),reverse=True)
    reuse=[]
    catalog=memory.get("reuse_catalog") or {}
    for kind,key in (("branch","branches"),("architecture","architectures")):
        for row in catalog.get(key) or []:
            if not isinstance(row,dict):continue
            s=reuse_score(row,query,domains,caps,policy)
            if s<0:continue
            reuse.append({"kind":kind,"score":s,**row})
    reuse.sort(key=lambda x:(x["score"],float(x.get("quality_score") or 0),int(x.get("success_count") or 0)),reverse=True)
    max_t=int(policy["retrieval"]["max_trusted_items"]);max_c=int(policy["retrieval"]["max_cautions"]);max_r=int(policy["retrieval"]["max_reuse_candidates"])
    brief={
      "schema":"chacha.dev/central-memory-recall/v1","generated_at":now(),"project_id":project_id,
      "source_memory_snapshot_digest":memory.get("snapshot_digest"),
      "query_digest":digest({"intent":intent,"preplan":pre,"project_id":project_id}),
      "domains":sorted(domains),"capabilities":sorted(caps),"package_ids":sorted(package_ids),
      "trusted_memory":trusted[:max_t],"cautions":cautions[:max_c],
      "provisional_context_count":len(provisional),
      "current_best_reuse_candidates":reuse[:max_r],
      "trusted_memory_count":min(len(trusted),max_t),
      "caution_count":min(len(cautions),max_c),
      "reuse_candidate_count":min(len(reuse),max_r),
      "memory_authority":"ADVISORY",
      "provisional_is_actionable":False,
      "single_observation_is_actionable":False,
      "previous_solution_is_default":False,
      "technology_revalidation_required":True,
      "architecture_council_final_authority":True,
      "automatic_external_spend_eur":0
    }
    brief["brief_digest"]=digest(brief)
    return brief
def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--memory",type=Path,default=DEFAULT_MEMORY)
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--intent",type=Path,required=True)
    ap.add_argument("--preplan",type=Path,required=True)
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    if not a.memory.is_file():raise SystemExit("CENTRAL_MEMORY_RECALL_BLOCKED=ASSIMILATION_SNAPSHOT_MISSING")
    memory=load(a.memory);policy=load(a.policy)
    if memory.get("schema")!="chacha.dev/central-memory-assimilation/v1":raise SystemExit("CENTRAL_MEMORY_RECALL_BLOCKED=ASSIMILATION_SCHEMA_INVALID")
    if policy.get("schema")!="chacha.dev/central-memory-recall-policy/v1":raise SystemExit("CENTRAL_MEMORY_RECALL_BLOCKED=POLICY_SCHEMA_INVALID")
    out=recall(memory,load(a.intent),load(a.preplan),str(a.project_id),policy)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V623_CENTRAL_MEMORY_RECALL=PASS")
    print("TRUSTED_MEMORY="+str(out["trusted_memory_count"]))
    print("CAUTIONS="+str(out["caution_count"]))
    print("CURRENT_BEST_REUSE="+str(out["reuse_candidate_count"]))
    return 0
if __name__=="__main__":raise SystemExit(main())
