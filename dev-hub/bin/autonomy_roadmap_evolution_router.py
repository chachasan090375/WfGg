#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save_atomic(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    tmp.replace(p)

def digest(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def slug(v:str)->str:
    return re.sub(r"[^a-zA-Z0-9_.-]+","-",v).strip("-") or "unknown"

def component_index(canonical:dict[str,Any])->dict[str,dict[str,Any]]:
    out={}
    for row in canonical.get("components") or []:
        if isinstance(row,dict) and str(row.get("component_id") or ""):
            out[str(row["component_id"])]=row
    return out

def build_plan(roadmap:dict[str,Any],policy:dict[str,Any],canonical:dict[str,Any])->dict[str,Any]:
    if roadmap.get("schema")!="chacha.dev/autonomy-gap-roadmap/v1":raise ValueError("ROADMAP_SCHEMA_INVALID")
    if policy.get("schema")!="chacha.dev/autonomy-roadmap-evolution-routing/v1":raise ValueError("ROUTING_POLICY_SCHEMA_INVALID")
    rules=policy.get("rules") if isinstance(policy.get("rules"),dict) else {}
    eligible=set(policy.get("eligible_statuses") or [])
    principles=policy.get("principles") if isinstance(policy.get("principles"),dict) else {}
    council_final=principles.get("architecture_council_final_authority") is True
    council_recommendation=principles.get("architecture_council_recommendation_authority") is True
    central_final=principles.get("central_orchestrator_is_final_decider") is True
    if council_final or not council_recommendation or not central_final:
        raise ValueError("ARCHITECTURE_AUTHORITY_CONSTITUTION_INVALID")
    components=component_index(canonical)
    requests=[];closed=[];boundaries=[];blocked=[]
    seen=set()
    for gap in roadmap.get("gaps") or []:
        if not isinstance(gap,dict):continue
        gid=str(gap.get("id") or "");seen.add(gid)
        rule=rules.get(gid)
        if not isinstance(rule,dict):
            blocked.append({"gap_id":gid,"blocker":"ROUTING_RULE_MISSING"});continue
        status=str(gap.get("status") or "")
        progress=int(gap.get("progress") or 0)
        if status not in eligible or progress>=100:
            closed.append({"gap_id":gid,"status":status,"progress":progress,"state":"NO_REASSESSMENT_REQUIRED"});continue
        mode=str(rule.get("mode") or "")
        if mode=="HUMAN_BOUNDARY":
            boundaries.append({"gap_id":gid,"status":status,"progress":progress,"mode":mode,
              "reason":str(rule.get("reason") or "UNSPECIFIED_HUMAN_BOUNDARY"),
              "automatic_external_spend_eur":0});continue
        if mode not in {"AUTO_REASSESS","GOVERNED_REASSESS"}:
            blocked.append({"gap_id":gid,"blocker":"UNSUPPORTED_ROUTING_MODE","mode":mode});continue
        cid=str(rule.get("component_id") or "")
        row=components.get(cid)
        if row is None:
            blocked.append({"gap_id":gid,"component_id":cid,"blocker":"CANONICAL_COMPONENT_NOT_FOUND"});continue
        owner=str(row.get("evolution_owner") or "")
        if owner not in {"branch-foundry","capability-foundry"}:
            blocked.append({"gap_id":gid,"component_id":cid,"candidate_owner":owner,"blocker":"UNSUPPORTED_EVOLUTION_OWNER"});continue
        evidence=str(gap.get("evidence") or "")
        request_id="roadmap-"+slug(gid)+"-"+slug(cid)
        req={
          "schema":"chacha.dev/platform-component-reassessment-request/v1",
          "request_id":request_id,"component_id":cid,
          "trigger_reasons":["AUTONOMY_ROADMAP_GAP",f"GAP_ID:{gid}",f"STATUS:{status}",f"PROGRESS:{progress}"],
          "candidate_owner":owner,"roadmap_gap_id":gid,"roadmap_status":status,"roadmap_progress":progress,
          "roadmap_state":str(gap.get("state") or ""),"roadmap_evidence_digest":"sha256:"+hashlib.sha256(evidence.encode()).hexdigest(),
          "routing_mode":mode,"shadow_required":True,"pilot_required":True,
          "direct_self_mutation":False,"direct_component_mutation":False,"self_promotion":False,"permission_expansion":False,
          "technology_watch_revalidation_required":True,"logician_falsification_required":True,
          "guardian_required":True,"sentinel_required":True,
          "architecture_council_final_authority":False,"architecture_council_recommendation_authority":True,
          "central_orchestrator_is_final_decider":True,"automatic_external_spend_eur":0}
        requests.append(req)
    extra=sorted(set(rules)-seen)
    for gid in extra:blocked.append({"gap_id":gid,"blocker":"ROUTING_RULE_ORPHANED"})
    return {"schema":"chacha.dev/autonomy-roadmap-evolution-routing-result/v1",
      "roadmap_updated_at":roadmap.get("updated_at"),"roadmap_score_percent":roadmap.get("score_percent"),
      "gap_count":len(roadmap.get("gaps") or []),"request_count":len(requests),"closed_count":len(closed),
      "human_boundary_count":len(boundaries),"blocked_count":len(blocked),
      "requests":requests,"closed":closed,"human_boundaries":boundaries,"blocked":blocked,
      "routing_complete":not blocked and len(requests)+len(closed)+len(boundaries)==len(roadmap.get("gaps") or []),
      "direct_component_mutation":False,"self_promotion":False,"permission_expansion":False,
      "architecture_council_final_authority":False,"architecture_council_recommendation_authority":True,
      "central_orchestrator_is_final_decider":True,"automatic_external_spend_eur":0}

def apply_plan(runtime_root:Path,policy:dict[str,Any],plan:dict[str,Any])->dict[str,Any]:
    queue=runtime_root/str(policy.get("queue_root") or "platform-evolution/reassessment-queue")
    queue.mkdir(parents=True,exist_ok=True)
    prefix=str(policy.get("managed_file_prefix") or "roadmap-gap-")
    desired={}
    for req in plan.get("requests") or []:
        name=prefix+slug(str(req.get("roadmap_gap_id") or ""))+"--"+slug(str(req.get("component_id") or ""))+".json"
        desired[name]=req
    removed=[];written=[];unchanged=[]
    for p in sorted(queue.glob(prefix+"*.json")):
        if p.name not in desired:
            p.unlink();removed.append(p.name)
    for name,req in sorted(desired.items()):
        p=queue/name
        before=None
        if p.is_file():
            try:before=load(p)
            except Exception:before=None
        if before==req:unchanged.append(name);continue
        save_atomic(p,req);written.append(name)
    out=dict(plan)
    out.update({"queue_root":str(queue),"written_files":written,"unchanged_files":unchanged,"removed_stale_files":removed,
      "managed_request_file_count":len(desired)})
    return out

def route(repo_root:Path,runtime_root:Path,canonical:dict[str,Any]|None=None)->dict[str,Any]:
    cfg=repo_root/"dev-hub/config"
    roadmap=load(cfg/"autonomy-gap-roadmap.v1.json")
    policy=load(cfg/"autonomy-roadmap-evolution-routing.v1.json")
    if canonical is None:
        canonical=load(runtime_root/"canonical-registry/canonical-component-registry.json")
    return apply_plan(runtime_root,policy,build_plan(roadmap,policy,canonical))

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"));ap.add_argument("--output",type=Path)
    a=ap.parse_args();out=route(a.repo_root.resolve(),a.runtime_root.resolve())
    if a.output:save_atomic(a.output,out)
    print("CHACHA_DEV_AUTONOMY_ROADMAP_EVOLUTION_ROUTING="+("PASS" if out["routing_complete"] else "BLOCKED"))
    print("REQUESTS="+str(out["request_count"]));print("HUMAN_BOUNDARIES="+str(out["human_boundary_count"]));print("BLOCKED="+str(out["blocked_count"]))
    print("DIRECT_COMPONENT_MUTATION=NO");print("SELF_PROMOTION=NO");print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if out["routing_complete"] else 2
if __name__=="__main__":raise SystemExit(main())
