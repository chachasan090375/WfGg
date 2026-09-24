#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,tempfile,time
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/platform-component-adapter-registry-writer-policy/v1"
CONTRACT_SCHEMA="chacha.dev/platform-component-adapter-registration-contract/v1"
REGISTRY_SCHEMA="chacha.dev/platform-component-apply-adapter-registry/v1"
RECEIPT_SCHEMA="chacha.dev/platform-component-adapter-registry-write-receipt/v1"
ROLLBACK_SCHEMA="chacha.dev/platform-component-adapter-registry-rollback-receipt/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def canonical_digest(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def atomic_json(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as fh:
            json.dump(x,fh,indent=2,ensure_ascii=False);fh.write("\n");fh.flush();os.fsync(fh.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def inside(child:Path,parent:Path)->bool:
    try:child.resolve(strict=False).relative_to(parent.resolve(strict=False));return True
    except Exception:return False

def validate_policy(policy:dict[str,Any])->None:
    if policy.get("schema")!=POLICY_SCHEMA:raise RuntimeError("REGISTRY_WRITER_POLICY_SCHEMA_INVALID")
    p=policy.get("principles") if isinstance(policy.get("principles"),dict) else {}
    required=[
      "project_control_registration_contract_required","explicit_apply_required",
      "exact_before_digest_required","exact_after_digest_required","additive_single_key_only",
      "overwrite_forbidden","delete_forbidden_in_apply","rollback_exact_insert_only",
      "atomic_registry_write_required","default_deny_must_be_preserved",
      "single_use_registration_contract","commit_not_performed_by_writer","push_forbidden",
      "source_integration_forbidden_until_post_registration_gates",
      "direct_runtime_mutation_forbidden","production_activation_forbidden",
      "production_deployment_forbidden","merge_to_production_branch_forbidden",
      "permission_expansion_forbidden"
    ]
    missing=[k for k in required if p.get(k) is not True]
    if missing:raise RuntimeError("REGISTRY_WRITER_POLICY_WEAKENED:"+",".join(missing))
    if float(p.get("automatic_external_spend_eur") or 0)!=0:
        raise RuntimeError("REGISTRY_WRITER_EXTERNAL_SPEND_FORBIDDEN")

def validate_contract(contract:dict[str,Any])->None:
    checks={
      "schema":contract.get("schema")==CONTRACT_SCHEMA,
      "project":contract.get("project")=="chacha-dev-platform",
      "actor":contract.get("actor")=="central-orchestrator",
      "project_control":contract.get("issued_by_project_control") is True,
      "human_approval":contract.get("human_approval_verified") is True,
      "registration_authorized":contract.get("registration_authorized") is True,
      "dedicated_writer_authorized":contract.get("registry_mutation_authorized_for_dedicated_writer") is True,
      "additive_only":contract.get("additive_write_only") is True,
      "overwrite_forbidden":contract.get("overwrite_authorized") is False,
      "delete_forbidden":contract.get("delete_authorized") is False,
      "default_deny":contract.get("default_deny_must_be_preserved") is True,
      "single_use":contract.get("single_use") is True,
      "source_integration_forbidden":contract.get("source_integration_authorized") is False,
      "runtime_mutation_forbidden":contract.get("direct_runtime_mutation_authorized") is False,
      "production_activation_forbidden":contract.get("production_activation_authorized") is False,
      "production_deployment_forbidden":contract.get("production_deployment_authorized") is False,
      "production_merge_forbidden":contract.get("merge_to_production_branch_authorized") is False,
      "automatic_apply_forbidden":contract.get("automatic_apply") is False,
      "component_present":bool(str(contract.get("component_id") or "")),
      "registry_key_matches_component":contract.get("registry_key")==contract.get("component_id"),
      "binding_present":isinstance(contract.get("exact_registry_binding"),dict) and bool(contract.get("exact_registry_binding")),
      "registry_before_digest":bool(str(contract.get("registry_before_digest") or "")),
      "registry_after_digest":bool(str(contract.get("registry_after_digest") or "")),
      "registration_id":bool(str(contract.get("registration_id") or "")),
      "post_registration_gates":len([x for x in contract.get("post_registration_exact_sha_gates_required") or [] if str(x)])>=3,
      "zero_external_spend":float(contract.get("automatic_external_spend_eur") or 0)==0,
    }
    bad=sorted(k for k,v in checks.items() if not v)
    if bad:raise RuntimeError("REGISTRATION_CONTRACT_INVALID:"+",".join(bad))

def resolve_registry(repo_root:Path,policy:dict[str,Any],contract:dict[str,Any])->Path:
    canonical=str(policy.get("canonical_registry_path") or "")
    requested=str(contract.get("registry_path") or "")
    if not canonical or requested!=canonical:
        raise RuntimeError("REGISTRY_PATH_CONTRACT_MISMATCH")
    path=(repo_root/canonical).resolve()
    if not inside(path,repo_root):raise RuntimeError("REGISTRY_PATH_ESCAPE")
    return path

def expected_after(registry:dict[str,Any],contract:dict[str,Any])->dict[str,Any]:
    out=json.loads(json.dumps(registry))
    adapters=out.get("adapters")
    if not isinstance(adapters,dict):raise RuntimeError("REGISTRY_ADAPTERS_INVALID")
    key=str(contract.get("registry_key") or "")
    if key in adapters:raise RuntimeError("REGISTRY_KEY_ALREADY_EXISTS")
    adapters[key]=json.loads(json.dumps(contract["exact_registry_binding"]))
    return out

def validate_registry_before(registry:dict[str,Any],contract:dict[str,Any])->dict[str,Any]:
    if registry.get("schema")!=REGISTRY_SCHEMA:raise RuntimeError("REGISTRY_SCHEMA_INVALID")
    if registry.get("default_admission")!="DENY":raise RuntimeError("REGISTRY_DEFAULT_ADMISSION_NOT_DENY")
    before=canonical_digest(registry)
    if before!=contract.get("registry_before_digest"):
        raise RuntimeError("REGISTRY_BEFORE_DIGEST_MISMATCH")
    after=expected_after(registry,contract)
    if canonical_digest(after)!=contract.get("registry_after_digest"):
        raise RuntimeError("REGISTRY_AFTER_DIGEST_MISMATCH")
    return after

def consume_contract(runtime_root:Path,contract:dict[str,Any])->Path:
    rid=str(contract.get("registration_id") or "")
    if not rid:raise RuntimeError("REGISTRATION_ID_MISSING")
    d=runtime_root/"consumed-registration-contracts";d.mkdir(parents=True,exist_ok=True)
    p=d/(rid+".json")
    body={
      "schema":"chacha.dev/platform-component-adapter-registration-consumption/v1",
      "registration_id":rid,"contract_digest":canonical_digest(contract),
      "consumed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "single_use":True
    }
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    try:
        fd=os.open(p,flags,0o600)
    except FileExistsError as exc:
        raise RuntimeError("REGISTRATION_CONTRACT_REPLAY_BLOCKED") from exc
    with os.fdopen(fd,"w",encoding="utf-8") as fh:
        json.dump(body,fh,separators=(",",":"));fh.write("\n");fh.flush();os.fsync(fh.fileno())
    return p

def plan(repo_root:Path,policy:dict[str,Any],contract:dict[str,Any])->dict[str,Any]:
    validate_policy(policy);validate_contract(contract)
    registry_path=resolve_registry(repo_root,policy,contract)
    registry=load(registry_path)
    after=validate_registry_before(registry,contract)
    return {
      "schema":"chacha.dev/platform-component-adapter-registry-write-plan/v1",
      "status":"READY",
      "registration_id":contract.get("registration_id"),
      "component_id":contract.get("component_id"),
      "registry_path":str(registry_path),
      "registry_before_digest":canonical_digest(registry),
      "registry_after_digest":canonical_digest(after),
      "additive_single_key_only":True,
      "overwrite":False,"delete":False,
      "commit_performed":False,"push_performed":False,
      "source_integration_authorized":False,
      "production_activation_allowed":False,
      "automatic_external_spend_eur":0
    }

def apply(repo_root:Path,policy:dict[str,Any],contract:dict[str,Any],runtime_root:Path)->dict[str,Any]:
    validate_policy(policy);validate_contract(contract)
    registry_path=resolve_registry(repo_root,policy,contract)
    before=load(registry_path)
    after=validate_registry_before(before,contract)
    consumption=consume_contract(runtime_root,contract)
    atomic_json(registry_path,after)
    observed=load(registry_path)
    observed_digest=canonical_digest(observed)
    if observed_digest!=contract.get("registry_after_digest"):
        atomic_json(registry_path,before)
        raise RuntimeError("REGISTRY_POST_WRITE_DIGEST_MISMATCH_ROLLED_BACK")
    key=str(contract.get("registry_key") or "")
    if observed.get("default_admission")!="DENY" or (observed.get("adapters") or {}).get(key)!=contract.get("exact_registry_binding"):
        atomic_json(registry_path,before)
        raise RuntimeError("REGISTRY_POST_WRITE_CONTENT_MISMATCH_ROLLED_BACK")
    return {
      "schema":RECEIPT_SCHEMA,"status":"PASS",
      "registration_id":contract.get("registration_id"),
      "component_id":contract.get("component_id"),
      "registry_path":str(registry_path),
      "registry_before_digest":contract.get("registry_before_digest"),
      "registry_after_digest":observed_digest,
      "exact_registry_binding_digest":canonical_digest(contract.get("exact_registry_binding")),
      "consumption_receipt":str(consumption),
      "additive_single_key_write":True,"overwrite_performed":False,"delete_performed":False,
      "default_deny_preserved":True,
      "commit_performed":False,"push_performed":False,
      "post_registration_exact_sha_gates_pending":True,
      "source_integration_authorized":False,
      "direct_runtime_mutation":False,
      "production_activation":False,"production_deployment":False,
      "merge_to_production_branch":False,"permission_expansion":False,
      "rollback_required_until_post_registration_gates":True,
      "automatic_external_spend_eur":0
    }

def rollback(repo_root:Path,policy:dict[str,Any],contract:dict[str,Any],receipt:dict[str,Any])->dict[str,Any]:
    validate_policy(policy);validate_contract(contract)
    if receipt.get("schema")!=RECEIPT_SCHEMA or receipt.get("status")!="PASS":
        raise RuntimeError("REGISTRY_WRITE_RECEIPT_INVALID")
    if receipt.get("registration_id")!=contract.get("registration_id"):
        raise RuntimeError("REGISTRY_WRITE_RECEIPT_ID_MISMATCH")
    registry_path=resolve_registry(repo_root,policy,contract)
    current=load(registry_path)
    if canonical_digest(current)!=contract.get("registry_after_digest"):
        raise RuntimeError("REGISTRY_ROLLBACK_CURRENT_DIGEST_MISMATCH")
    adapters=current.get("adapters") if isinstance(current.get("adapters"),dict) else {}
    key=str(contract.get("registry_key") or "")
    if adapters.get(key)!=contract.get("exact_registry_binding"):
        raise RuntimeError("REGISTRY_ROLLBACK_BINDING_CHANGED")
    restored=json.loads(json.dumps(current));del restored["adapters"][key]
    if canonical_digest(restored)!=contract.get("registry_before_digest"):
        raise RuntimeError("REGISTRY_ROLLBACK_BEFORE_DIGEST_MISMATCH")
    atomic_json(registry_path,restored)
    if canonical_digest(load(registry_path))!=contract.get("registry_before_digest"):
        raise RuntimeError("REGISTRY_ROLLBACK_VERIFY_FAILED")
    return {
      "schema":ROLLBACK_SCHEMA,"status":"PASS",
      "registration_id":contract.get("registration_id"),
      "component_id":contract.get("component_id"),
      "registry_restored_digest":contract.get("registry_before_digest"),
      "exact_insert_removed":True,"overwrite_performed":False,
      "other_binding_deleted":False,"default_deny_preserved":True,
      "rollback_proven":True,
      "commit_performed":False,"push_performed":False,
      "source_integration_authorized":False,
      "production_activation":False,"production_deployment":False,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--registration-contract",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime/platform-component-adapter-registration"))
    sub=ap.add_subparsers(dest="command",required=True)
    sub.add_parser("plan")
    a=sub.add_parser("apply");a.add_argument("--apply",action="store_true");a.add_argument("--receipt",type=Path,required=True)
    rb=sub.add_parser("rollback");rb.add_argument("--receipt",type=Path,required=True);rb.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    repo=args.repo_root.resolve();policy=load(args.policy);contract=load(args.registration_contract)
    if args.command=="plan":
        print(json.dumps(plan(repo,policy,contract),indent=2,ensure_ascii=False));return 0
    if args.command=="apply":
        if not args.apply:
            print("EXPLICIT_APPLY_FLAG_REQUIRED");return 2
        out=apply(repo,policy,contract,args.runtime_root.resolve());atomic_json(args.receipt,out)
        print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_WRITE=PASS")
        print("POST_REGISTRATION_EXACT_SHA_GATES_PENDING=YES")
        print("SOURCE_INTEGRATION_AUTHORIZED=NO")
        print("PRODUCTION_ACTIVATION_ALLOWED=NO")
        return 0
    receipt=load(args.receipt);out=rollback(repo,policy,contract,receipt);atomic_json(args.output,out)
    print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_ROLLBACK=PASS")
    print("ROLLBACK_PROVEN=YES")
    return 0

if __name__=="__main__":raise SystemExit(main())
