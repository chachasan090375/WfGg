#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
import agent_evolution_controller as aec
import agent_observation_bus as aob

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def safe(p:Path)->dict[str,Any]|None:
    try:return load(p)
    except Exception:return None
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def parse(v:Any)->datetime|None:
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None
def event_id(project:str,task_id:str,source_digest:str)->str:
    raw=(project+"|"+task_id+"|"+source_digest).encode()
    return "aobs-historical-"+hashlib.sha256(raw).hexdigest()[:28]

def normalize_role(role:str,ids:set[str],aliases:dict[str,Any])->str|None:
    role=str(role or "").strip()
    if role in ids:return role
    alias=str(aliases.get(role) or "")
    return alias if alias in ids else None

def task_index(runtime_root:Path,ids:set[str],aliases:dict[str,Any])->dict[tuple[str,str],list[dict[str,Any]]]:
    out:dict[tuple[str,str],list[dict[str,Any]]]=defaultdict(list)
    for p in runtime_root.glob("plans/**/*.task-graph.json"):
        x=safe(p)
        if not x or x.get("schema")!="chacha.dev/task-graph/v1":continue
        project=str(x.get("project") or "")
        for task in x.get("tasks") or []:
            if not isinstance(task,dict):continue
            tid=str(task.get("id") or "");aid=normalize_role(str(task.get("owner_role") or ""),ids,aliases)
            if not project or not tid or not aid:continue
            out[(project,tid)].append({"agent_id":aid,"capabilities":[str(c) for c in task.get("capabilities") or [] if str(c)]})
    return out

def unique_task(rows:list[dict[str,Any]])->dict[str,Any]|None:
    if not rows:return None
    sig={(r["agent_id"],tuple(sorted(r["capabilities"]))) for r in rows}
    return rows[0] if len(sig)==1 else None

def existing_keys(runtime_root:Path)->set[tuple[str,str]]:
    keys=set()
    try:
        for e in aob.read_events(runtime_root):
            if not isinstance(e,dict):continue
            if str(e.get("verification") or "")!="VERIFIED":continue
            if str(e.get("event_type") or "") not in {"TASK_RESULT_VERIFIED","HISTORICAL_TASK_RESULT_VERIFIED","FINAL_REVIEW_VERIFIED"}:continue
            project=str(e.get("project_id") or "");task=str(e.get("task_id") or "")
            if project and task:keys.add((project,task))
    except Exception:pass
    return keys

def validate_pair(result:dict[str,Any],report:dict[str,Any],policy:dict[str,Any])->tuple[bool,str]:
    if result.get("schema")!="chacha.dev/task-result/v1":return False,"RESULT_SCHEMA"
    ver=result.get("verification") or {}
    if str(ver.get("status") or "").upper()!="VERIFIED":return False,"RESULT_NOT_VERIFIED"
    if report.get("schema")!="chacha.dev/verification-report/v1":return False,"REPORT_SCHEMA"
    if str(report.get("status") or "").upper()!="VERIFIED":return False,"REPORT_NOT_VERIFIED"
    if str(report.get("project") or "")!=str(result.get("project") or ""):return False,"PROJECT_MISMATCH"
    if str(report.get("task_id") or "")!=str(result.get("task_id") or ""):return False,"TASK_MISMATCH"
    verifier=str(ver.get("verifier") or "");producer=str(result.get("producer") or "")
    if not verifier or verifier==producer:return False,"INDEPENDENT_VERIFIER_REQUIRED"
    if verifier!=str(report.get("verifier") or ""):return False,"VERIFIER_MISMATCH"
    digest=str(report.get("source_result_digest") or "")
    if not digest.startswith("sha256:"):return False,"SOURCE_RESULT_DIGEST_REQUIRED"
    evidence=result.get("evidence") or []
    if not isinstance(evidence,list) or not evidence:return False,"EVIDENCE_REQUIRED"
    if any(not str((e or {}).get("source") or "") or not str((e or {}).get("digest") or "").startswith("sha256:") for e in evidence if isinstance(e,dict)):
        return False,"EVIDENCE_LINEAGE_REQUIRED"
    checks=report.get("checks") or []
    if policy.get("require_report_checks_pass",True):
        if not checks or any(str((x or {}).get("status") or "").upper()!="PASS" for x in checks if isinstance(x,dict)):
            return False,"REPORT_CHECK_NOT_PASS"
    return True,"PASS"

def run(runtime_root:Path,fleet_policy:dict[str,Any],bus_policy:dict[str,Any],
        routing:dict[str,Any],seven:dict[str,Any],project_regs:list[dict[str,Any]],dry_run:bool=False)->dict[str,Any]:
    cfg=bus_policy.get("historical_verified_backfill") or {}
    inventory=aec.build_inventory(routing,seven,project_regs)
    ids={str(a.get("agent_id")) for a in inventory.get("agents") or [] if a.get("agent_id")}
    idx=task_index(runtime_root,ids,fleet_policy.get("role_aliases") or {})
    present=existing_keys(runtime_root)
    minimum_age=timedelta(minutes=int(cfg.get("minimum_age_minutes") or 0))
    now=datetime.now(timezone.utc)
    counts=defaultdict(int);published=[];eligible=[]
    for path in sorted(runtime_root.glob("transactions/**/verified-task-result.json")):
        counts["scanned"]+=1
        result=safe(path);report=safe(path.parent/"verification-report.json")
        if not result or not report:counts["invalid"]+=1;continue
        valid,reason=validate_pair(result,report,cfg)
        if not valid:counts["invalid"]+=1;continue
        project=str(result.get("project") or "");task_id=str(result.get("task_id") or "")
        task=unique_task(idx.get((project,task_id)) or [])
        if not task:counts["unmapped_or_ambiguous"]+=1;continue
        observed=parse((result.get("verification") or {}).get("observed_at") or result.get("observed_at"))
        if observed and now-observed<minimum_age:counts["too_recent"]+=1;continue
        key=(project,task_id)
        if key in present:counts["already_present"]+=1;continue
        source_digest=str(report.get("source_result_digest"))
        refs=[str(path),str(path.parent/"verification-report.json")]
        for e in result.get("evidence") or []:
            if isinstance(e,dict):refs.append(str(e.get("source"))+"#"+str(e.get("digest")))
        event={
          "schema":"chacha.dev/agent-observation-event/v1",
          "event_id":event_id(project,task_id,source_digest),
          "event_type":str(cfg.get("event_type") or "HISTORICAL_TASK_RESULT_VERIFIED"),
          "source_id":str(cfg.get("source_id") or "project-control"),
          "source_surface":str(cfg.get("source_surface") or "project-control:historical-verified-backfill"),
          "project_id":project,"task_id":task_id,"subject_role":task["agent_id"],
          "outcome":str(result.get("status") or "UNKNOWN").upper(),
          "verification":"VERIFIED","revision":source_digest,
          "capabilities":task["capabilities"],"evidence_refs":refs,
          "observed_at":((result.get("verification") or {}).get("observed_at") or result.get("observed_at")),
          "details":{"historical_verified_backfill":True,"original_verifier":(result.get("verification") or {}).get("verifier"),
                     "verification_method":(result.get("verification") or {}).get("method"),"producer":result.get("producer"),
                     "source_result_digest":source_digest,"retroactive_reassessment":False}
        }
        eligible.append(event);counts["eligible"]+=1
        if dry_run:continue
        pub=aob.publish(event,bus_policy,runtime_root)
        if pub.get("trigger") is not None:raise RuntimeError("HISTORICAL_BACKFILL_TRIGGER_FORBIDDEN:"+event["event_id"])
        if pub.get("inserted"):counts["inserted"]+=1;published.append(event["event_id"]);present.add(key)
        else:counts["duplicates"]+=1
    return {"schema":"chacha.dev/verified-evidence-backfill/v1","dry_run":dry_run,
      "counts":dict(counts),"eligible_event_count":len(eligible),"published_event_ids":published,
      "event_type":str(cfg.get("event_type") or "HISTORICAL_TASK_RESULT_VERIFIED"),
      "production_truth":True,"independent_verification_required":True,
      "retroactive_reassessment":False,"direct_agent_mutation":False,"candidate_materialization":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--runtime-root",type=Path,required=True)
    ap.add_argument("--fleet-policy",type=Path,required=True);ap.add_argument("--bus-policy",type=Path,required=True)
    ap.add_argument("--routing",type=Path,required=True);ap.add_argument("--seven",type=Path,required=True)
    ap.add_argument("--project-registry",type=Path,action="append",default=[]);ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--dry-run",action="store_true");a=ap.parse_args()
    out=run(a.runtime_root.resolve(),load(a.fleet_policy),load(a.bus_policy),load(a.routing),load(a.seven),
            [load(p) for p in a.project_registry],a.dry_run)
    save(a.output,out);print("CHACHA_DEV_V655_VERIFIED_EVIDENCE_BACKFILL=PASS")
    print("ELIGIBLE="+str(out["eligible_event_count"]));print("INSERTED="+str(out["counts"].get("inserted",0)))
    print("RETROACTIVE_REASSESSMENT=NO");print("CHACHA_DEV_V655_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
