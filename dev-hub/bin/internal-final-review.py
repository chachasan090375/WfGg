#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/compromise-agent-review/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def compromise_digest(comp:dict[str,Any])->str:
    return str(comp.get("dossier_digest") or digest(comp))

def logic_review(report,comp,impl,verify):
    hard=[];soft=[];refs=[]
    proposal=((comp.get("compromise") or {}).get("logic_proposal") or {}).get("candidate") or {}
    candidate_id=str(proposal.get("candidate_id") or "")
    execution_mode=str(proposal.get("execution_mode") or "")
    implemented=(impl.get("logic") or {})
    if not candidate_id:hard.append("LOGIC_COMPROMISE_CANDIDATE_MISSING")
    if str(implemented.get("candidate_id") or "")!=candidate_id:
        hard.append("LOGIC_IMPLEMENTED_CANDIDATE_MISMATCH")
    if execution_mode and str(implemented.get("execution_mode") or "")!=execution_mode:
        soft.append("LOGIC_EXECUTION_MODE_DRIFT")
    if verify.get("non_dominated_compromise_verified") is not True:
        hard.append("NON_DOMINATED_COMPROMISE_NOT_VERIFIED")
    if verify.get("hard_constraints_satisfied") is not True:
        hard.append("HARD_CONSTRAINTS_NOT_SATISFIED")
    original_digest=str(report.get("report_digest") or digest(report))
    refs.extend([original_digest,"logic-candidate:"+candidate_id] if candidate_id else [original_digest])
    verdict="ACCEPT" if not hard and not soft else "REVISE"
    return verdict,hard,soft,refs,candidate_id

def ux_review(report,comp,impl,verify):
    hard=[];soft=[];refs=[]
    ux=((comp.get("compromise") or {}).get("ux_proposal") or {}).get("ux_contract") or {}
    recs=[x for x in ux.get("recommendations") or [] if isinstance(x,dict)]
    required={str(x.get("id")) for x in recs if x.get("id")}
    implemented=set(map(str,(impl.get("ux") or {}).get("implemented_requirement_ids") or []))
    missing=sorted(required-implemented)
    if missing:hard.append("UX_REQUIREMENTS_MISSING:"+",".join(missing))
    if ux.get("primary_job_statement") and (impl.get("ux") or {}).get("primary_job_verified") is not True:
        hard.append("UX_PRIMARY_JOB_NOT_VERIFIED")
    if ux.get("curator_handoff_required") is True and (impl.get("ux") or {}).get("curator_handoff_completed") is not True:
        hard.append("CURATOR_HANDOFF_NOT_COMPLETED")
    if verify.get("hard_constraints_satisfied") is not True:
        hard.append("HARD_CONSTRAINTS_NOT_SATISFIED")
    original_digest=str(report.get("report_digest") or digest(report))
    refs.extend([original_digest,"ux-requirements:"+digest(sorted(required))])
    verdict="ACCEPT" if not hard and not soft else "REVISE"
    return verdict,hard,soft,refs,sorted(required)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--agent",choices=["logician","ergonomist"],required=True)
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--report",type=Path,required=True)
    ap.add_argument("--compromise",type=Path,required=True)
    ap.add_argument("--implementation-manifest",type=Path,required=True)
    ap.add_argument("--implementation-verification",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()

    report=load(a.report);comp=load(a.compromise);impl=load(a.implementation_manifest);verify=load(a.implementation_verification)
    cd=compromise_digest(comp)
    hard=[]

    if comp.get("schema")!="chacha.dev/multi-agent-compromise/v1":hard.append("COMPROMISE_SCHEMA_INVALID")
    if impl.get("schema")!="chacha.dev/implementation-manifest/v1":hard.append("IMPLEMENTATION_MANIFEST_SCHEMA_INVALID")
    if verify.get("schema")!="chacha.dev/implementation-verification/v1":hard.append("IMPLEMENTATION_VERIFICATION_SCHEMA_INVALID")
    for src,name in ((impl,"manifest"),(verify,"verification")):
        if str(src.get("project_id") or "")!=a.project_id:hard.append(name.upper()+"_PROJECT_MISMATCH")
        if str(src.get("revision") or "")!=a.revision:hard.append(name.upper()+"_REVISION_MISMATCH")
        if str(src.get("compromise_digest") or "")!=cd:hard.append(name.upper()+"_COMPROMISE_MISMATCH")
    if verify.get("status")!="PASS":hard.append("IMPLEMENTATION_NOT_VERIFIED")

    if a.agent=="logician":
        verdict,h2,soft,refs,subject=logic_review(report,comp,impl,verify)
        subject_ref={"candidate_id":subject}
    else:
        verdict,h2,soft,refs,subject=ux_review(report,comp,impl,verify)
        subject_ref={"required_ux_ids":subject}
    hard.extend(h2)
    if hard:verdict="REVISE"

    result={
      "schema":SCHEMA,"version":"1.0.0","agent":a.agent,
      "project_id":a.project_id,"revision":a.revision,"compromise_digest":cd,
      "verdict":verdict,"hard_objections":hard,"soft_objections":soft,
      "evidence_refs":refs+["implementation-manifest:"+digest(impl),"implementation-verification:"+digest(verify)],
      "implementation_verified":verify.get("status")=="PASS",
      "source_authority":"INTERNAL_SECOND_READ",
      "source_reverified":False,
      "original_proposal_referenced":True,
      "post_implementation_second_read":True,
      "subject":subject_ref,
      "direct_mutation":False,"reviewed_at":now()
    }
    result["review_digest"]=digest(result)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_INTERNAL_FINAL_REVIEW="+verdict)
    print("AGENT="+a.agent)
    print("POST_IMPLEMENTATION_SECOND_READ=YES")
    print("ORIGINAL_PROPOSAL_REFERENCED=YES")
    return 0 if verdict=="ACCEPT" else 20

if __name__=="__main__":raise SystemExit(main())
