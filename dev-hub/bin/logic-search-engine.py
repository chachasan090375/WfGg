#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,itertools,json,math,subprocess
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/logic-search-report/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def git_files(root:Path)->list[str]:
    p=subprocess.run(["git","ls-files"],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0:return []
    return [x.strip() for x in p.stdout.splitlines() if x.strip()]
def tokens(row:dict[str,Any])->list[str]:
    xs=[str(row.get("domain") or ""),str(row.get("kind") or "")]
    xs.extend(map(str,row.get("capabilities") or []))
    out=[]
    for x in xs:
        for part in x.lower().replace("_","-").split("-"):
            if len(part)>=4 and part not in {"with","from","this","that","project"}:out.append(part)
    return sorted(set(out))
def existing_matches(files:list[str],row:dict[str,Any],limit:int)->list[str]:
    ts=tokens(row)
    if not ts:return []
    scored=[]
    for f in files:
        low=f.lower()
        score=sum(1 for t in ts if t in low)
        if score:scored.append((score,len(f),f))
    scored.sort(key=lambda x:(-x[0],x[1],x[2]))
    return [x[2] for x in scored[:limit]]
def memory_reuse_count(memory:dict[str,Any])->int:
    return sum(1 for x in memory.get("current_best_reuse_candidates") or [] if isinstance(x,dict))
def decode_path(index:int,n_packages:int,n_choices:int)->list[int]:
    out=[]
    for _ in range(n_packages):
        out.append(index%n_choices);index//=n_choices
    return out
def score_path(routes:list[str],execution:str,package_rows:list[dict[str,Any]],matches:list[list[str]],
               reuse_available:bool,policy:dict[str,Any])->tuple[float,dict[str,Any]]:
    w=policy.get("scoring") or {}
    score=float(w.get("base",100))
    synthesis=sum(1 for r in routes if r=="MINIMAL_SYNTHESIS")
    existing=sum(1 for i,r in enumerate(routes) if r=="EXISTING_ARTIFACT" and bool(matches[i]))
    reuse=sum(1 for r in routes if r=="CURRENT_BEST_REUSE" and reuse_available)
    invalid_existing=sum(1 for i,r in enumerate(routes) if r=="EXISTING_ARTIFACT" and not matches[i])
    invalid_reuse=sum(1 for r in routes if r=="CURRENT_BEST_REUSE" and not reuse_available)
    uncertainty=synthesis+invalid_existing+invalid_reuse
    step_count=len(package_rows)+synthesis+invalid_existing+invalid_reuse
    score-=step_count*float(w.get("step_penalty",1.4))
    score-=synthesis*float(w.get("synthesis_penalty",4.0))
    score-=uncertainty*float(w.get("uncertainty_penalty",2.5))
    score+=existing*float(w.get("existing_artifact_bonus",3.0))
    score+=reuse*float(w.get("current_best_reuse_bonus",4.0))
    if execution=="PARALLEL_WHERE_INDEPENDENT" and len(package_rows)>1:
        score+=min(len(package_rows)-1,6)*float(w.get("parallelism_bonus",1.5))
    if execution=="EVIDENCE_FIRST":score+=float(w.get("evidence_first_bonus",1.0))
    hard_ok=(invalid_existing==0 and invalid_reuse==0)
    metrics={
      "step_count":step_count,"synthesis_count":synthesis,"existing_artifact_count":existing,
      "reuse_count":reuse,"uncertainty_count":uncertainty,"hard_constraints_ok":hard_ok
    }
    return round(score,4),metrics
def make_candidate(routes,execution,rows,matches,reuse_available,policy):
    score,metrics=score_path(routes,execution,rows,matches,reuse_available,policy)
    package_routes=[]
    for i,row in enumerate(rows):
        package_routes.append({
          "package_id":row.get("id"),"domain":row.get("domain"),"kind":row.get("kind"),
          "route":routes[i],
          "existing_artifact_matches":matches[i][:3] if routes[i]=="EXISTING_ARTIFACT" else []
        })
    x={"execution_mode":execution,"package_routes":package_routes,"score":score,"metrics":metrics,
       "verification_required":True,"automatic_external_spend_eur":0}
    x["candidate_id"]="logic-"+hashlib.sha256(canon(x).encode()).hexdigest()[:16]
    return x

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--intent",type=Path,required=True);ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--preplan",type=Path,required=True);ap.add_argument("--memory-brief",type=Path)
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    root=a.repo_root.resolve();pre=load(a.preplan);policy=load(a.policy);intent=load(a.intent);contract=load(a.contract)
    memory=load(a.memory_brief) if a.memory_brief and a.memory_brief.is_file() else {}
    rows=[x for x in pre.get("packages") or [] if isinstance(x,dict)]
    files=git_files(root);limit=int(policy.get("max_repository_matches_per_package",12))
    matches=[existing_matches(files,row,limit) for row in rows]
    reuse_available=memory_reuse_count(memory)>0
    choices=list(policy.get("route_choices") or ["CURRENT_PLAN"])
    modes=list(policy.get("execution_modes") or ["DEPENDENCY_ORDERED"])
    n=max(1,len(rows));space=(len(choices)**n)*max(1,len(modes))
    max_paths=int(policy.get("max_virtual_paths",50000));evaluated=min(space,max_paths)
    baseline_routes=["CURRENT_PLAN"]*len(rows)
    baseline=make_candidate(baseline_routes,"DEPENDENCY_ORDERED",rows,matches,reuse_available,policy)
    best=baseline
    nchoices=max(1,len(choices))
    for idx in range(evaluated):
        route_idx=decode_path(idx//max(1,len(modes)),len(rows),nchoices)
        routes=[choices[i] for i in route_idx]
        mode=modes[idx%len(modes)]
        cand=make_candidate(routes,mode,rows,matches,reuse_available,policy)
        if not cand["metrics"]["hard_constraints_ok"]:continue
        if (cand["score"],cand["candidate_id"])>(best["score"],best["candidate_id"]):best=cand
    gain=round(float(best["score"])-float(baseline["score"]),4)
    th=policy.get("challenge_thresholds") or {}
    if best["candidate_id"]==baseline["candidate_id"] or gain<float(th.get("reconsider_gain",4)):
        status="KEEP"
    elif gain>=float(th.get("replan_gain",10)):
        status="REPLAN_REQUIRED"
    else:
        status="RECONSIDER"
    existing_found=sum(1 for x in matches if x)
    result={
      "schema":SCHEMA,"version":"1.0.0",
      "intent_name":intent.get("name"),"contract_id":contract.get("contract_id"),
      "virtual_space_size":space,"evaluated_path_count":evaluated,
      "search_budget_exhausted":space>max_paths,"max_virtual_paths":max_paths,
      "repository_file_count":len(files),"packages_with_existing_artifact_matches":existing_found,
      "memory_reuse_available":reuse_available,
      "baseline":baseline,"best_candidate":best,"score_gain":gain,
      "challenge_status":status,
      "challenge_reason":"BETTER_ELIGIBLE_PATH" if status!="KEEP" else "CURRENT_PATH_NOT_MATERIALLY_OUTPERFORMED",
      "central_brain_response_required":status!="KEEP",
      "dismissal_without_evidence_forbidden":True,
      "recommended_next_action":"REOPEN_PLAN" if status=="REPLAN_REQUIRED" else "COMPARE_AND_ANSWER" if status=="RECONSIDER" else "CONTINUE",
      "evidence_class":"STRUCTURAL_HEURISTIC_REQUIRES_VERIFICATION",
      "technology_watch_required_for_architecture_change":True,
      "architecture_council_final_authority":True,
      "direct_mutation":False,"automatic_external_spend_eur":0
    }
    result["report_digest"]=digest(result)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_LOGIC_SEARCH=PASS")
    print("VIRTUAL_PATHS="+str(space))
    print("EVALUATED_PATHS="+str(evaluated))
    print("CHALLENGE_STATUS="+status)
    print("SCORE_GAIN="+str(gain))
    print("DIRECT_MUTATION=NO")
    return 0

if __name__=="__main__":raise SystemExit(main())
