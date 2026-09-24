#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/platform-component-branch-foundry-source-integrator/v1"
APPLY_SCHEMA="chacha.dev/platform-component-source-integration-request/v1"
ROLLBACK_REQUEST_SCHEMA="chacha.dev/platform-component-source-integration-rollback-request/v1"
APPLY_RECEIPT_SCHEMA="chacha.dev/platform-component-source-integration-receipt/v1"
ROLLBACK_RECEIPT_SCHEMA="chacha.dev/platform-component-source-integration-rollback/v1"
ZERO="0"*40

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def emit(value:dict[str,Any],code:int=0)->int:
    sys.stdout.write(json.dumps(value,ensure_ascii=False,separators=(",",":"))+"\n")
    return code

def blocked(operation:str,reason:str,details:dict[str,Any]|None=None)->int:
    return emit({
      "schema":"chacha.dev/platform-component-source-integration-adapter-result/v1",
      "operation":operation,"status":"BLOCKED","reason":reason,
      "details":details or {},"direct_runtime_mutation":False,
      "production_activation":False,"production_deployment":False,
      "merge_to_production_branch":False,"automatic_external_spend_eur":0
    },2)

def load_policy()->dict[str,Any]:
    candidates=[]
    raw=os.environ.get("CHACHA_PLATFORM_SOURCE_INTEGRATOR_POLICY","").strip()
    if raw:candidates.append(Path(raw))
    try:candidates.append(Path(__file__).resolve().parents[1]/"config/platform-component-branch-foundry-source-integrator.v1.json")
    except Exception:pass
    candidates.append(Path("/opt/chacha-dev/runtime/adapter-policies/platform-component-branch-foundry-source-integrator.v1.json"))
    candidates.append(Path("/opt/chacha-dev/platform/current/dev-hub/config/platform-component-branch-foundry-source-integrator.v1.json"))
    path=next((p for p in candidates if p.is_file()),None)
    if path is None:raise ValueError("SOURCE_INTEGRATOR_POLICY_NOT_FOUND")
    policy=load(path)
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("SOURCE_INTEGRATOR_POLICY_SCHEMA_INVALID")
    return policy

def repository_path(policy:dict[str,Any])->Path:
    repo=policy.get("repository") or {}
    override=os.environ.get(str(repo.get("qualification_override_env") or ""),"").strip()
    if override:
        if os.environ.get("CHACHA_PLATFORM_SOURCE_INTEGRATOR_QUALIFICATION")!="1":
            raise ValueError("SOURCE_REPOSITORY_OVERRIDE_QUALIFICATION_ONLY")
        return Path(override).resolve()
    return Path(str(repo.get("default_path") or "")).resolve()

def run_git(repo:Path,args:list[str],timeout:int=30)->subprocess.CompletedProcess[str]:
    env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"LANG":"C","LC_ALL":"C",
         "GIT_CONFIG_NOSYSTEM":"1","GIT_TERMINAL_PROMPT":"0"}
    return subprocess.run(
      ["/usr/bin/git","--git-dir",str(repo),*args],
      stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
      text=True,shell=False,check=False,timeout=timeout,env=env
    )

def require_repo(repo:Path)->None:
    if not repo.is_dir():raise ValueError("SOURCE_REPOSITORY_MISSING")
    p=run_git(repo,["rev-parse","--is-bare-repository"])
    if p.returncode!=0 or p.stdout.strip()!="true":raise ValueError("BARE_SOURCE_REPOSITORY_REQUIRED")

def regex(policy:dict[str,Any],key:str)->re.Pattern[str]:
    pattern=str((policy.get("refs") or {}).get(key) or "")
    if not pattern:raise ValueError("POLICY_PATTERN_MISSING:"+key)
    return re.compile(pattern)

def validate_identity(req:dict[str,Any],policy:dict[str,Any])->tuple[str,str,str]:
    component=str(req.get("component_id") or "")
    candidate=str(req.get("candidate_revision") or "")
    incumbent=str(req.get("incumbent_revision") or "")
    if regex(policy,"component_id_pattern").fullmatch(component) is None:
        raise ValueError("COMPONENT_ID_INVALID")
    if regex(policy,"candidate_revision_pattern").fullmatch(candidate) is None:
        raise ValueError("CANDIDATE_REVISION_INVALID")
    if regex(policy,"incumbent_revision_pattern").fullmatch(incumbent) is None:
        raise ValueError("INCUMBENT_REVISION_INVALID")
    if candidate==incumbent:raise ValueError("CANDIDATE_EQUALS_INCUMBENT")
    return component,candidate,incumbent

def ref_name(policy:dict[str,Any],component:str,candidate:str)->str:
    prefix=str((policy.get("refs") or {}).get("prefix") or "").rstrip("/")
    if not prefix.startswith("refs/chacha-dev/release-candidates"):
        raise ValueError("TRUSTED_REF_PREFIX_INVALID")
    ref=f"{prefix}/{component}/{candidate}"
    if not ref.startswith("refs/chacha-dev/release-candidates/"):
        raise ValueError("RELEASE_CANDIDATE_REF_ESCAPE")
    return ref

def object_commit(repo:Path,revision:str)->None:
    p=run_git(repo,["cat-file","-e",revision+"^{commit}"])
    if p.returncode!=0:raise ValueError("REVISION_COMMIT_NOT_FOUND:"+revision)

def require_ancestry(repo:Path,incumbent:str,candidate:str)->None:
    p=run_git(repo,["merge-base","--is-ancestor",incumbent,candidate])
    if p.returncode!=0:raise ValueError("CANDIDATE_NOT_DESCENDANT_OF_INCUMBENT")

def current_ref(repo:Path,ref:str)->str|None:
    p=run_git(repo,["rev-parse","--verify",ref+"^{commit}"])
    if p.returncode==0:return p.stdout.strip()
    if p.returncode==128:return None
    raise RuntimeError("RELEASE_CANDIDATE_REF_READ_FAILED")

def binding(repo:Path,component:str,candidate:str,incumbent:str,ref:str)->dict[str,str]:
    return {
      "repository":str(repo),"component_id":component,
      "candidate_revision":candidate,"incumbent_revision":incumbent,"ref":ref
    }

def rollback_token(repo:Path,component:str,candidate:str,incumbent:str,ref:str)->str:
    raw=json.dumps(binding(repo,component,candidate,incumbent,ref),
                   sort_keys=True,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def validate_common_flags(req:dict[str,Any])->None:
    for key in ("direct_runtime_mutation","production_activation","production_deployment","merge_to_production_branch"):
        if req.get(key) is not False:raise ValueError("FORBIDDEN_FLAG_NOT_FALSE:"+key)
    if float(req.get("automatic_external_spend_eur") or 0)!=0:
        raise ValueError("AUTOMATIC_EXTERNAL_SPEND_FORBIDDEN")

def do_apply(req:dict[str,Any],policy:dict[str,Any],repo:Path)->int:
    if req.get("schema")!=APPLY_SCHEMA:return blocked("apply","APPLY_SCHEMA_INVALID")
    try:
        validate_common_flags(req)
        if req.get("apply_mode")!="SOURCE_RELEASE_CANDIDATE_INTEGRATION":
            raise ValueError("APPLY_MODE_INVALID")
        if str(req.get("candidate_owner") or "")!=str(policy.get("candidate_owner") or "")=="branch-foundry":
            raise ValueError("CANDIDATE_OWNER_INVALID")
        component,candidate,incumbent=validate_identity(req,policy)
        if req.get("candidate_artifact_ref")!="git:candidate@"+candidate:
            raise ValueError("CANDIDATE_ARTIFACT_REF_MISMATCH")
        if req.get("incumbent_artifact_ref")!="git:incumbent@"+incumbent:
            raise ValueError("INCUMBENT_ARTIFACT_REF_MISMATCH")
        require_repo(repo);object_commit(repo,incumbent);object_commit(repo,candidate)
        require_ancestry(repo,incumbent,candidate)
        ref=ref_name(policy,component,candidate)
        before=current_ref(repo,ref)
        if before is not None and before!=candidate:
            raise ValueError("RELEASE_CANDIDATE_REF_CONFLICT")
        idempotent=before==candidate
        if not idempotent:
            p=run_git(repo,["update-ref",ref,candidate,ZERO])
            if p.returncode!=0:raise RuntimeError("RELEASE_CANDIDATE_REF_CREATE_FAILED:"+p.stderr[-300:])
        after=current_ref(repo,ref)
        if after!=candidate:raise RuntimeError("RELEASE_CANDIDATE_REF_VERIFY_FAILED")
        token=rollback_token(repo,component,candidate,incumbent,ref)
        return emit({
          "schema":APPLY_RECEIPT_SCHEMA,"status":"PASS",
          "adapter_id":policy.get("adapter_id"),"candidate_owner":"branch-foundry",
          "component_id":component,"candidate_revision":candidate,"incumbent_revision":incumbent,
          "source_release_candidate_integrated":True,"release_candidate_ref":ref,
          "rollback_token":token,"idempotent":idempotent,
          "direct_runtime_mutation":False,"production_activation":False,
          "production_deployment":False,"merge_to_production_branch":False,
          "automatic_external_spend_eur":0
        })
    except Exception as exc:
        return blocked("apply",str(exc))

def do_rollback(req:dict[str,Any],policy:dict[str,Any],repo:Path)->int:
    if req.get("schema")!=ROLLBACK_REQUEST_SCHEMA:return blocked("rollback","ROLLBACK_SCHEMA_INVALID")
    try:
        if float(req.get("automatic_external_spend_eur") or 0)!=0:
            raise ValueError("AUTOMATIC_EXTERNAL_SPEND_FORBIDDEN")
        component,candidate,incumbent=validate_identity(req,policy)
        require_repo(repo);object_commit(repo,incumbent);object_commit(repo,candidate)
        ref=ref_name(policy,component,candidate)
        expected=rollback_token(repo,component,candidate,incumbent,ref)
        if str(req.get("rollback_token") or "")!=expected:
            raise ValueError("ROLLBACK_TOKEN_MISMATCH")
        before=current_ref(repo,ref)
        already_reverted=before is None
        if before is not None and before!=candidate:
            raise ValueError("ROLLBACK_REF_CHANGED_SINCE_APPLY")
        if before==candidate:
            p=run_git(repo,["update-ref","-d",ref,candidate])
            if p.returncode!=0:raise RuntimeError("RELEASE_CANDIDATE_REF_DELETE_FAILED:"+p.stderr[-300:])
        after=current_ref(repo,ref)
        if after is not None:raise RuntimeError("RELEASE_CANDIDATE_REF_ROLLBACK_VERIFY_FAILED")
        return emit({
          "schema":ROLLBACK_RECEIPT_SCHEMA,"status":"PASS",
          "adapter_id":policy.get("adapter_id"),"candidate_owner":"branch-foundry",
          "component_id":component,"candidate_revision":candidate,"incumbent_revision":incumbent,
          "rollback_proven":True,"source_candidate_integration_reverted":True,
          "release_candidate_ref":ref,"already_reverted":already_reverted,
          "direct_runtime_mutation":False,"production_activation":False,
          "production_deployment":False,"merge_to_production_branch":False,
          "automatic_external_spend_eur":0
        })
    except Exception as exc:
        return blocked("rollback",str(exc))

def main()->int:
    if len(sys.argv)!=2 or sys.argv[1] not in {"apply","rollback"}:
        return blocked("unknown","OPERATION_NOT_ALLOWED")
    operation=sys.argv[1]
    try:req=json.load(sys.stdin)
    except Exception:return blocked(operation,"INPUT_JSON_INVALID")
    if not isinstance(req,dict):return blocked(operation,"INPUT_ROOT_NOT_OBJECT")
    try:
        policy=load_policy();repo=repository_path(policy)
    except Exception as exc:
        return blocked(operation,"POLICY_OR_REPOSITORY_RESOLUTION_FAILED:"+str(exc))
    return do_apply(req,policy,repo) if operation=="apply" else do_rollback(req,policy,repo)

if __name__=="__main__":raise SystemExit(main())
