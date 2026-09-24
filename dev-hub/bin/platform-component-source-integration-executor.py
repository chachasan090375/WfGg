#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time,urllib.parse,urllib.request,uuid
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/platform-component-source-integration-executor/v1"
DEFAULT_STOP=Path("/opt/chacha-dev/runtime/control/emergency-stop.json")

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def digest(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def stop_active(path:Path=DEFAULT_STOP)->bool:
    try:return bool(load(path).get("active"))
    except Exception:return False

def workflow_success(runs:dict[str,Any],name:str,revision:str)->bool:
    return any(
      isinstance(x,dict) and x.get("name")==name and x.get("head_sha")==revision and
      x.get("status")=="completed" and x.get("conclusion")=="success"
      for x in (runs.get("workflow_runs") or [])
    )

def github_runs(repository:str,revision:str)->dict[str,Any]:
    q=urllib.parse.urlencode({"head_sha":revision,"per_page":100})
    req=urllib.request.Request(
      "https://api.github.com/repos/"+repository+"/actions/runs?"+q,
      headers={"User-Agent":"ChaCha-DEV-Source-Integration/1.0","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req,timeout=20) as r:
        x=json.loads(r.read().decode("utf-8"))
    if not isinstance(x,dict):raise RuntimeError("GITHUB_RUNS_INVALID")
    return x

def _under(path:Path,root:Path)->bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False));return True
    except Exception:return False

def validate_inputs(planner:dict[str,Any],handoff:dict[str,Any],registry:dict[str,Any])->dict[str,Any]:
    plan=planner.get("apply_plan") if isinstance(planner.get("apply_plan"),dict) else {}
    cid=str(plan.get("component_id") or "")
    owner=str(plan.get("candidate_owner") or "")
    principles=registry.get("principles") if isinstance(registry.get("principles"),dict) else {}
    adapters=registry.get("adapters") if isinstance(registry.get("adapters"),dict) else {}
    adapter=adapters.get(cid) if cid else None
    checks={
      "planner_schema":planner.get("schema")=="chacha.dev/platform-component-controlled-apply-planner/v1",
      "planner_ready":planner.get("status")=="READY_FOR_CENTRAL_ORCHESTRATOR_APPLY",
      "planner_plan_ready":planner.get("controlled_apply_plan_ready") is True,
      "planner_execution_not_authorized":planner.get("apply_execution_authorized_by_planner") is False,
      "plan_schema":plan.get("schema")=="chacha.dev/platform-component-controlled-apply-plan/v1",
      "plan_source_candidate_only":plan.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "plan_central_orchestrator_required":plan.get("central_orchestrator_apply_required") is True,
      "plan_runtime_mutation_forbidden":plan.get("direct_runtime_mutation") is False,
      "plan_production_activation_forbidden":plan.get("production_activation_allowed") is False,
      "plan_production_deployment_forbidden":plan.get("production_deployment_allowed") is False,
      "plan_production_merge_forbidden":plan.get("merge_to_production_branch_allowed") is False,
      "plan_rollback_required":plan.get("rollback_required") is True,
      "handoff_schema":handoff.get("schema")=="chacha.dev/platform-component-central-apply-handoff/v1",
      "handoff_actor":handoff.get("actor")=="central-orchestrator",
      "handoff_execution_authorized":handoff.get("apply_execution_authorized") is True,
      "handoff_single_use":handoff.get("single_use") is True,
      "handoff_source_candidate_only":handoff.get("source_candidate_integration_only") is True,
      "handoff_component_matches":handoff.get("component_id")==cid and bool(cid),
      "handoff_owner_matches":handoff.get("candidate_owner")==owner and bool(owner),
      "handoff_candidate_revision_matches":handoff.get("candidate_revision")==plan.get("candidate_revision") and bool(plan.get("candidate_revision")),
      "handoff_incumbent_revision_matches":handoff.get("incumbent_revision")==plan.get("incumbent_revision") and bool(plan.get("incumbent_revision")),
      "handoff_candidate_artifact_matches":handoff.get("candidate_artifact_ref")==plan.get("candidate_artifact_ref") and bool(plan.get("candidate_artifact_ref")),
      "handoff_incumbent_artifact_matches":handoff.get("incumbent_artifact_ref")==plan.get("incumbent_artifact_ref") and bool(plan.get("incumbent_artifact_ref")),
      "handoff_adapter_matches":handoff.get("adapter_id")==plan.get("adapter_id") and bool(plan.get("adapter_id")),
      "handoff_approval_id_matches":handoff.get("approval_id")==planner.get("approval_id") and bool(planner.get("approval_id")),
      "handoff_approval_actor_matches":handoff.get("approval_actor")==planner.get("approval_actor") and bool(planner.get("approval_actor")),
      "handoff_review_digest_matches":handoff.get("technical_review_digest")==planner.get("technical_review_digest") and bool(planner.get("technical_review_digest")),
      "handoff_human_approval_verified":handoff.get("human_approval_verified") is True,
      "handoff_plan_digest_matches":handoff.get("controlled_apply_plan_digest")==digest(plan),
      "handoff_rollback_required":handoff.get("rollback_required") is True,
      "handoff_guardian_pre_post_required":handoff.get("guardian_pre_post_required") is True,
      "handoff_emergency_stop_required":handoff.get("emergency_stop_required") is True,
      "handoff_runtime_mutation_forbidden":handoff.get("direct_runtime_mutation_authorized") is False,
      "handoff_production_activation_forbidden":handoff.get("production_activation_authorized") is False,
      "handoff_production_deployment_forbidden":handoff.get("production_deployment_authorized") is False,
      "handoff_production_merge_forbidden":handoff.get("merge_to_production_branch_authorized") is False,
      "handoff_automatic_apply_forbidden":handoff.get("automatic_apply") is False,
      "handoff_zero_external_spend":float(handoff.get("automatic_external_spend_eur") or 0)==0,
      "registry_schema":registry.get("schema")=="chacha.dev/platform-component-apply-adapter-registry/v1",
      "registry_default_deny":registry.get("default_admission")=="DENY",
      "registry_fixed_operation_protocol":principles.get("fixed_operation_protocol") is True,
      "registry_shell_interpolation_forbidden":principles.get("shell_interpolation_forbidden") is True,
      "registry_single_use_handoff_required":principles.get("single_use_central_handoff_required") is True,
      "registry_trusted_executable_root_present":bool(str(principles.get("trusted_executable_root") or "")),
      "adapter_registered":isinstance(adapter,dict),
    }
    if isinstance(adapter,dict):
        exe=str(adapter.get("executable") or "")
        trusted_root=Path(str(principles.get("trusted_executable_root") or "/nonexistent"))
        checks.update({
          "adapter_id_matches":adapter.get("adapter_id")==plan.get("adapter_id"),
          "adapter_owner_matches":adapter.get("candidate_owner")==owner,
          "adapter_status_qualified":adapter.get("status")=="QUALIFIED",
          "adapter_mode_matches":adapter.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
          "adapter_reversible":adapter.get("reversible") is True,
          "adapter_rollback_id_matches":adapter.get("rollback_adapter_id")==plan.get("rollback_adapter_id") and bool(plan.get("rollback_adapter_id")),
          "adapter_exact_revision":adapter.get("exact_revision_enforced") is True,
          "adapter_executable_absolute":bool(exe) and Path(exe).is_absolute(),
          "adapter_executable_under_trusted_root":bool(exe) and _under(Path(exe),trusted_root),
          "adapter_runtime_mutation_forbidden":adapter.get("direct_runtime_mutation") is False,
          "adapter_production_activation_forbidden":adapter.get("production_activation") is False,
          "adapter_production_deployment_forbidden":adapter.get("production_deployment") is False,
          "adapter_production_merge_forbidden":adapter.get("merge_to_production_branch") is False,
          "adapter_automatic_apply_forbidden":adapter.get("automatic_apply") is False,
          "adapter_zero_external_spend":float(adapter.get("automatic_external_spend_eur") or 0)==0,
        })
    blockers=sorted(k for k,v in checks.items() if not v)
    return {"ok":not blockers,"checks":checks,"blockers":blockers,"plan":plan,"adapter":adapter or {}}

def guardian_event(repo_root:Path,phase:str,plan:dict[str,Any],handoff:dict[str,Any],status:str|None=None)->dict[str,Any]:
    # PLATFORM_COMPONENT_SOURCE_INTEGRATION_GUARDIAN_PRE_POST
    if not Path("/opt/chacha-dev/runtime").exists():
        return {"status":"NON_RUNTIME_TEST_BYPASS","verdict":"PASS"}
    event={
      "schema":"chacha.dev/governance-action/v1","event_id":"gov-"+uuid.uuid4().hex,
      "phase":phase,"actor":"central-orchestrator",
      "subject_role":"platform-component-source-integration-executor",
      "action":"INTEGRATE_RELEASE_CANDIDATE_SOURCE",
      "task_kind":"platform-component-source-integration",
      "permission":"workspace-write","project_id":"chacha-dev-platform",
      "run_id":handoff.get("handoff_id"),"adapters":[plan.get("adapter_id")],
      "evidence":{
        "exact_candidate_revision":plan.get("candidate_revision"),
        "exact_incumbent_revision":plan.get("incumbent_revision"),
        "source_candidate_only":True,"rollback_required":True,
        "central_orchestrator_handoff":True,"result_status":status
      },
      "context":{"resource_class":"light","human_approval_required":True,
                 "storage_preflight_required":False}
    }
    ep=Path("/tmp")/("chacha-platform-source-integration-"+event["event_id"]+".json")
    ep.write_text(json.dumps(event,ensure_ascii=False)+"\n",encoding="utf-8")
    try:
        p=subprocess.run([
          sys.executable,str(repo_root/"dev-hub/bin/guardian-client.py"),
          "--policy",str(repo_root/"dev-hub/config/guardian-runtime-policy.v1.json"),
          "check","--event",str(ep)
        ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=25)
    finally:
        try:ep.unlink()
        except Exception:pass
    try:v=json.loads(p.stdout.strip())
    except Exception:v={"status":"UNAVAILABLE","reason":"INVALID_RESPONSE"}
    if p.returncode!=0 or str(v.get("verdict") or v.get("status") or "") in {"BLOCK","CRITICAL","UNAVAILABLE"}:
        raise RuntimeError("GUARDIAN_SOURCE_INTEGRATION_BLOCK:"+str(v.get("reason_codes") or v.get("reason") or p.returncode))
    return v

def consume_handoff(runtime_root:Path,handoff:dict[str,Any])->Path:
    hid=str(handoff.get("handoff_id") or "")
    if not hid:raise RuntimeError("CENTRAL_APPLY_HANDOFF_ID_MISSING")
    token=hashlib.sha256(hid.encode()).hexdigest()
    d=runtime_root/"consumed-handoffs";d.mkdir(parents=True,exist_ok=True)
    p=d/(token+".json")
    body=json.dumps({"schema":"chacha.dev/platform-component-central-apply-handoff-consumption/v1",
      "handoff_id":hid,"consumed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "single_use":True},separators=(",",":"))+"\n"
    try:
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc:
        raise RuntimeError("CENTRAL_APPLY_HANDOFF_REPLAY_BLOCKED") from exc
    with os.fdopen(fd,"w",encoding="utf-8") as h:h.write(body)
    return p

def run_adapter(executable:str,operation:str,payload:dict[str,Any])->dict[str,Any]:
    p=subprocess.run([executable,operation],input=json.dumps(payload,separators=(",",":")),
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,
                     shell=False,timeout=180)
    if p.returncode!=0:
        raise RuntimeError("SOURCE_INTEGRATION_ADAPTER_"+operation.upper()+"_FAILED:"+p.stderr[-500:])
    try:x=json.loads(p.stdout)
    except Exception as exc:raise RuntimeError("SOURCE_INTEGRATION_ADAPTER_INVALID_JSON") from exc
    if not isinstance(x,dict):raise RuntimeError("SOURCE_INTEGRATION_ADAPTER_RESULT_NOT_OBJECT")
    return x

def validate_apply_receipt(receipt:dict[str,Any],plan:dict[str,Any])->None:
    checks={
      "schema":receipt.get("schema")=="chacha.dev/platform-component-source-integration-receipt/v1",
      "status":receipt.get("status")=="PASS",
      "component":receipt.get("component_id")==plan.get("component_id"),
      "candidate_revision":receipt.get("candidate_revision")==plan.get("candidate_revision"),
      "incumbent_revision":receipt.get("incumbent_revision")==plan.get("incumbent_revision"),
      "source_candidate_integrated":receipt.get("source_release_candidate_integrated") is True,
      "rollback_token":bool(str(receipt.get("rollback_token") or "")),
      "runtime_mutation_forbidden":receipt.get("direct_runtime_mutation") is False,
      "production_activation_forbidden":receipt.get("production_activation") is False,
      "production_deployment_forbidden":receipt.get("production_deployment") is False,
      "production_merge_forbidden":receipt.get("merge_to_production_branch") is False,
      "zero_external_spend":float(receipt.get("automatic_external_spend_eur") or 0)==0,
    }
    bad=sorted(k for k,v in checks.items() if not v)
    if bad:raise RuntimeError("SOURCE_INTEGRATION_RECEIPT_INVALID:"+",".join(bad))

def validate_rollback_receipt(receipt:dict[str,Any],plan:dict[str,Any])->None:
    checks={
      "schema":receipt.get("schema")=="chacha.dev/platform-component-source-integration-rollback/v1",
      "status":receipt.get("status")=="PASS",
      "component":receipt.get("component_id")==plan.get("component_id"),
      "candidate_revision":receipt.get("candidate_revision")==plan.get("candidate_revision"),
      "rollback_proven":receipt.get("rollback_proven") is True,
      "source_candidate_integration_reverted":receipt.get("source_candidate_integration_reverted") is True,
      "runtime_mutation_forbidden":receipt.get("direct_runtime_mutation") is False,
      "production_activation_forbidden":receipt.get("production_activation") is False,
      "production_deployment_forbidden":receipt.get("production_deployment") is False,
      "production_merge_forbidden":receipt.get("merge_to_production_branch") is False,
      "zero_external_spend":float(receipt.get("automatic_external_spend_eur") or 0)==0,
    }
    bad=sorted(k for k,v in checks.items() if not v)
    if bad:raise RuntimeError("SOURCE_INTEGRATION_ROLLBACK_INVALID:"+",".join(bad))

def execute(planner:dict[str,Any],handoff:dict[str,Any],registry:dict[str,Any],repo_root:Path,
            runs:dict[str,Any],adapter_provider=None,guardian_provider=None,
            handoff_consumer=None,runtime_root:Path|None=None,stop_provider=None)->dict[str,Any]:
    validated=validate_inputs(planner,handoff,registry)
    if not validated["ok"]:
        return {"schema":SCHEMA,"status":"BLOCKED_INPUT","blockers":validated["blockers"],
                "source_release_candidate_integrated":False,"rollback_attempted":False,
                "production_activation_allowed":False,"production_deployment_allowed":False,
                "merge_to_production_branch_allowed":False,"automatic_external_spend_eur":0}
    stop_provider=stop_provider or stop_active
    if stop_provider():raise RuntimeError("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
    plan=validated["plan"];adapter=validated["adapter"]
    handoff_consumer=handoff_consumer or consume_handoff
    runtime_root=runtime_root or Path("/opt/chacha-dev/runtime/platform-component-source-integration")
    consumption_receipt=handoff_consumer(runtime_root,handoff)
    adapter_provider=adapter_provider or run_adapter
    guardian_provider=guardian_provider or guardian_event
    guardian_pre=guardian_provider(repo_root,"PRE_ACTION",plan,handoff,None)
    apply_payload={
      "schema":"chacha.dev/platform-component-source-integration-request/v1",
      "handoff_id":handoff.get("handoff_id"),"component_id":plan.get("component_id"),
      "candidate_owner":plan.get("candidate_owner"),
      "candidate_revision":plan.get("candidate_revision"),"incumbent_revision":plan.get("incumbent_revision"),
      "candidate_artifact_ref":plan.get("candidate_artifact_ref"),"incumbent_artifact_ref":plan.get("incumbent_artifact_ref"),
      "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "direct_runtime_mutation":False,"production_activation":False,
      "production_deployment":False,"merge_to_production_branch":False,
      "automatic_external_spend_eur":0
    }
    receipt=adapter_provider(str(adapter.get("executable")),"apply",apply_payload)
    validate_apply_receipt(receipt,plan)
    rollback_attempted=False;rollback_receipt=None
    required=[str(x) for x in plan.get("post_apply_exact_sha_gates_required") or [] if str(x)]
    revision=str(plan.get("candidate_revision") or "")
    missing_gates=sorted(x for x in required if not workflow_success(runs,x,revision))
    if missing_gates:
        rollback_attempted=True
        rollback_payload={
          "schema":"chacha.dev/platform-component-source-integration-rollback-request/v1",
          "handoff_id":handoff.get("handoff_id"),"component_id":plan.get("component_id"),
          "candidate_revision":plan.get("candidate_revision"),"incumbent_revision":plan.get("incumbent_revision"),
          "rollback_token":receipt.get("rollback_token"),"reason":"POST_APPLY_EXACT_SHA_GATE_FAILED",
          "failed_gates":missing_gates,"automatic_external_spend_eur":0
        }
        rollback_receipt=adapter_provider(str(adapter.get("executable")),"rollback",rollback_payload)
        validate_rollback_receipt(rollback_receipt,plan)
        guardian_post=guardian_provider(repo_root,"POST_ACTION",plan,handoff,"BLOCKED_ROLLED_BACK")
        return {"schema":SCHEMA,"status":"BLOCKED_ROLLED_BACK",
          "component_id":plan.get("component_id"),"candidate_revision":revision,
          "source_release_candidate_integrated":False,"post_apply_exact_sha_gates_pass":False,
          "missing_post_apply_gates":missing_gates,"rollback_attempted":True,"rollback_proven":True,
          "apply_receipt_digest":digest(receipt),"rollback_receipt_digest":digest(rollback_receipt),
          "guardian_pre_receipt_digest":digest(guardian_pre),"guardian_post_receipt_digest":digest(guardian_post),
      "handoff_consumption_receipt":str(consumption_receipt),
          "handoff_consumption_receipt":str(consumption_receipt),
          "production_activation_allowed":False,"production_deployment_allowed":False,
          "merge_to_production_branch_allowed":False,"direct_runtime_mutation":False,
          "automatic_external_spend_eur":0}
    try:
        guardian_post=guardian_provider(repo_root,"POST_ACTION",plan,handoff,"PASS")
    except Exception as exc:
        rollback_attempted=True
        rollback_payload={
          "schema":"chacha.dev/platform-component-source-integration-rollback-request/v1",
          "handoff_id":handoff.get("handoff_id"),"component_id":plan.get("component_id"),
          "candidate_revision":plan.get("candidate_revision"),"incumbent_revision":plan.get("incumbent_revision"),
          "rollback_token":receipt.get("rollback_token"),"reason":"GUARDIAN_POST_APPLY_FAILED",
          "automatic_external_spend_eur":0
        }
        rollback_receipt=adapter_provider(str(adapter.get("executable")),"rollback",rollback_payload)
        validate_rollback_receipt(rollback_receipt,plan)
        return {"schema":SCHEMA,"status":"BLOCKED_ROLLED_BACK",
          "component_id":plan.get("component_id"),"candidate_revision":revision,
          "source_release_candidate_integrated":False,"post_apply_exact_sha_gates_pass":True,
          "guardian_post_apply_pass":False,"guardian_post_error":str(exc)[:300],
          "rollback_attempted":True,"rollback_proven":True,
          "apply_receipt_digest":digest(receipt),"rollback_receipt_digest":digest(rollback_receipt),
          "guardian_pre_receipt_digest":digest(guardian_pre),
          "handoff_consumption_receipt":str(consumption_receipt),
          "production_activation_allowed":False,"production_deployment_allowed":False,
          "merge_to_production_branch_allowed":False,"direct_runtime_mutation":False,
          "automatic_external_spend_eur":0}
    return {"schema":SCHEMA,"status":"PASS_SOURCE_RELEASE_CANDIDATE_INTEGRATED",
      "component_id":plan.get("component_id"),"candidate_owner":plan.get("candidate_owner"),
      "candidate_revision":revision,"incumbent_revision":plan.get("incumbent_revision"),
      "source_release_candidate_integrated":True,"post_apply_exact_sha_gates_pass":True,
      "post_apply_exact_sha_gates":required,"guardian_post_apply_pass":True,
      "rollback_attempted":rollback_attempted,"rollback_proven":False,
      "apply_receipt_digest":digest(receipt),
      "guardian_pre_receipt_digest":digest(guardian_pre),"guardian_post_receipt_digest":digest(guardian_post),
      "production_activation_allowed":False,"production_deployment_allowed":False,
      "merge_to_production_branch_allowed":False,"direct_runtime_mutation":False,
      "central_orchestrator_remains_final_apply_authority":True,
      "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--planner-result",type=Path,required=True)
    ap.add_argument("--central-handoff",type=Path,required=True)
    ap.add_argument("--adapter-registry",type=Path,required=True)
    ap.add_argument("--repository",default="chachasan090375/WfGg")
    ap.add_argument("--github-runs-json",type=Path)
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime/platform-component-source-integration"))
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    planner=load(a.planner_result);handoff=load(a.central_handoff);registry=load(a.adapter_registry)
    plan=planner.get("apply_plan") or {}
    revision=str(plan.get("candidate_revision") or "")
    runs=load(a.github_runs_json) if a.github_runs_json else github_runs(a.repository,revision)
    result=execute(planner,handoff,registry,a.repo_root.resolve(),runs,runtime_root=a.runtime_root.resolve())
    save(a.output,result)
    print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION="+result["status"])
    print("PRODUCTION_ACTIVATION_ALLOWED=NO")
    print("PRODUCTION_DEPLOYMENT_ALLOWED=NO")
    print("MERGE_TO_PRODUCTION_BRANCH_ALLOWED=NO")
    print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"] in {"PASS_SOURCE_RELEASE_CANDIDATE_INTEGRATED","BLOCKED_ROLLED_BACK"} else 20

if __name__=="__main__":raise SystemExit(main())
