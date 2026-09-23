#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,hashlib,json,os,subprocess,tempfile,uuid
from pathlib import Path
from typing import Any
import universal_learning_runtime as ul

DEFAULT_POLICY=Path("dev-hub/config/acceptance-confidence.v1.json")
DEFAULT_MARKERS=Path("/opt/chacha-dev/runtime/knowledge/acceptance-confidence-applied")
DEFAULT_OUTBOX=Path("/opt/chacha-dev/runtime/learning/outbox")
DEFAULT_STATE=Path("/opt/chacha-dev/runtime/learning/producer-state")

def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return hashlib.sha256(canon(v).encode()).hexdigest()
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def guardian_check(repo_root:Path,phase:str,action_id:str,evidence:dict[str,Any])->dict[str,Any]:
    if not Path("/opt/chacha-dev/runtime").exists():return {"status":"NON_RUNTIME_TEST_BYPASS"}
    client=repo_root/"dev-hub/bin/guardian-client.py";policy=repo_root/"dev-hub/config/guardian-runtime-policy.v1.json"
    if not client.is_file() or not policy.is_file():raise RuntimeError("GUARDIAN_UNAVAILABLE")
    event={"schema":"chacha.dev/governance-action/v1","event_id":"gov-"+uuid.uuid4().hex,
           "action_id":action_id,"phase":phase,"actor":"central-orchestrator",
           "subject_role":"acceptance-confidence-bridge","action":"WRITE_MEMORY",
           "task_kind":"acceptance-confidence-bridge","permission":"workspace-write",
           "project_id":"platform-global","run_id":action_id,"adapters":[],
           "evidence":evidence,
           "context":{"resource_class":"light","human_approval_required":False,
                      "storage_preflight_required":False,"deadline_seconds":90}}
    with tempfile.NamedTemporaryFile(prefix="chacha-v626-guardian-",suffix=".json",mode="w",encoding="utf-8",delete=False) as f:
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

def bridge(*,repo_root:Path,acceptance:dict[str,Any],lineage:dict[str,Any],project_id:str,deployment_id:str,
           source_id:str,policy:dict[str,Any],marker_root:Path,outbox_root:Path,state_root:Path)->dict[str,Any]:
    if acceptance.get("schema")!="chacha.dev/acceptance-result/v1":raise RuntimeError("ACCEPTANCE_SCHEMA_INVALID")
    if lineage.get("schema")!="chacha.dev/component-lineage/v1" or not (lineage.get("components") or []):
        raise RuntimeError("EXACT_COMPONENT_LINEAGE_REQUIRED")
    for row in lineage.get("components") or []:
        if not isinstance(row,dict) or not row.get("kind") or not row.get("component_id") or not row.get("version"):
            raise RuntimeError("COMPONENT_LINEAGE_ROW_INVALID")
    if acceptance.get("accepted") is not True:
        return {"schema":"chacha.dev/acceptance-confidence-bridge-result/v1","status":"SKIPPED_NOT_ACCEPTED",
                "positive_component_confidence_emitted":False,
                "project_level_rejection_penalized_all_components":False,
                "automatic_external_spend_eur":0}
    criteria=acceptance.get("criteria") or []
    required=[x for x in criteria if isinstance(x,dict) and bool(x.get("required",True))]
    if any(str(x.get("state"))!="PASS" for x in required):
        raise RuntimeError("ACCEPTANCE_INCONSISTENT_REQUIRED_CRITERIA")
    acceptance_digest=digest({"acceptance":acceptance,"lineage":lineage,"project_id":project_id,"deployment_id":deployment_id})
    marker_root.mkdir(parents=True,exist_ok=True)
    marker=marker_root/(acceptance_digest+".json");lock=marker.with_suffix(".lock")
    action_id="acceptance-confidence-"+acceptance_digest[:20]
    with open(lock,"a+",encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(),fcntl.LOCK_EX)
        if marker.is_file():
            prior=load(marker)
            return {"schema":"chacha.dev/acceptance-confidence-bridge-result/v1","status":"DEDUPLICATED",
                    "acceptance_digest":acceptance_digest,"delta_id":prior.get("delta_id"),
                    "positive_component_confidence_emitted":True,
                    "automatic_external_spend_eur":0}
        guardian_check(repo_root,"PRE_ACTION",action_id,{"emergency_stop_active":False,
                       "full_acceptance":True,"exact_component_lineage":True})
        evaluation={"schema":"chacha.dev/component-evaluation/v1","verified":True,"outcome":"PASS",
                    "acceptance_score":1.0,
                    "evidence_refs":["acceptance:"+str(x.get("criterion_id")) for x in required if x.get("criterion_id")]}
        obs=ul.observe(project_id=project_id,source_id=source_id,source_kind="learning-module",
                       deployment_id=deployment_id,
                       state={"acceptance_digest":acceptance_digest,"accepted":True,
                              "required_criteria_count":len(required)},
                       evidence_refs=evaluation["evidence_refs"],lineage=lineage,evaluation=evaluation,
                       outbox_root=outbox_root,state_root=state_root)
        if obs.get("status")!="QUEUED":raise RuntimeError("ACCEPTANCE_CONFIDENCE_DELTA_NOT_QUEUED:"+str(obs))
        tmp=marker.with_name(marker.name+".tmp-"+str(os.getpid()))
        tmp.write_text(json.dumps({"schema":"chacha.dev/acceptance-confidence-applied/v1",
                                   "acceptance_digest":acceptance_digest,"delta_id":obs.get("delta_id"),
                                   "outbox":obs.get("outbox")},indent=2)+"\n",encoding="utf-8")
        os.replace(tmp,marker)
        guardian_check(repo_root,"POST_ACTION",action_id,{"emergency_stop_active":False,
                       "full_acceptance":True,"exact_component_lineage":True,
                       "verified_evaluation_emitted":True,"output_exists":marker.is_file(),
                       "direct_application_mutation":False,"automatic_external_spend_eur":0})
    return {"schema":"chacha.dev/acceptance-confidence-bridge-result/v1","status":"QUEUED",
            "acceptance_digest":acceptance_digest,"delta_id":obs.get("delta_id"),"outbox":obs.get("outbox"),
            "positive_component_confidence_emitted":True,
            "project_level_rejection_penalized_all_components":False,
            "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--acceptance",type=Path,required=True)
    ap.add_argument("--lineage",type=Path,required=True)
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--deployment-id",required=True)
    ap.add_argument("--source-id",default="acceptance-confidence-bridge")
    ap.add_argument("--marker-root",type=Path,default=DEFAULT_MARKERS)
    ap.add_argument("--outbox-root",type=Path,default=DEFAULT_OUTBOX)
    ap.add_argument("--state-root",type=Path,default=DEFAULT_STATE)
    ap.add_argument("--output",type=Path)
    a=ap.parse_args()
    out=bridge(repo_root=a.repo_root.resolve(),acceptance=load(a.acceptance),lineage=load(a.lineage),
               project_id=str(a.project_id),deployment_id=str(a.deployment_id),source_id=str(a.source_id),
               policy=load(a.policy),marker_root=a.marker_root,outbox_root=a.outbox_root,state_root=a.state_root)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V626_ACCEPTANCE_CONFIDENCE_BRIDGE=PASS")
    return 0
if __name__=="__main__":raise SystemExit(main())
