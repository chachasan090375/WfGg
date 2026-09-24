#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA="chacha.dev/durable-capability-adoptions/v1"
CANDIDATE_SCHEMA="chacha.dev/capability-adoption-candidate/v1"
SUCCESS_SCHEMA="chacha.dev/capability-project-success/v1"
RECEIPT_SCHEMA="chacha.dev/durable-capability-adoption-receipt/v1"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def canon(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()

def digest_obj(v:Any)->str:
    return "sha256:"+hashlib.sha256(canon(v)).hexdigest()

def digest_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return "sha256:"+h.hexdigest()

def load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict):
        raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return v

def save(path:Path,v:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(v,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def atomic_save(path:Path,v:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(v,f,indent=2,ensure_ascii=False);f.write("\n");f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,path)
        dfd=os.open(str(path.parent),os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def empty_registry()->dict[str,Any]:
    return {
      "schema":REGISTRY_SCHEMA,"version":"1.0.0",
      "capabilities":{},"providers":{},"adapters":{},"adoptions":{},
      "history":[],"updated_at":now_iso(),"automatic_external_spend_eur":0
    }

def read_registry(path:Path)->dict[str,Any]:
    if not path.exists(): return empty_registry()
    v=load(path)
    if v.get("schema")!=REGISTRY_SCHEMA:
        raise SystemExit("DURABLE_REGISTRY_SCHEMA_INVALID")
    for key in ("capabilities","providers","adapters","adoptions"):
        if not isinstance(v.get(key),dict): raise SystemExit("DURABLE_REGISTRY_SECTION_INVALID:"+key)
    return v

def validate_candidate(candidate:dict[str,Any])->None:
    if candidate.get("schema")!=CANDIDATE_SCHEMA:
        raise SystemExit("ADOPTION_CANDIDATE_SCHEMA_INVALID")
    if candidate.get("source_kind") not in {"BUILT_ADAPTER","EXISTING_PROVIDER"}:
        raise SystemExit("ADOPTION_CANDIDATE_SOURCE_KIND_INVALID")
    for k in ("project_id","capability","provider","adapter"):
        if not str(candidate.get(k) or "").strip():
            raise SystemExit("ADOPTION_CANDIDATE_FIELD_MISSING:"+k)
    if float(candidate.get("automatic_external_spend_eur") or 0)!=0:
        raise SystemExit("ADOPTION_CANDIDATE_NONZERO_EXTERNAL_SPEND")

def validate_success(candidate:dict[str,Any],success:dict[str,Any],policy:dict[str,Any],
                     human_approval:dict[str,Any]|None)->None:
    if success.get("schema")!=SUCCESS_SCHEMA:
        raise SystemExit("PROJECT_SUCCESS_SCHEMA_INVALID")
    required={
      "project_id":candidate["project_id"],"capability":candidate["capability"],
      "provider":candidate["provider"],"adapter":candidate["adapter"]
    }
    for k,v in required.items():
        if success.get(k)!=v: raise SystemExit("PROJECT_SUCCESS_MISMATCH:"+k)
    if success.get("status")!="PASS" or success.get("project_success") is not True:
        raise SystemExit("PROJECT_SUCCESS_NOT_PASS")
    if success.get("verification_status")!=(policy.get("requirements") or {}).get("verification_status_required","VERIFIED"):
        raise SystemExit("PROJECT_SUCCESS_NOT_VERIFIED")
    if success.get("quality_gates_pass") is not True:
        raise SystemExit("PROJECT_SUCCESS_QUALITY_GATES_REQUIRED")
    if int(success.get("runtime_use_count") or 0)<1:
        raise SystemExit("PROJECT_SUCCESS_RUNTIME_USE_REQUIRED")
    if int(success.get("incident_count") or 0)!=0:
        raise SystemExit("PROJECT_SUCCESS_INCIDENT_FREE_REQUIRED")
    if success.get("technology_watch_revalidated") is not True:
        raise SystemExit("TECHNOLOGY_WATCH_REVALIDATION_REQUIRED")
    council=success.get("architecture_council") if isinstance(success.get("architecture_council"),dict) else {}
    if council.get("decision")!="APPROVED" or not council.get("decision_id"):
        raise SystemExit("ARCHITECTURE_COUNCIL_APPROVAL_REQUIRED")
    if float(success.get("automatic_external_spend_eur") or 0)!=0:
        raise SystemExit("PROJECT_SUCCESS_NONZERO_EXTERNAL_SPEND")
    refs=success.get("evidence_refs")
    if not isinstance(refs,list) or not refs:
        raise SystemExit("PROJECT_SUCCESS_EVIDENCE_REFS_REQUIRED")

    # V6.42: a project-success declaration is not self-authenticating. It must
    # be backed by a committed Project Control verify-result transaction and
    # the verified task result referenced by that transaction.
    receipt_path=Path(str(success.get("project_control_receipt") or ""))
    if not receipt_path.is_file():
        raise SystemExit("PROJECT_CONTROL_VERIFICATION_RECEIPT_REQUIRED")
    receipt=load(receipt_path)
    if receipt.get("schema")!="chacha.dev/control-transaction-receipt/v1":
        raise SystemExit("PROJECT_CONTROL_RECEIPT_SCHEMA_INVALID")
    if receipt.get("project")!=candidate["project_id"] or receipt.get("operation")!="verify-result":
        raise SystemExit("PROJECT_CONTROL_RECEIPT_SCOPE_INVALID")
    if receipt.get("status")!="COMMITTED" or receipt.get("verification_status")!="VERIFIED":
        raise SystemExit("PROJECT_CONTROL_VERIFICATION_NOT_COMMITTED")
    verified_path=Path(str(receipt.get("verified_result") or ""))
    if not verified_path.is_file():
        raise SystemExit("PROJECT_CONTROL_VERIFIED_RESULT_MISSING")
    verified=load(verified_path)
    if verified.get("project")!=candidate["project_id"] or verified.get("status")!="OK":
        raise SystemExit("PROJECT_CONTROL_VERIFIED_RESULT_SCOPE_INVALID")
    verification=verified.get("verification") if isinstance(verified.get("verification"),dict) else {}
    if verification.get("status")!="VERIFIED":
        raise SystemExit("PROJECT_CONTROL_VERIFIED_RESULT_STATUS_INVALID")
    expected_task=str(success.get("verified_task_id") or "")
    if expected_task and verified.get("task_id")!=expected_task:
        raise SystemExit("PROJECT_CONTROL_VERIFIED_TASK_MISMATCH")

    claims_path=Path(str(success.get("verified_claims_path") or ""))
    declared_claims_digest=str(success.get("verified_claims_digest") or "")
    if not claims_path.is_file() or not declared_claims_digest.startswith("sha256:"):
        raise SystemExit("PROJECT_SUCCESS_VERIFIED_CLAIMS_REQUIRED")
    if digest_file(claims_path)!=declared_claims_digest:
        raise SystemExit("PROJECT_SUCCESS_CLAIMS_DIGEST_INVALID")
    claims=load(claims_path)
    claim_keys=(
      "project_id","capability","provider","adapter","status","project_success",
      "quality_gates_pass","runtime_use_count","incident_count",
      "technology_watch_revalidated","architecture_council",
      "automatic_external_spend_eur","evidence_refs"
    )
    for key in claim_keys:
        if claims.get(key)!=success.get(key):
            raise SystemExit("PROJECT_SUCCESS_CLAIMS_MISMATCH:"+key)
    evidence=verified.get("evidence") if isinstance(verified.get("evidence"),list) else []
    matched=False
    try: claims_resolved=str(claims_path.resolve())
    except Exception: claims_resolved=str(claims_path)
    for item in evidence:
        if not isinstance(item,dict): continue
        src=Path(str(item.get("source") or ""))
        try: src_value=str(src.resolve())
        except Exception: src_value=str(src)
        if src_value==claims_resolved and item.get("digest")==declared_claims_digest:
            matched=True;break
    if not matched:
        raise SystemExit("PROJECT_SUCCESS_CLAIMS_NOT_IN_VERIFIED_RESULT")

    ledger_path=Path(str(success.get("project_control_ledger") or ""))
    if not ledger_path.is_file():
        raise SystemExit("PROJECT_CONTROL_EVIDENCE_LEDGER_REQUIRED")
    ledger=load(ledger_path)
    if ledger.get("schema")!="chacha.dev/evidence-ledger/v1" or ledger.get("project")!=candidate["project_id"]:
        raise SystemExit("PROJECT_CONTROL_EVIDENCE_LEDGER_SCOPE_INVALID")
    if receipt.get("new_ledger_digest")!=digest_obj(ledger):
        raise SystemExit("PROJECT_CONTROL_LEDGER_DIGEST_MISMATCH")
    artifact_id=str(success.get("verified_success_artifact_id") or ("capability-project-success:"+candidate["capability"]))
    artifact=(ledger.get("artifacts") or {}).get(artifact_id)
    if not isinstance(artifact,dict):
        raise SystemExit("PROJECT_CONTROL_SUCCESS_ARTIFACT_MISSING")
    verified_digest=digest_obj(verified)
    if artifact.get("status")!="OK" or artifact.get("digest")!=verified_digest:
        raise SystemExit("PROJECT_CONTROL_SUCCESS_ARTIFACT_INVALID")
    if expected_task and artifact.get("task_id")!=expected_task:
        raise SystemExit("PROJECT_CONTROL_SUCCESS_ARTIFACT_TASK_MISMATCH")
    history=ledger.get("history") or []
    if not any(isinstance(row,dict)
               and row.get("event")=="task-result-ingested"
               and row.get("task_id")==verified.get("task_id")
               and row.get("result_digest")==verified_digest
               and row.get("verification_status")=="VERIFIED"
               for row in history):
        raise SystemExit("PROJECT_CONTROL_LEDGER_HISTORY_PROOF_MISSING")

    protected=bool(candidate.get("production_capable") or candidate.get("credentials_required") or candidate.get("network_access"))
    if protected:
        a=human_approval or {}
        actor=str(a.get("actor") or "")
        agents={"central-orchestrator","guardian","sentinel","curator","bastion","intendant","logician","ergonomist"}
        if a.get("schema")!="chacha.dev/capability-durable-adoption-approval/v1":
            raise SystemExit("DURABLE_ADOPTION_HUMAN_APPROVAL_REQUIRED")
        if a.get("capability")!=candidate["capability"] or a.get("target_status")!="ADOPT":
            raise SystemExit("DURABLE_ADOPTION_HUMAN_APPROVAL_SCOPE_INVALID")
        if not actor or actor in agents:
            raise SystemExit("DURABLE_ADOPTION_HUMAN_ACTOR_INVALID")

def validate_build_result(candidate:dict[str,Any])->dict[str,Any]:
    p=Path(str(candidate.get("build_result") or ""))
    if not p.is_file(): raise SystemExit("BUILD_RESULT_MISSING")
    b=load(p)
    if b.get("schema")!="chacha.dev/capability-build-result/v1":
        raise SystemExit("BUILD_RESULT_SCHEMA_INVALID")
    if b.get("status")!="PASS" or b.get("adapter_status")!="ENABLED":
        raise SystemExit("BUILD_RESULT_NOT_ENABLED_PASS")
    if b.get("same_project_resume_allowed") is not True:
        raise SystemExit("BUILD_RESULT_NOT_RESUMABLE")
    if b.get("durable_adoption")!="PENDING_PROJECT_SUCCESS":
        raise SystemExit("BUILD_RESULT_ADOPTION_STATE_INVALID")
    for k in ("capability","provider","adapter"):
        if b.get(k)!=candidate.get(k): raise SystemExit("BUILD_RESULT_MISMATCH:"+k)
    if bool(b.get("production_capable"))!=bool(candidate.get("production_capable")):
        raise SystemExit("BUILD_RESULT_PRODUCTION_FLAG_MISMATCH")
    if bool(b.get("network_access"))!=bool(candidate.get("network_access")):
        raise SystemExit("BUILD_RESULT_NETWORK_FLAG_MISMATCH")
    if bool(b.get("credentials_required"))!=bool(candidate.get("credentials_required")):
        raise SystemExit("BUILD_RESULT_CREDENTIAL_FLAG_MISMATCH")
    if float(b.get("automatic_external_spend_eur") or 0)!=0:
        raise SystemExit("BUILD_RESULT_NONZERO_EXTERNAL_SPEND")
    source=Path(str(b.get("generated_source") or ""))
    sandbox=Path(str(b.get("sandbox_executable") or ""))
    if not source.is_file() or digest_file(source)!=b.get("generated_source_digest"):
        raise SystemExit("BUILD_RESULT_SOURCE_DIGEST_INVALID")
    if not sandbox.is_file() or digest_file(sandbox)!=b.get("sandbox_executable_digest"):
        raise SystemExit("BUILD_RESULT_SANDBOX_DIGEST_INVALID")
    artifacts=b.get("artifacts") if isinstance(b.get("artifacts"),dict) else {}
    for key in ("provisioning_receipt","pilot_receipt","enabled_receipt","enablement_evidence"):
        ep=Path(str(artifacts.get(key) or ""))
        if not ep.is_file(): raise SystemExit("BUILD_RESULT_EVIDENCE_MISSING:"+key)
    return b

def durable_provision(*,repo_root:Path,build:dict[str,Any],adapter_root:Path,work:Path,actor:str)->dict[str,Any]:
    source=Path(str(build["generated_source"]))
    adapter=str(build["adapter"]);provider=str(build["provider"]);capability=str(build["capability"])
    fixture=load(Path(str((build.get("artifacts") or {}).get("fixture") or "")))
    digest=build["generated_source_digest"].split(":",1)[1]
    version="v642-"+digest[:16]

    stage=work/"provision-stage"
    (stage/"dev-hub/bin").mkdir(parents=True,exist_ok=True)
    (stage/"dev-hub/generated/v642").mkdir(parents=True,exist_ok=True)
    shutil.copy2(repo_root/"dev-hub/bin/adapter-provision.py",stage/"dev-hub/bin/adapter-provision.py")
    staged_source=stage/"dev-hub/generated/v642"/(adapter+".py")
    shutil.copy2(source,staged_source);os.chmod(staged_source,0o755)
    policy={
      "schema":"chacha.dev/adapter-provisioning/v1",
      "target_root":str(adapter_root),"sandbox_root_override_allowed":False,
      "probe_timeout_seconds":10,
      "adapters":{
        adapter:{
          "source":"dev-hub/generated/v642/"+adapter+".py",
          "namespace":provider,"version":version,"executable_name":adapter,
          "mode":"0755","current_link_name":"current",
          "probe":{"input":fixture,"expected_schema":"chacha.dev/task-result/v1",
                   "expected_status":"OK","expected_producer":adapter,
                   "expected_verification_status":"UNVERIFIED"}
        }
      }
    }
    pp=stage/"provision.json";save(pp,policy)
    receipt=work/"durable-provisioning-receipt.json"
    script=stage/"dev-hub/bin/adapter-provision.py"
    def call(args):
        p=subprocess.run([sys.executable,str(script),*map(str,args)],cwd=str(stage),
                         text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        if p.returncode!=0:
            raise SystemExit("DURABLE_PROVISION_FAILED:"+(p.stderr or p.stdout)[-3000:])
        return p
    call(["--policy",pp,"apply","--adapter",adapter,"--actor",actor,"--receipt",receipt,"--apply"])
    call(["--policy",pp,"verify","--adapter",adapter,"--receipt",receipt])
    r=load(receipt)
    if r.get("executable_digest")!=build.get("generated_source_digest"):
        raise SystemExit("DURABLE_EXECUTABLE_DIGEST_MISMATCH")
    return r

def archive_source(source:Path,archive_root:Path,adoption_id:str,expected_digest:str)->Path:
    archive_root.mkdir(parents=True,exist_ok=True)
    target=archive_root/(adoption_id+".py")
    if target.exists():
        if digest_file(target)!=expected_digest: raise SystemExit("SOURCE_ARCHIVE_COLLISION")
        return target
    fd,tmp=tempfile.mkstemp(prefix=target.name+".",suffix=".tmp",dir=str(archive_root))
    try:
        with os.fdopen(fd,"wb") as dst,source.open("rb") as src:
            shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
        os.chmod(tmp,0o644);os.replace(tmp,target)
        dfd=os.open(str(archive_root),os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    if digest_file(target)!=expected_digest: raise SystemExit("SOURCE_ARCHIVE_DIGEST_MISMATCH")
    return target

def adoption_id(candidate:dict[str,Any],success:dict[str,Any])->str:
    raw={"project_id":candidate["project_id"],"capability":candidate["capability"],
         "provider":candidate["provider"],"adapter":candidate["adapter"],
         "success_digest":digest_obj(success)}
    return "adopt-"+hashlib.sha256(canon(raw)).hexdigest()[:24]

def verify_existing_provider(candidate:dict[str,Any],base_provider:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    providers=base_provider.get("providers") or {};adapters=base_provider.get("adapters") or {}
    p=providers.get(candidate["provider"]);a=adapters.get(candidate["adapter"])
    if not isinstance(p,dict) or p.get("adapter")!=candidate["adapter"]:
        raise SystemExit("EXISTING_PROVIDER_BINDING_INVALID")
    if not isinstance(a,dict) or a.get("status")!="ENABLED":
        raise SystemExit("EXISTING_PROVIDER_ADAPTER_NOT_ENABLED")
    protected=set((policy.get("protected_adapter_permissions") or []))
    supports=set(a.get("supports") or [])
    if bool(supports & protected)!=bool(candidate.get("production_capable")):
        raise SystemExit("EXISTING_PROVIDER_PRODUCTION_FLAG_MISMATCH")
    return {"provider":p,"adapter":a}

def memory_event(candidate:dict[str,Any],success:dict[str,Any],adopt_id:str,receipt_path:Path)->dict[str,Any]:
    return {
      "schema":"chacha.dev/experience-event/v1",
      "observed_at":now_iso(),"project_id":candidate["project_id"],
      "learner":"capability-durable-adoption",
      "intent_signature":"capability-reuse:"+candidate["capability"],
      "context_signature":"provider:"+candidate["provider"]+"|adapter:"+candidate["adapter"],
      "outcome":"success","acceptance_score":1.0,"external_spend_eur":0,
      "capability":candidate["capability"],"provider":candidate["provider"],"adapter":candidate["adapter"],
      "adoption_id":adopt_id,"project_success_verified":True,
      "technology_watch_revalidated":True,
      "architecture_council_decision_id":(success.get("architecture_council") or {}).get("decision_id"),
      "evidence_refs":[*success.get("evidence_refs",[]),str(receipt_path)],
      "raw_user_content":False,"secrets_included":False
    }

def run_memory(*,repo_root:Path,event:dict[str,Any],work:Path,experience_db:Path,
               memory_db:Path|None,memory_snapshot:Path|None,nas:bool)->dict[str,Any]:
    event_path=work/"experience-event.json";save(event_path,event)
    cmd=[sys.executable,str(repo_root/"dev-hub/bin/experience-ledger.py"),"--db",str(experience_db),
         "record","--event",str(event_path)]
    if nas:cmd.append("--nas")
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if p.returncode!=0:raise SystemExit("EXPERIENCE_LEDGER_FAILED:"+(p.stderr or p.stdout)[-2000:])
    out=json.loads(p.stdout)
    if nas and (out.get("nas") or {}).get("status")!="PERSISTED":
        raise SystemExit("EXPERIENCE_LEDGER_NAS_NOT_PERSISTED")
    result={"experience":out,"event":str(event_path)}
    if memory_db is not None and memory_snapshot is not None:
        cmd=[sys.executable,str(repo_root/"dev-hub/bin/central-memory-assimilator.py"),
             "--policy",str(repo_root/"dev-hub/config/central-memory-assimilation.v1.json"),
             "--experience-db",str(experience_db),"--db",str(memory_db),"--snapshot",str(memory_snapshot)]
        if nas:cmd.append("--nas")
        p=subprocess.run(cmd,cwd=str(repo_root),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        if p.returncode!=0:raise SystemExit("CENTRAL_MEMORY_REFRESH_FAILED:"+(p.stderr or p.stdout)[-2000:])
        raw=p.stdout
        marker="\nCHACHA_DEV_V622_CENTRAL_MEMORY_ASSIMILATION=PASS"
        payload=raw.split(marker,1)[0].strip()
        result["central_memory"]=json.loads(payload) if payload.startswith("{") else {"status":"PASS"}
        result["snapshot"]=str(memory_snapshot)
    return result

def merge_registries(base_caps:dict[str,Any],base_provider:dict[str,Any],durable:dict[str,Any],
                     require_executables:bool,trust_snapshot:dict[str,Any]|None=None,
                     trust_policy:dict[str,Any]|None=None)->tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    caps=copy.deepcopy(base_caps);providers=copy.deepcopy(base_provider)
    valid=[];quarantined=[]
    trust_index={}
    if isinstance(trust_snapshot,dict):
        for item in trust_snapshot.get("items") or []:
            if not isinstance(item,dict) or item.get("component_kind")!="capability":continue
            trust_index[(str(item.get("component_id") or ""),str(item.get("version") or ""))]=item
    reuse_policy=(trust_policy or {}).get("reuse") if isinstance(trust_policy,dict) else {}
    blocked_trust_states=set((reuse_policy or {}).get("blocked_states") or ["DEGRADED","QUARANTINED","RECOVERY_CANDIDATE"])
    for aid,row in sorted((durable.get("adoptions") or {}).items()):
        if not isinstance(row,dict) or row.get("status")!="ADOPTED":continue
        cap=str(row.get("capability") or "");provider=str(row.get("provider") or "");adapter=str(row.get("adapter") or "")
        ce=(durable.get("capabilities") or {}).get(cap)
        pe=(durable.get("providers") or {}).get(provider)
        ae=(durable.get("adapters") or {}).get(adapter)
        origin=str(row.get("provider_origin") or "")
        reasons=[]
        if not isinstance(ce,dict):reasons.append("CAPABILITY_ENTRY_MISSING")
        if origin=="DURABLE_BUILT":
            if not isinstance(pe,dict):reasons.append("PROVIDER_ENTRY_MISSING")
            if not isinstance(ae,dict):reasons.append("ADAPTER_ENTRY_MISSING")
            elif ae.get("status")!="ENABLED":reasons.append("ADAPTER_NOT_ENABLED")
            elif require_executables:
                ex=Path(str(ae.get("executable") or ""))
                if not ex.is_file() or not os.access(ex,os.X_OK):reasons.append("EXECUTABLE_UNAVAILABLE")
                elif row.get("executable_digest") and digest_file(ex)!=row.get("executable_digest"):
                    reasons.append("EXECUTABLE_DIGEST_INVALID")
        elif origin=="BASE_EXISTING":
            bp=(providers.get("providers") or {}).get(provider)
            ba=(providers.get("adapters") or {}).get(adapter)
            if not isinstance(bp,dict) or bp.get("adapter")!=adapter:reasons.append("BASE_PROVIDER_UNAVAILABLE")
            if not isinstance(ba,dict) or ba.get("status")!="ENABLED":reasons.append("BASE_ADAPTER_NOT_ENABLED")
        else:reasons.append("PROVIDER_ORIGIN_INVALID")
        trust_item=trust_index.get((cap,aid))
        trust_state=str((trust_item or {}).get("state") or "UNKNOWN")
        if trust_state in blocked_trust_states:
            reasons.append("CAPABILITY_TRUST_BLOCKED:"+trust_state)
        if reasons:
            quarantined.append({"adoption_id":aid,"capability":cap,"trust_state":trust_state,
                                "reason_codes":reasons});continue
        caps.setdefault("capabilities",{})[cap]=copy.deepcopy(ce)
        caps["capabilities"][cap]["trust_state"]=trust_state
        caps["capabilities"][cap]["trust_is_advisory"]=True
        caps["capabilities"][cap]["technology_revalidation_required"]=True
        if origin=="DURABLE_BUILT":
            providers.setdefault("providers",{})[provider]=copy.deepcopy(pe)
            providers.setdefault("adapters",{})[adapter]=copy.deepcopy(ae)
        valid.append({"adoption_id":aid,"capability":cap,"trust_state":trust_state})
    return caps,providers,{"valid_adoptions":valid,"quarantined":quarantined,
                           "trust_filter_applied":bool(trust_index),
                           "trusted_does_not_escalate_permissions":True}

def adopt(args)->dict[str,Any]:
    policy=load(args.policy);candidate=load(args.candidate);success=load(args.success)
    if policy.get("schema")!="chacha.dev/durable-capability-adoption-policy/v1":
        raise SystemExit("DURABLE_ADOPTION_POLICY_INVALID")
    validate_candidate(candidate)
    approval=load(args.human_approval) if args.human_approval else None
    validate_success(candidate,success,policy,approval)
    durable=read_registry(args.registry)
    base_provider=load(args.base_provider_registry)
    if base_provider.get("schema")!="chacha.dev/provider-adapters/v1":raise SystemExit("BASE_PROVIDER_REGISTRY_INVALID")
    base_caps=load(args.base_capability_registry)
    if base_caps.get("schema")!="chacha.dev/capability-registry/v1":raise SystemExit("BASE_CAPABILITY_REGISTRY_INVALID")

    aid=adoption_id(candidate,success)
    prior=(durable.get("adoptions") or {}).get(aid)
    if isinstance(prior,dict) and prior.get("status")=="ADOPTED":
        receipt={"schema":RECEIPT_SCHEMA,"status":"IDEMPOTENT","adoption_id":aid,
                 "applied":False,"capability":candidate["capability"],"provider":candidate["provider"],
                 "adapter":candidate["adapter"],"observed_at":now_iso()}
        save(args.receipt,receipt);return receipt
    for existing_id,row in (durable.get("adoptions") or {}).items():
        if not isinstance(row,dict) or row.get("status")!="ADOPTED":continue
        if row.get("capability")==candidate["capability"] and existing_id!=aid:
            raise SystemExit("DURABLE_CAPABILITY_CONFLICT")

    work=Path(tempfile.mkdtemp(prefix="chacha-v642-adopt-"))
    original=copy.deepcopy(durable)
    try:
        provider_origin="BASE_EXISTING"
        provision=None;archive=None
        if candidate["source_kind"]=="BUILT_ADAPTER":
            build=validate_build_result(candidate)
            provision=durable_provision(repo_root=args.repo_root,build=build,adapter_root=args.adapter_root,work=work,actor=args.actor)
            archive=archive_source(Path(build["generated_source"]),args.source_archive_root,aid,build["generated_source_digest"])
            provider_origin="DURABLE_BUILT"
            durable["providers"][candidate["provider"]]={
              "adapter":candidate["adapter"],"kind":"generated-safe-local-runtime","execution":"vps",
              "adoption_id":aid
            }
            durable["adapters"][candidate["adapter"]]={
              "status":"ENABLED","executable":provision["executable_path"],"supports":["read"],
              "adoption_id":aid,"source_archive":str(archive),
              "source_digest":build["generated_source_digest"],
              "executable_digest":provision["executable_digest"]
            }
        else:
            verify_existing_provider(candidate,base_provider,policy)

        durable["capabilities"][candidate["capability"]]={
          "class":"execution",
          "providers":[{
            "id":candidate["provider"],"status":"ADOPT","health":"runtime-check",
            "cost_class":"included","scope":"platform-durable","fallback":[]
          }],
          "generated_by":"durable-capability-adoption",
          "promotion_state":"ADOPT","selected_adapter":candidate["adapter"],
          "adoption_id":aid,"automatic_external_spend_eur":0
        }
        adoption={
          "adoption_id":aid,"status":"ADOPTED","project_id":candidate["project_id"],
          "capability":candidate["capability"],"provider":candidate["provider"],"adapter":candidate["adapter"],
          "provider_origin":provider_origin,"source_kind":candidate["source_kind"],
          "project_success_digest":digest_obj(success),
          "technology_watch_revalidated":True,
          "architecture_council_decision_id":(success.get("architecture_council") or {}).get("decision_id"),
          "production_capable":bool(candidate.get("production_capable")),
          "network_access":bool(candidate.get("network_access")),
          "credentials_required":bool(candidate.get("credentials_required")),
          "automatic_external_spend_eur":0,
          "source_archive":str(archive) if archive else None,
          "source_digest":(provision or {}).get("source_digest"),
          "executable":(provision or {}).get("executable_path"),
          "executable_digest":(provision or {}).get("executable_digest"),
          "evidence_refs":success.get("evidence_refs") or [],
          "adopted_at":now_iso()
        }
        durable["adoptions"][aid]=adoption
        durable.setdefault("history",[]).append({"event":"ADOPT","adoption_id":aid,"observed_at":now_iso(),"actor":args.actor})
        durable["updated_at"]=now_iso()
        durable["automatic_external_spend_eur"]=0

        if not args.apply: raise SystemExit("DURABLE_ADOPTION_EXPLICIT_APPLY_REQUIRED")
        atomic_save(args.registry,durable)

        receipt={
          "schema":RECEIPT_SCHEMA,"status":"COMMITTED","adoption_id":aid,"applied":True,
          "capability":candidate["capability"],"provider":candidate["provider"],"adapter":candidate["adapter"],
          "provider_origin":provider_origin,"registry":str(args.registry),
          "registry_digest":digest_file(args.registry),
          "source_archive":str(archive) if archive else None,
          "durable_executable":(provision or {}).get("executable_path"),
          "durable_executable_digest":(provision or {}).get("executable_digest"),
          "project_success_digest":digest_obj(success),"observed_at":now_iso(),
          "automatic_external_spend_eur":0
        }
        save(args.receipt,receipt)

        mem=run_memory(repo_root=args.repo_root,event=memory_event(candidate,success,aid,args.receipt),
                       work=args.evidence_root/aid,experience_db=args.experience_db,
                       memory_db=args.central_memory_db if args.memory_refresh else None,
                       memory_snapshot=args.central_memory_snapshot if args.memory_refresh else None,
                       nas=args.nas)
        receipt["memory"]=mem
        save(args.receipt,receipt)
        return receipt
    except BaseException:
        if args.registry.exists():
            atomic_save(args.registry,original)
        raise
    finally:
        shutil.rmtree(work,ignore_errors=True)

def rollback(args)->dict[str,Any]:
    durable=read_registry(args.registry)
    row=(durable.get("adoptions") or {}).get(args.adoption_id)
    if not isinstance(row,dict) or row.get("status")!="ADOPTED":
        receipt={"schema":RECEIPT_SCHEMA,"status":"IDEMPOTENT_ROLLBACK","adoption_id":args.adoption_id,
                 "applied":False,"observed_at":now_iso()}
        save(args.receipt,receipt);return receipt
    cap=row["capability"];provider=row["provider"];adapter=row["adapter"]
    durable.get("capabilities",{}).pop(cap,None)
    # Remove provider/adapter only if no other active adoption references them.
    others=[x for k,x in (durable.get("adoptions") or {}).items()
            if k!=args.adoption_id and isinstance(x,dict) and x.get("status")=="ADOPTED"]
    if row.get("provider_origin")=="DURABLE_BUILT":
        if not any(x.get("provider")==provider for x in others):durable.get("providers",{}).pop(provider,None)
        if not any(x.get("adapter")==adapter for x in others):durable.get("adapters",{}).pop(adapter,None)
    row["status"]="ROLLED_BACK";row["rolled_back_at"]=now_iso();row["rollback_actor"]=args.actor
    durable["adoptions"][args.adoption_id]=row
    durable.setdefault("history",[]).append({"event":"ROLLBACK","adoption_id":args.adoption_id,
                                             "observed_at":now_iso(),"actor":args.actor})
    durable["updated_at"]=now_iso()
    if not args.apply:raise SystemExit("DURABLE_ROLLBACK_EXPLICIT_APPLY_REQUIRED")
    atomic_save(args.registry,durable)
    receipt={"schema":RECEIPT_SCHEMA,"status":"ROLLED_BACK","adoption_id":args.adoption_id,
             "applied":True,"capability":cap,"provider":provider,"adapter":adapter,
             "adapter_binary_retained_for_forensics":True,"observed_at":now_iso()}
    save(args.receipt,receipt);return receipt

def main()->int:
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="cmd",required=True)

    m=sub.add_parser("merge")
    m.add_argument("--base-capability-registry",type=Path,required=True)
    m.add_argument("--base-provider-registry",type=Path,required=True)
    m.add_argument("--registry",type=Path,required=True)
    m.add_argument("--output-capabilities",type=Path,required=True)
    m.add_argument("--output-providers",type=Path,required=True)
    m.add_argument("--require-executables",action="store_true")
    m.add_argument("--trust-snapshot",type=Path)
    m.add_argument("--trust-policy",type=Path)

    a=sub.add_parser("adopt")
    a.add_argument("--policy",type=Path,required=True);a.add_argument("--candidate",type=Path,required=True)
    a.add_argument("--success",type=Path,required=True);a.add_argument("--human-approval",type=Path)
    a.add_argument("--base-capability-registry",type=Path,required=True)
    a.add_argument("--base-provider-registry",type=Path,required=True)
    a.add_argument("--registry",type=Path,required=True);a.add_argument("--repo-root",type=Path,required=True)
    a.add_argument("--adapter-root",type=Path,required=True);a.add_argument("--source-archive-root",type=Path,required=True)
    a.add_argument("--evidence-root",type=Path,required=True);a.add_argument("--experience-db",type=Path,required=True)
    a.add_argument("--central-memory-db",type=Path);a.add_argument("--central-memory-snapshot",type=Path)
    a.add_argument("--memory-refresh",action="store_true");a.add_argument("--nas",action="store_true")
    a.add_argument("--actor",required=True);a.add_argument("--receipt",type=Path,required=True);a.add_argument("--apply",action="store_true")

    r=sub.add_parser("rollback")
    r.add_argument("--registry",type=Path,required=True);r.add_argument("--adoption-id",required=True)
    r.add_argument("--actor",required=True);r.add_argument("--receipt",type=Path,required=True);r.add_argument("--apply",action="store_true")

    v=sub.add_parser("verify")
    v.add_argument("--registry",type=Path,required=True)

    args=ap.parse_args()
    if args.cmd=="merge":
        base_caps=load(args.base_capability_registry);base_provider=load(args.base_provider_registry)
        durable=read_registry(args.registry)
        trust_snapshot=load(args.trust_snapshot) if args.trust_snapshot and args.trust_snapshot.is_file() else None
        trust_policy=load(args.trust_policy) if args.trust_policy and args.trust_policy.is_file() else None
        caps,providers,report=merge_registries(base_caps,base_provider,durable,args.require_executables,
                                              trust_snapshot=trust_snapshot,trust_policy=trust_policy)
        save(args.output_capabilities,caps);save(args.output_providers,providers)
        print("CHACHA_DEV_V642_DURABLE_REGISTRY_MERGE=PASS")
        print("CHACHA_DEV_V642_DURABLE_REUSE_COUNT="+str(len(report["valid_adoptions"])))
        print("CHACHA_DEV_V642_DURABLE_QUARANTINED_COUNT="+str(len(report["quarantined"])))
        print("CHACHA_DEV_V643_CAPABILITY_TRUST_FILTER="+("PASS" if report["trust_filter_applied"] else "NOT_AVAILABLE"))
        print("CHACHA_DEV_V643_TRUSTED_PERMISSION_ESCALATION=NO")
        print(json.dumps(report,ensure_ascii=False))
        return 0
    if args.cmd=="adopt":
        receipt=adopt(args)
        print("CHACHA_DEV_V642_DURABLE_ADOPTION="+("PASS" if receipt["status"] in {"COMMITTED","IDEMPOTENT"} else receipt["status"]))
        print("CHACHA_DEV_V642_DURABLE_ADOPTION_APPLIED="+("YES" if receipt.get("applied") else "NO"))
        print("CHACHA_DEV_V642_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
        return 0
    if args.cmd=="rollback":
        receipt=rollback(args)
        print("CHACHA_DEV_V642_DURABLE_ROLLBACK="+("PASS" if receipt["status"] in {"ROLLED_BACK","IDEMPOTENT_ROLLBACK"} else receipt["status"]))
        return 0
    reg=read_registry(args.registry)
    active=sum(1 for x in (reg.get("adoptions") or {}).values() if isinstance(x,dict) and x.get("status")=="ADOPTED")
    print(json.dumps({"schema":REGISTRY_SCHEMA,"status":"PASS","active_adoptions":active,
                      "registry_digest":digest_file(args.registry) if args.registry.exists() else digest_obj(reg)},indent=2))
    print("CHACHA_DEV_V642_DURABLE_REGISTRY_VERIFY=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
