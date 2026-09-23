#!/usr/bin/env python3
"""ChaCha DEV V6.39 Cloudflare Pages production adapter.

Production-capable by contract, but fail-closed until the adapter is separately
qualified, promoted and enabled. It accepts only structured dispatch envelopes,
requires a protected Project Control approval receipt, captures the current
successful production deployment before any write, and exposes explicit deploy,
health and rollback actions. Secret values are never returned.

No shell interpolation is used. Project creation, settings mutation, domain
mutation and secret mutation are intentionally out of scope.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

INPUT_SCHEMA="chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA="chacha.dev/task-result/v1"
POLICY_SCHEMA="chacha.dev/cloudflare-pages-production-adapter/v1"
ADAPTER_ID="cloudflare-pages-production-adapter"
PROVIDER_ID="cloudflare-pages-production"
APPROVAL_ID="production-deployment"
REV_RE=re.compile(r"^[0-9a-f]{40}$")
PROJECT_RE=re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?$")
FORBIDDEN_ACTORS={
    "central-orchestrator","guardian","sentinel","curator",
    "bastion","intendant","logician","ergonomist"
}

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def sha256_bytes(v:bytes)->str:
    return "sha256:"+hashlib.sha256(v).hexdigest()

def result(req:dict[str,Any],status:str,summary:str,
           evidence:list[dict[str,Any]]|None=None,
           outputs:list[dict[str,Any]]|None=None)->dict[str,Any]:
    task=req.get("task") if isinstance(req.get("task"),dict) else {}
    return {
      "schema":OUTPUT_SCHEMA,
      "project":str(req.get("project") or "unknown"),
      "task_id":str(task.get("id") or "unknown"),
      "status":status,
      "producer":ADAPTER_ID,
      "observed_at":now_iso(),
      "summary":summary,
      "evidence":evidence or [],
      "verification":{
        "status":"UNVERIFIED","method":"none","verifier":"none",
        "observed_at":now_iso(),
        "notes":"Production adapter results require independent verification."
      },
      "outputs":outputs or []
    }

def emit(payload:dict[str,Any],code:int=0)->int:
    sys.stdout.write(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    return code

def blocked(req:dict[str,Any],reason:str,details:dict[str,Any]|None=None)->int:
    raw=json.dumps({"reason":reason,**(details or {})},sort_keys=True,separators=(",",":")).encode()
    ev=[{"kind":"report","source":"adapter-policy","digest":sha256_bytes(raw),
         "details":{"reason":reason,**(details or {})}}]
    return emit(result(req,"BLOCKED",reason,ev),2)

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):
        raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def load_policy()->dict[str,Any]:
    raw=os.environ.get("CHACHA_CF_PAGES_PROD_POLICY","").strip()
    candidates=[]
    if raw:
        candidates.append(Path(raw))
    # Source-tree execution (qualification / tests).
    try:
        candidates.append(Path(__file__).resolve().parents[1]/"config/cloudflare-pages-production-adapter.v1.json")
    except Exception:
        pass
    # Provisioned VPS execution: policy stays authoritative in platform/current.
    candidates.append(Path("/opt/chacha-dev/platform/current/dev-hub/config/cloudflare-pages-production-adapter.v1.json"))
    path=next((p for p in candidates if p.is_file()),None)
    if path is None:
        raise ValueError("PRODUCTION_ADAPTER_POLICY_NOT_FOUND")
    x=load(path)
    if x.get("schema")!=POLICY_SCHEMA:
        raise ValueError("POLICY_SCHEMA_INVALID")
    return x

def clean_url(url:str)->str:
    p=urlsplit(url)
    return urlunsplit((p.scheme,p.netloc,p.path or "/","",""))

def run(argv:list[str],timeout:int=300,env:dict[str,str]|None=None)->subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          timeout=timeout,shell=False,check=False,env=env or os.environ.copy())

def allowed_projects()->set[str]:
    raw=os.environ.get("CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS","")
    return {x.strip() for x in raw.split(",") if x.strip()}

def approval_receipt(path:Path,project_id:str)->dict[str,Any]:
    x=load(path)
    if x.get("schema")!="chacha.dev/control-transaction-receipt/v1":
        raise ValueError("APPROVAL_RECEIPT_SCHEMA_INVALID")
    if x.get("operation")!="record-approval" or x.get("status")!="COMMITTED":
        raise ValueError("APPROVAL_RECEIPT_NOT_COMMITTED")
    if x.get("approval_id")!=APPROVAL_ID:
        raise ValueError("APPROVAL_ID_MISMATCH")
    actor=str(x.get("actor") or "").strip()
    if not actor or actor in FORBIDDEN_ACTORS:
        raise ValueError("REAL_HUMAN_APPROVAL_REQUIRED")
    if str(x.get("project") or "")!=project_id:
        raise ValueError("APPROVAL_PROJECT_MISMATCH")
    return x

def validate_request(req:dict[str,Any])->tuple[dict[str,Any]|None,str|None]:
    if req.get("schema")!=INPUT_SCHEMA:
        return None,"INPUT_SCHEMA_INVALID"
    task=req.get("task")
    if not isinstance(task,dict) or not task.get("id"):
        return None,"TASK_ID_MISSING"
    bindings=req.get("bindings")
    if not isinstance(bindings,list) or not any(
        isinstance(x,dict) and x.get("provider")==PROVIDER_ID and x.get("adapter")==ADAPTER_ID
        for x in bindings
    ):
        return None,"CLOUDFLARE_PAGES_PRODUCTION_BINDING_MISSING"
    meta=req.get("metadata")
    cf=meta.get("cloudflare_pages_production") if isinstance(meta,dict) else None
    if not isinstance(cf,dict):
        return None,"CLOUDFLARE_PAGES_PRODUCTION_METADATA_MISSING"
    action=str(cf.get("action") or "")
    expected={
      "contract-status":"read",
      "deployment-plan":"read",
      "production-deploy":"production-deploy",
      "production-health":"read",
      "production-rollback":"production-deploy"
    }.get(action)
    if expected is None:
        return None,"CLOUDFLARE_PAGES_PRODUCTION_ACTION_NOT_ALLOWED"
    if task.get("permission")!=expected:
        return None,"CLOUDFLARE_PAGES_PRODUCTION_PERMISSION_REQUIRED:"+expected
    return cf,None

def validate_target(cf:dict[str,Any])->tuple[str,str,str,Path]:
    project=str(cf.get("project_name") or "").strip()
    branch=str(cf.get("production_branch") or "").strip()
    revision=str(cf.get("revision") or "").strip().lower()
    build=Path(str(cf.get("build_directory") or ""))
    if PROJECT_RE.fullmatch(project) is None:
        raise ValueError("PROJECT_NAME_INVALID")
    if project not in allowed_projects():
        raise ValueError("PROJECT_NOT_ALLOWLISTED")
    if not branch or len(branch)>200:
        raise ValueError("PRODUCTION_BRANCH_INVALID")
    if REV_RE.fullmatch(revision) is None:
        raise ValueError("PINNED_REVISION_REQUIRED")
    if not build.is_absolute() or not build.is_dir():
        raise ValueError("BUILD_DIRECTORY_INVALID")
    return project,branch,revision,build

def auth_headers()->dict[str,str]:
    token=os.environ.get("CLOUDFLARE_API_TOKEN","").strip()
    if not token:
        raise ValueError("CLOUDFLARE_API_TOKEN_MISSING")
    return {"Authorization":"Bearer "+token,"Content-Type":"application/json",
            "User-Agent":"ChaCha-DEV-V639-CloudflarePages/1"}

def account_id()->str:
    value=os.environ.get("CLOUDFLARE_ACCOUNT_ID","").strip()
    if not value:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID_MISSING")
    return value

def api_json(method:str,path:str,body:dict[str,Any]|None=None,timeout:int=30)->dict[str,Any]:
    base="https://api.cloudflare.com/client/v4"
    data=None if body is None else json.dumps(body,separators=(",",":")).encode()
    req=urllib.request.Request(base+path,data=data,headers=auth_headers(),method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            payload=json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError("CLOUDFLARE_HTTP_"+str(exc.code)) from exc
    if not isinstance(payload,dict) or payload.get("success") is not True:
        raise RuntimeError("CLOUDFLARE_API_NOT_SUCCESS")
    return payload

def get_project(project:str)->dict[str,Any]:
    aid=urllib.parse.quote(account_id(),safe="")
    pname=urllib.parse.quote(project,safe="")
    p=api_json("GET",f"/accounts/{aid}/pages/projects/{pname}")
    row=p.get("result") or {}
    if not isinstance(row,dict):
        raise RuntimeError("CLOUDFLARE_PROJECT_RESPONSE_INVALID")
    return row

def get_deployment(project:str,deployment:str)->dict[str,Any]:
    aid=urllib.parse.quote(account_id(),safe="")
    pname=urllib.parse.quote(project,safe="")
    did=urllib.parse.quote(deployment,safe="")
    p=api_json("GET",f"/accounts/{aid}/pages/projects/{pname}/deployments/{did}")
    row=p.get("result") or {}
    if not isinstance(row,dict):
        raise RuntimeError("CLOUDFLARE_DEPLOYMENT_RESPONSE_INVALID")
    return row

def canonical_production(project:str)->dict[str,Any]:
    row=(get_project(project).get("canonical_deployment") or {})
    if not isinstance(row,dict) or not row.get("id"):
        raise RuntimeError("CANONICAL_PRODUCTION_DEPLOYMENT_MISSING")
    return row

def wait_canonical(project:str,expected_id:str|None,forbid_id:str|None,timeout:int=90)->dict[str,Any]:
    end=time.monotonic()+timeout
    last={}
    while time.monotonic()<end:
        last=canonical_production(project)
        did=str(last.get("id") or "")
        if expected_id is not None and did==expected_id and successful(last):
            return last
        if forbid_id is not None and did and did!=forbid_id and successful(last):
            return last
        time.sleep(2)
    raise RuntimeError("CANONICAL_PRODUCTION_CHANGE_NOT_OBSERVED")

def successful(row:dict[str,Any])->bool:
    latest=(row.get("latest_stage") or {})
    return str(latest.get("status") or "").lower()=="success"

def deployment_id(row:dict[str,Any])->str:
    return str(row.get("id") or "")

def source_url(row:dict[str,Any])->str:
    return clean_url(str(row.get("url") or "")) if row.get("url") else ""

def execution_enabled(policy:dict[str,Any])->bool:
    g=policy.get("mutation_guard") or {}
    return os.environ.get(str(g.get("environment_switch") or ""),"")==str(g.get("required_value") or "")

def require_mutation_authority(req:dict[str,Any],cf:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if not execution_enabled(policy):
        raise ValueError("REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED")
    ctx=req.get("policy_context") if isinstance(req.get("policy_context"),dict) else {}
    if ctx.get("human_approval_required") is not True or str(ctx.get("approval_id") or "")!=APPROVAL_ID:
        raise ValueError("PRODUCTION_APPROVAL_POLICY_MISSING")
    receipt_path=Path(str(cf.get("approval_receipt") or ""))
    if not receipt_path.is_file():
        raise ValueError("PROJECT_CONTROL_APPROVAL_RECEIPT_MISSING")
    return approval_receipt(receipt_path,str(req.get("project") or ""))

def do_contract(req:dict[str,Any],policy:dict[str,Any])->int:
    details={
      "adapter_status_required":policy.get("status_required_for_execution"),
      "execution_switch_enabled":execution_enabled(policy),
      "production_capable":True,
      "project_creation_forbidden":True,
      "rollback_required":True
    }
    raw=json.dumps(details,sort_keys=True,separators=(",",":")).encode()
    return emit(result(req,"OK","CLOUDFLARE_PAGES_PRODUCTION_CONTRACT_OK",
                       [{"kind":"report","source":"adapter-contract","digest":sha256_bytes(raw),"details":details}],
                       [{"type":"artifact","id":"cloudflare-pages-production-contract","status":"UNVERIFIED"}]))

def do_plan(req:dict[str,Any],cf:dict[str,Any],policy:dict[str,Any])->int:
    try:
        project,branch,revision,build=validate_target(cf)
    except Exception as exc:
        return blocked(req,str(exc))
    details={
      "project_name":project,"production_branch":branch,"revision":revision,
      "build_directory":str(build),"production_mutation":False,
      "approval_id":APPROVAL_ID,"rollback_capture_required":True,
      "execution_switch_enabled":execution_enabled(policy)
    }
    raw=json.dumps(details,sort_keys=True,separators=(",",":")).encode()
    return emit(result(req,"OK","CLOUDFLARE_PAGES_PRODUCTION_PLAN_OK",
                       [{"kind":"report","source":"deployment-plan","digest":sha256_bytes(raw),"details":details}],
                       [{"type":"artifact","id":"cloudflare-pages-production-plan","status":"UNVERIFIED"}]))

def do_deploy(req:dict[str,Any],cf:dict[str,Any],policy:dict[str,Any])->int:
    try:
        project,branch,revision,build=validate_target(cf)
        approval=require_mutation_authority(req,cf,policy)
        previous=canonical_production(project)
        if not successful(previous) or not deployment_id(previous):
            raise ValueError("PREVIOUS_SUCCESSFUL_PRODUCTION_DEPLOYMENT_REQUIRED")
    except Exception as exc:
        return blocked(req,str(exc))

    env=os.environ.copy()
    cmd=["npx","--yes","wrangler@"+str((policy.get("deployment") or {}).get("wrangler_version") or "4.45.0"),
         "pages","deploy",str(build),"--project-name",project,"--branch",branch,
         "--commit-hash",revision,"--commit-message","ChaCha DEV V6.39 controlled production deploy"]
    proc=run(cmd,timeout=600,env=env)
    if proc.returncode!=0:
        details={"returncode":proc.returncode,"stderr_digest":sha256_bytes(proc.stderr[:65536])}
        return emit(result(req,"FAILED","CLOUDFLARE_PAGES_PRODUCTION_DEPLOY_FAILED",
                           [{"kind":"command","source":"local://wrangler-pages-deploy",
                             "digest":sha256_bytes(proc.stdout[:65536]+proc.stderr[:65536]),"details":details}]))
    try:
        current=wait_canonical(project,None,deployment_id(previous),90)
    except Exception as exc:
        return emit(result(req,"FAILED",str(exc)))

    details={
      "project_name":project,"revision":revision,
      "approval_actor":approval.get("actor"),
      "previous_deployment_id":deployment_id(previous),
      "previous_deployment_url":source_url(previous),
      "new_deployment_id":deployment_id(current),
      "new_deployment_url":source_url(current),
      "rollback_available":True
    }
    raw=json.dumps(details,sort_keys=True,separators=(",",":")).encode()
    return emit(result(req,"OK","CLOUDFLARE_PAGES_PRODUCTION_DEPLOY_OK",
                       [{"kind":"provider","source":"cloudflare://pages/"+project,
                         "digest":sha256_bytes(raw),"details":details}],
                       [{"type":"artifact","id":"production-deployment-receipt","status":"UNVERIFIED"}]))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

def do_health(req:dict[str,Any],cf:dict[str,Any])->int:
    url=str(cf.get("canonical_url") or "")
    p=urlsplit(url)
    if p.scheme!="https" or not p.hostname or p.username or p.password:
        return blocked(req,"CANONICAL_HTTPS_URL_INVALID")
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    started=time.monotonic()
    try:
        with opener.open(urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-V639-Health/1"}),timeout=20) as r:
            code=int(r.status);sample=r.read(65536)
    except urllib.error.HTTPError as exc:
        code=int(exc.code);sample=exc.read(65536)
    except Exception as exc:
        return emit(result(req,"FAILED","PRODUCTION_HEALTH_TRANSPORT_FAILED:"+type(exc).__name__))
    elapsed=round((time.monotonic()-started)*1000,2)
    details={"http_status":code,"elapsed_ms":elapsed,"url":clean_url(url)}
    ev=[{"kind":"url","source":clean_url(url),"digest":sha256_bytes(sample),"details":details}]
    if code!=200:
        return emit(result(req,"FAILED","PRODUCTION_HEALTH_UNEXPECTED_STATUS:"+str(code),ev))
    return emit(result(req,"OK","PRODUCTION_HEALTH_OK",ev,
                       [{"type":"artifact","id":"production-health","status":"UNVERIFIED"}]))

def do_rollback(req:dict[str,Any],cf:dict[str,Any],policy:dict[str,Any])->int:
    try:
        project,_,_,_=validate_target(cf)
        approval=require_mutation_authority(req,cf,policy)
        previous=str(cf.get("previous_deployment_id") or "").strip()
        if not previous:
            raise ValueError("PREVIOUS_DEPLOYMENT_ID_REQUIRED")
        target=get_deployment(project,previous)
        if not successful(target):
            raise ValueError("ROLLBACK_TARGET_NOT_SUCCESSFUL_PRODUCTION")
        aid=urllib.parse.quote(account_id(),safe="")
        pname=urllib.parse.quote(project,safe="")
        did=urllib.parse.quote(previous,safe="")
        api_json("POST",f"/accounts/{aid}/pages/projects/{pname}/deployments/{did}/rollback",{})
        wait_canonical(project,previous,None,90)
    except Exception as exc:
        return blocked(req,str(exc))
    details={"project_name":project,"restored_deployment_id":previous,
             "approval_actor":approval.get("actor"),"rollback_proven":True}
    raw=json.dumps(details,sort_keys=True,separators=(",",":")).encode()
    return emit(result(req,"OK","CLOUDFLARE_PAGES_PRODUCTION_ROLLBACK_OK",
                       [{"kind":"provider","source":"cloudflare://pages/"+project,
                         "digest":sha256_bytes(raw),"details":details}],
                       [{"type":"artifact","id":"production-rollback-receipt","status":"UNVERIFIED"}]))

def main()->int:
    try:req=json.load(sys.stdin)
    except Exception as exc:
        return emit(result({"project":"unknown","task":{"id":"unknown"}},"BLOCKED",
                           "INPUT_JSON_INVALID:"+type(exc).__name__),2)
    if not isinstance(req,dict):
        return emit(result({"project":"unknown","task":{"id":"unknown"}},"BLOCKED","INPUT_ROOT_NOT_OBJECT"),2)
    try:policy=load_policy()
    except Exception as exc:return blocked(req,"POLICY_LOAD_FAILED:"+str(exc))
    cf,error=validate_request(req)
    if error:return blocked(req,error)
    assert cf is not None
    action=str(cf.get("action") or "")
    if action=="contract-status":return do_contract(req,policy)
    if action=="deployment-plan":return do_plan(req,cf,policy)
    if action=="production-deploy":return do_deploy(req,cf,policy)
    if action=="production-health":return do_health(req,cf)
    if action=="production-rollback":return do_rollback(req,cf,policy)
    return blocked(req,"ACTION_NOT_ALLOWED")

if __name__=="__main__":
    raise SystemExit(main())
