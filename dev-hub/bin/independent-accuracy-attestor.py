#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/independent-accuracy-attestation/v1"
VERIFIER="v660-independent-accuracy-attestor"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def stable(x:Any)->str:
    return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def sha256_text(value:str)->str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def sha256_file(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verified_sha256_ref(value:Any)->bool:
    ref=str(value or "")
    if "#sha256:" not in ref:return False
    raw,digest=ref.rsplit("#sha256:",1)
    if len(digest)!=64:return False
    p=Path(raw)
    return p.is_file() and sha256_file(p)==digest

def run_dirs(runtime_root:Path)->list[Path]:
    root=runtime_root/"golden-path-runs"
    return sorted([p for p in root.iterdir() if p.is_dir()]) if root.is_dir() else []

def guardian_case(run:Path)->dict[str,Any]|None:
    contract_path=run/"planning/functional-contract.json"
    acceptance_path=run/"external-assurance/acceptance.json"
    receipt_path=run/"external-assurance/guardian-functional-receipt.json"
    if not all(p.is_file() for p in (contract_path,acceptance_path,receipt_path)):return None
    contract=load(contract_path);acceptance=load(acceptance_path);receipt=load(receipt_path)
    if contract.get("schema")!="chacha.dev/functional-contract/v1":return None
    if acceptance.get("schema")!="chacha.dev/acceptance-result/v1":return None
    if receipt.get("schema")!="chacha.dev/guardian-functional-acceptance-receipt/v1":return None
    amap={str(x.get("criterion_id")):x for x in (acceptance.get("criteria") or []) if isinstance(x,dict) and x.get("criterion_id")}
    required=[x for x in (contract.get("criteria") or []) if isinstance(x,dict) and x.get("required") is not False]
    reasons=[];passed=0;hashes_ok=True
    for criterion in required:
        cid=str(criterion.get("criterion_id") or "")
        row=amap.get(cid)
        if not row:
            reasons.append("REQUIRED_FUNCTIONAL_CRITERION_MISSING:"+cid);continue
        if str(row.get("state") or "")!="PASS":
            reasons.append("REQUIRED_FUNCTIONAL_CRITERION_NOT_PASS:"+cid);continue
        if not str(row.get("evidence") or ""):
            reasons.append("REQUIRED_FUNCTIONAL_EVIDENCE_MISSING:"+cid);continue
        if not verified_sha256_ref(row.get("evidence")):
            hashes_ok=False;reasons.append("REQUIRED_FUNCTIONAL_EVIDENCE_DIGEST_INVALID:"+cid);continue
        passed+=1
    if acceptance.get("accepted") is not True or acceptance.get("delivery_allowed") is not True:
        reasons.append("LOCAL_ACCEPTANCE_NOT_DELIVERABLE")
    digest=sha256_text(stable(contract))
    expected_verdict="PASS" if not reasons else "BLOCK"
    matched=(
      str(receipt.get("contract_id") or "")==str(contract.get("contract_id") or "") and
      str(receipt.get("contract_digest") or "")==digest and
      int(receipt.get("required_criteria_count") or 0)==len(required) and
      int(receipt.get("passed_required_criteria_count") or 0)==passed and
      str(receipt.get("verdict") or "")==expected_verdict and
      list(receipt.get("reason_codes") or [])==reasons and
      hashes_ok and
      str(receipt.get("guardian") or "")=="external-worker" and
      receipt.get("functional_scope_only") is True and
      receipt.get("direct_application_mutation") is False and
      receipt.get("central_orchestrator_owns_remediation") is True
    )
    return {
      "case_id":"guardian:"+str(receipt.get("receipt_id") or run.name),
      "project_id":receipt.get("project_id"),"revision":receipt.get("revision"),
      "passed":bool(matched),"expected_verdict":expected_verdict,"observed_verdict":receipt.get("verdict"),
      "contract_digest_recomputed":digest,"contract_digest_matches":str(receipt.get("contract_digest") or "")==digest,
      "required_criteria_count":len(required),"passed_required_criteria_count":passed,
      "evidence_hashes_verified":hashes_ok,
      "external_worker":str(receipt.get("guardian") or "")=="external-worker",
      "functional_scope_only":receipt.get("functional_scope_only") is True,
      "no_direct_mutation":receipt.get("direct_application_mutation") is False,
      "source_refs":[str(contract_path),str(acceptance_path),str(receipt_path)]
    }

def acceptance_case(run:Path)->dict[str,Any]|None:
    contract_path=run/"planning/functional-contract.json"
    acceptance_path=run/"external-assurance/acceptance.json"
    evidence_path=run/"external-assurance/acceptance-evidence.json"
    if not all(p.is_file() for p in (contract_path,acceptance_path,evidence_path)):return None
    contract=load(contract_path);acceptance=load(acceptance_path);evidence=load(evidence_path)
    if contract.get("schema")!="chacha.dev/functional-contract/v1" or acceptance.get("schema")!="chacha.dev/acceptance-result/v1":return None
    emap={str(x.get("criterion_id")):x for x in (evidence.get("criteria") or []) if isinstance(x,dict)}
    expected=[];routes={};hashes_ok=True
    for c in contract.get("criteria") or []:
        if not isinstance(c,dict):continue
        cid=str(c.get("criterion_id") or "");required=bool(c.get("required",True));e=emap.get(cid)
        state=str((e or {}).get("state") or "UNVERIFIED");passed=state=="PASS";eref=(e or {}).get("evidence")
        if state=="PASS" and not verified_sha256_ref(eref):hashes_ok=False
        expected.append({"criterion_id":cid,"dimension":c.get("dimension"),"required":required,
                         "owner":c.get("owner"),"state":state,"evidence":eref})
        if required and not passed:routes.setdefault(str(c.get("owner") or "core"),[]).append(cid)
    ok=not routes
    actual_rows=[x for x in (acceptance.get("criteria") or []) if isinstance(x,dict)]
    expected_gate={
      "accepted":ok,"return_to_factories":routes,"delivery_allowed":ok,"local_acceptance_candidate":ok,
      "final_delivery_allowed":False,"final_delivery_gate":"seven-agent-final-compromise","final_delivery_receipt_required":True
    }
    matched=(
      actual_rows==expected and hashes_ok and
      all(acceptance.get(k)==v for k,v in expected_gate.items())
    )
    return {
      "case_id":"acceptance:"+run.name,
      "passed":bool(matched),"expected_accepted":ok,"observed_accepted":acceptance.get("accepted"),
      "criteria_count":len(expected),"evidence_hashes_verified":hashes_ok,
      "final_gate_preserved":acceptance.get("final_delivery_gate")=="seven-agent-final-compromise",
      "source_refs":[str(contract_path),str(evidence_path),str(acceptance_path)]
    }

def fetch_github_json(url:str)->dict[str,Any]:
    req=urllib.request.Request(url,headers={
      "accept":"application/vnd.github+json","user-agent":"ChaCha-DEV-V660-Attestor/1.0",
      "x-github-api-version":"2022-11-28"
    })
    with urllib.request.urlopen(req,timeout=20) as r:
        x=json.loads(r.read().decode("utf-8"))
        if not isinstance(x,dict):raise ValueError("GITHUB_JSON_ROOT_NOT_OBJECT")
        return x

def fetch_github_sources(repository:str,run_id:str)->tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    base=f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
    return fetch_github_json(base),fetch_github_json(base+"/jobs"),fetch_github_json(base+"/artifacts")

def sentinel_case(run:Path,github_dir:Path|None,fetch_github:bool,source_dir:Path)->dict[str,Any]|None:
    receipt_path=run/"external-assurance/sentinel-technical-receipt.json"
    if not receipt_path.is_file():return None
    receipt=load(receipt_path)
    if receipt.get("schema")!="chacha.dev/sentinel-technical-receipt/v1":return None
    run_id=str(receipt.get("workflow_run_id") or "");repo=str(receipt.get("repository") or "")
    revision=str(receipt.get("revision") or "");workflow=str(receipt.get("workflow_name") or "")
    if not run_id or not repo or len(revision)!=40:return None
    run_path=(github_dir/(run_id+".json")) if github_dir else None
    jobs_path=(github_dir/(run_id+"-jobs.json")) if github_dir else None
    artifacts_path=(github_dir/(run_id+"-artifacts.json")) if github_dir else None
    if run_path and jobs_path and artifacts_path and all(p.is_file() for p in (run_path,jobs_path,artifacts_path)):
        gh=load(run_path);jobs=load(jobs_path);artifacts=load(artifacts_path)
    elif fetch_github:
        gh,jobs,artifacts=fetch_github_sources(repo,run_id)
        source_dir.mkdir(parents=True,exist_ok=True)
        run_path=source_dir/("github-run-"+run_id+".json")
        jobs_path=source_dir/("github-jobs-"+run_id+".json")
        artifacts_path=source_dir/("github-artifacts-"+run_id+".json")
        save(run_path,gh);save(jobs_path,jobs);save(artifacts_path,artifacts)
    else:return None

    repository_name=str(((gh.get("repository") or {}).get("full_name")) or repo)
    job_rows=[x for x in (jobs.get("jobs") or []) if isinstance(x,dict)]
    sentinel_jobs=[x for x in job_rows if str(x.get("name") or "")=="sentinel"]
    job=sentinel_jobs[0] if sentinel_jobs else None
    steps={str(x.get("name") or ""):x for x in ((job or {}).get("steps") or []) if isinstance(x,dict)}
    required_steps=[
      "External technical audit","Audit receipt","Enforce Sentinel verdict",
      "Persist and verify exact-revision Sentinel attestation"
    ]
    steps_ok=all(
      str((steps.get(name) or {}).get("status") or "")=="completed" and
      str((steps.get(name) or {}).get("conclusion") or "")=="success"
      for name in required_steps
    )
    artifact_name="chacha-dev-sentinel-technical-audit-"+revision
    artifact_rows=[x for x in (artifacts.get("artifacts") or []) if isinstance(x,dict)]
    matching_artifacts=[x for x in artifact_rows if str(x.get("name") or "")==artifact_name]
    artifact=matching_artifacts[0] if matching_artifacts else None
    artifact_workflow=(artifact or {}).get("workflow_run") or {}
    artifact_ok=(
      artifact is not None and artifact.get("expired") is False and
      str(artifact_workflow.get("id") or "")==run_id and
      str(artifact_workflow.get("head_sha") or "")==revision and
      str((artifact or {}).get("digest") or "").startswith("sha256:")
    )
    audit_digest=str(receipt.get("audit_digest") or "")
    checks={
      "workflow_id_matches":str(gh.get("id") or "")==run_id,
      "workflow_name_matches":str(gh.get("name") or "")==workflow,
      "workflow_revision_matches":str(gh.get("head_sha") or "")==revision,
      "workflow_completed_success":str(gh.get("status") or "")=="completed" and str(gh.get("conclusion") or "")=="success",
      "github_repository_matches":repository_name==repo,
      "sentinel_job_completed_success":job is not None and str(job.get("status") or "")=="completed" and str(job.get("conclusion") or "")=="success",
      "sentinel_job_revision_matches":job is not None and str(job.get("head_sha") or "")==revision,
      "required_assurance_steps_success":steps_ok,
      "technical_audit_artifact_bound":artifact_ok,
      "receipt_pass":str(receipt.get("verdict") or "")=="PASS",
      "d1_workflow_attestation":str(receipt.get("technical_verification_source") or "")=="D1_WORKFLOW_ATTESTATION",
      "external_worker":str(receipt.get("sentinel") or "")=="external-worker",
      "technical_scope_only":receipt.get("technical_scope_only") is True,
      "no_direct_mutation":receipt.get("direct_code_mutation") is False,
      "central_orchestrator_owns_remediation":receipt.get("central_orchestrator_owns_remediation") is True,
      "audit_digest_well_formed":audit_digest.startswith("sha256:") and len(audit_digest)==71
    }
    matched=all(checks.values())
    return {
      "case_id":"sentinel:"+str(receipt.get("receipt_id") or run.name),
      "project_id":receipt.get("project_id"),"revision":revision,
      "passed":bool(matched),"workflow_run_id":run_id,"checks":checks,
      "audit_digest":audit_digest,
      "artifact_name":artifact_name,"artifact_digest":(artifact or {}).get("digest"),
      "verification_model":"INDEPENDENT_GITHUB_RUN_JOB_STEPS_ARTIFACT_PLUS_D1_RECEIPT_BINDING",
      "source_refs":[str(receipt_path),str(run_path),str(jobs_path),str(artifacts_path)]
    }

def attestation(agent_id:str,cases:list[dict[str,Any]])->dict[str,Any]:
    total=len(cases);passed=sum(1 for x in cases if x.get("passed") is True)
    value=round(100.0*passed/total,1) if total else None
    source_refs=sorted({str(r) for c in cases for r in (c.get("source_refs") or [])})
    return {
      "schema":SCHEMA,"subject_agent":agent_id,"verifier":VERIFIER,
      "verification":"INDEPENDENTLY_ATTESTED","verification_scope":"REAL_RUNTIME",
      "generated_at":now_iso(),"case_count":total,"passed_case_count":passed,
      "accuracy_value":value,"production_truth_eligible":total>0,
      "source_refs":source_refs,"cases":cases,
      "decision_authority":False,"direct_mutation":False,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }

def build(runtime_root:Path,output_root:Path,github_dir:Path|None,fetch_github:bool)->dict[str,dict[str,Any]]:
    source_dir=output_root/"sources";cases={"guardian":[],"sentinel":[],"acceptance-engineer":[]}
    for run in run_dirs(runtime_root):
        g=guardian_case(run)
        if g:cases["guardian"].append(g)
        a=acceptance_case(run)
        if a:cases["acceptance-engineer"].append(a)
        s=sentinel_case(run,github_dir,fetch_github,source_dir)
        if s:cases["sentinel"].append(s)
    out={}
    for aid,rows in cases.items():
        item=attestation(aid,rows);out[aid]=item
        if rows:save(output_root/("accuracy-"+aid+".json"),item)
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime-root",type=Path,required=True)
    ap.add_argument("--output-root",type=Path,required=True)
    ap.add_argument("--github-run-dir",type=Path)
    ap.add_argument("--fetch-github",action="store_true")
    a=ap.parse_args()
    out=build(a.runtime_root.resolve(),a.output_root.resolve(),a.github_run_dir.resolve() if a.github_run_dir else None,a.fetch_github)
    for aid in ("guardian","sentinel","acceptance-engineer"):
        x=out[aid]
        print(aid.upper().replace("-","_")+"_CASES="+str(x["case_count"]))
        print(aid.upper().replace("-","_")+"_ACCURACY="+str(x["accuracy_value"]))
    ok=all(out[aid]["case_count"]>0 and out[aid]["passed_case_count"]==out[aid]["case_count"] for aid in out)
    print("CHACHA_DEV_V660_INDEPENDENT_ACCURACY_ATTESTATION="+("PASS" if ok else "BLOCK"))
    print("CHACHA_DEV_V660_DIRECT_MUTATION=NO")
    print("CHACHA_DEV_V660_CANONICAL_OBSERVATION_BUS_MUTATION=NO")
    print("CHACHA_DEV_V660_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("CHACHA_DEV_V660_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if ok else 20

if __name__=="__main__":
    raise SystemExit(main())
