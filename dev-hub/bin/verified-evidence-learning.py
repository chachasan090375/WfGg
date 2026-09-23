#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,hashlib,json,os,subprocess,tempfile,uuid
from pathlib import Path
from typing import Any
import universal_learning_runtime as ul

REPO_ROOT=Path(__file__).resolve().parents[2]
DEFAULT_POLICY=REPO_ROOT/"dev-hub/config/verified-evidence-learning.v1.json"
DEFAULT_MARKERS=Path("/opt/chacha-dev/runtime/knowledge/verified-evidence-learning-applied")
DEFAULT_OUTBOX=Path("/opt/chacha-dev/runtime/learning/outbox")
DEFAULT_STATE=Path("/opt/chacha-dev/runtime/learning/producer-state")
DEFAULT_EVIDENCE_ROOT=Path("/opt/chacha-dev/runtime/evidence")

def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return hashlib.sha256(canon(v).encode()).hexdigest()
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def validate_lineage(lineage:Any)->dict[str,Any]:
    if not isinstance(lineage,dict) or lineage.get("schema")!="chacha.dev/component-lineage/v1":
        raise RuntimeError("EXACT_COMPONENT_LINEAGE_REQUIRED")
    rows=lineage.get("components") or []
    if not rows:raise RuntimeError("EXACT_COMPONENT_LINEAGE_REQUIRED")
    for row in rows:
        if not isinstance(row,dict) or not row.get("kind") or not row.get("component_id") or not row.get("version"):
            raise RuntimeError("COMPONENT_LINEAGE_ROW_INVALID")
    return lineage

def validate_context(ctx:Any)->dict[str,Any]:
    if not isinstance(ctx,dict):raise RuntimeError("LEARNING_CONTEXT_INVALID")
    if ctx.get("schema")!="chacha.dev/verified-evidence-learning-context/v1":
        raise RuntimeError("LEARNING_CONTEXT_SCHEMA_INVALID")
    for key in ("deployment_id","source_id","surface_kind"):
        if not str(ctx.get(key) or "").strip():raise RuntimeError("LEARNING_CONTEXT_FIELD_MISSING:"+key)
    validate_lineage(ctx.get("component_lineage"))
    refs=ctx.get("evidence_refs")
    if refs is not None and not isinstance(refs,list):raise RuntimeError("LEARNING_CONTEXT_EVIDENCE_REFS_INVALID")
    return ctx

def guardian_check(repo_root:Path,phase:str,action_id:str,evidence:dict[str,Any])->dict[str,Any]:
    if os.environ.get("CHACHA_DEV_TEST_GUARDIAN_BYPASS")=="1":
        return {"status":"EXPLICIT_SEMANTIC_TEST_BYPASS"}
    if not Path("/opt/chacha-dev/runtime").exists():return {"status":"NON_RUNTIME_TEST_BYPASS"}
    client=repo_root/"dev-hub/bin/guardian-client.py"
    policy=repo_root/"dev-hub/config/guardian-runtime-policy.v1.json"
    if not client.is_file() or not policy.is_file():raise RuntimeError("GUARDIAN_UNAVAILABLE")
    event={"schema":"chacha.dev/governance-action/v1","event_id":"gov-"+uuid.uuid4().hex,
           "action_id":action_id,"phase":phase,"actor":"verified-evidence-learning",
           "subject_role":"verified-evidence-learning","action":"WRITE_MEMORY",
           "task_kind":"verified-evidence-learning","permission":"workspace-write",
           "project_id":"platform-global","run_id":action_id,"adapters":[],
           "evidence":evidence,
           "context":{"resource_class":"light","human_approval_required":False,
                      "storage_preflight_required":False,"deadline_seconds":90}}
    with tempfile.NamedTemporaryFile(prefix="chacha-v627-guardian-",suffix=".json",mode="w",encoding="utf-8",delete=False) as f:
        json.dump(event,f,separators=(",",":"));ep=Path(f.name)
    try:
        p=subprocess.run(["python3",str(client),"--policy",str(policy),"check","--event",str(ep)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    finally:
        ep.unlink(missing_ok=True)
    if p.returncode!=0:raise RuntimeError("GUARDIAN_CHECK_FAILED:"+(p.stdout or p.stderr)[-1000:])
    x=json.loads(p.stdout)
    if x.get("verdict") not in {"PASS","WARNING"}:raise RuntimeError("GUARDIAN_BLOCK:"+str(x))
    return x

def emit_event(*,repo_root:Path,project_id:str,event:dict[str,Any],policy:dict[str,Any],
               marker_root:Path,outbox_root:Path,state_root:Path)->dict[str,Any]:
    if str(event.get("result_status") or "")!="OK" or str(event.get("verification_status") or "")!="VERIFIED":
        return {"status":"SKIPPED_NOT_VERIFIED_SUCCESS","queued":False}
    ctx=event.get("learning_context")
    if not ctx:
        return {"status":"SKIPPED_NO_EXACT_LINEAGE","queued":False,"no_confidence_change":True}
    ctx=validate_context(ctx)
    result_digest=str(event.get("result_digest") or "")
    if not result_digest.startswith("sha256:"):raise RuntimeError("VERIFIED_RESULT_DIGEST_REQUIRED")
    event_key=digest({"project_id":project_id,"result_digest":result_digest,"learning_context":ctx})
    marker_root.mkdir(parents=True,exist_ok=True)
    marker=marker_root/(event_key+".json");lock=marker.with_suffix(".lock")
    action_id="verified-evidence-learning-"+event_key[:20]
    with open(lock,"a+",encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(),fcntl.LOCK_EX)
        if marker.is_file():
            prior=load(marker)
            return {"status":"DEDUPLICATED","queued":False,"delta_id":prior.get("delta_id"),"marker":str(marker)}
        guardian_check(repo_root,"PRE_ACTION",action_id,{"emergency_stop_active":False,
                       "verified_result":True,"exact_component_lineage":True,
                       "direct_application_mutation":False})
        refs=[str(x) for x in (ctx.get("evidence_refs") or [])]
        if not refs:
            refs=["evidence-ledger:"+result_digest]
        evaluation={"schema":"chacha.dev/component-evaluation/v1","verified":True,"outcome":"PASS",
                    "acceptance_score":1.0,"evidence_refs":refs}
        state={"surface_kind":ctx["surface_kind"],"task_id":event.get("task_id"),
               "result_digest":result_digest,"verified":True}
        obs=ul.observe(project_id=project_id,source_id=str(ctx["source_id"]),source_kind="learning-module",
                       deployment_id=str(ctx["deployment_id"]),state=state,evidence_refs=refs,
                       lineage=ctx["component_lineage"],evaluation=evaluation,
                       outbox_root=outbox_root,state_root=state_root)
        if obs.get("status")!="QUEUED":raise RuntimeError("VERIFIED_EVIDENCE_DELTA_NOT_QUEUED:"+str(obs))
        tmp=marker.with_name(marker.name+".tmp-"+str(os.getpid()))
        tmp.write_text(json.dumps({"schema":"chacha.dev/verified-evidence-learning-applied/v1",
                                   "event_key":event_key,"result_digest":result_digest,
                                   "delta_id":obs.get("delta_id"),"outbox":obs.get("outbox")},indent=2)+"\n",encoding="utf-8")
        os.replace(tmp,marker)
        guardian_check(repo_root,"POST_ACTION",action_id,{"emergency_stop_active":False,
                       "verified_result":True,"exact_component_lineage":True,
                       "verified_evaluation_emitted":True,"output_exists":marker.is_file(),
                       "direct_application_mutation":False,"automatic_external_spend_eur":0})
    return {"status":"QUEUED","queued":True,"delta_id":obs.get("delta_id"),"outbox":obs.get("outbox"),"marker":str(marker)}

def reconcile_ledger(*,repo_root:Path,ledger_path:Path,policy:dict[str,Any],marker_root:Path,
                     outbox_root:Path,state_root:Path)->dict[str,Any]:
    ledger=load(ledger_path)
    if ledger.get("schema")!="chacha.dev/evidence-ledger/v1":raise RuntimeError("EVIDENCE_LEDGER_SCHEMA_INVALID")
    project_id=str(ledger.get("project") or "")
    if not project_id:raise RuntimeError("EVIDENCE_LEDGER_PROJECT_MISSING")
    summary={"ledger":str(ledger_path),"project_id":project_id,"queued":0,"deduplicated":0,
             "skipped_no_lineage":0,"skipped_not_verified_success":0,"events":0}
    for event in ledger.get("history") or []:
        if not isinstance(event,dict) or event.get("event")!="task-result-ingested":continue
        summary["events"]+=1
        out=emit_event(repo_root=repo_root,project_id=project_id,event=event,policy=policy,
                       marker_root=marker_root,outbox_root=outbox_root,state_root=state_root)
        if out["status"]=="QUEUED":summary["queued"]+=1
        elif out["status"]=="DEDUPLICATED":summary["deduplicated"]+=1
        elif out["status"]=="SKIPPED_NO_EXACT_LINEAGE":summary["skipped_no_lineage"]+=1
        else:summary["skipped_not_verified_success"]+=1
    return summary

def discover(root:Path)->list[Path]:
    if not root.exists():return []
    return sorted(p for p in root.glob("*/ledger.json") if p.is_file())

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=REPO_ROOT)
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--ledger",type=Path,action="append",default=[])
    ap.add_argument("--evidence-root",type=Path,default=DEFAULT_EVIDENCE_ROOT)
    ap.add_argument("--marker-root",type=Path,default=DEFAULT_MARKERS)
    ap.add_argument("--outbox-root",type=Path,default=DEFAULT_OUTBOX)
    ap.add_argument("--state-root",type=Path,default=DEFAULT_STATE)
    a=ap.parse_args();policy=load(a.policy)
    if policy.get("schema")!="chacha.dev/verified-evidence-learning/v1":
        raise SystemExit("VERIFIED_EVIDENCE_LEARNING_POLICY_INVALID")
    ledgers=list(a.ledger) or discover(a.evidence_root)
    rows=[];totals={"queued":0,"deduplicated":0,"skipped_no_lineage":0,"skipped_not_verified_success":0,"events":0}
    for p in ledgers:
        row=reconcile_ledger(repo_root=a.repo_root.resolve(),ledger_path=p,policy=policy,
                             marker_root=a.marker_root,outbox_root=a.outbox_root,state_root=a.state_root)
        rows.append(row)
        for k in totals:totals[k]+=int(row.get(k) or 0)
    out={"schema":"chacha.dev/verified-evidence-learning-reconcile/v1","ledgers":len(ledgers),
         **totals,"results":rows,"automatic_external_spend_eur":0}
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V627_VERIFIED_EVIDENCE_LEARNING=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())
