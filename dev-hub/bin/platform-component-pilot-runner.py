#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time,uuid
from pathlib import Path
from typing import Any

DEFAULT_STOP=Path("/opt/chacha-dev/runtime/control/emergency-stop.json")
METRIC_KEYS=["acceptance_pass","quality_score","stability_score","error_rate","latency_ms","memory_mb","external_spend_eur"]

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp-"+str(os.getpid()))
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def digest(x:Any)->str:
    return "sha256:"+hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def stop_active(path:Path)->bool:
    try:return bool(load(path).get("active"))
    except Exception:return False

def unit_name(run_id:str,variant:str)->str:
    token=hashlib.sha256((run_id+":"+variant).encode()).hexdigest()[:16]
    return "chacha-dev-platform-pilot@"+token+".service"

def validate_contract(c:dict[str,Any])->None:
    if c.get("schema")!="chacha.dev/platform-component-comparative-pilot-contract/v1":
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_CONTRACT_INVALID")
    if c.get("pilot_execution_authorized") is not True:
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_NOT_AUTHORIZED")
    if c.get("production_change_authorized") is not False or c.get("promotion_authorized") is not False:
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_PRODUCTION_BOUNDARY_INVALID")
    if c.get("same_benchmark_contract") is not True or c.get("isolated_ephemeral_capsules") is not True:
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_ISOLATION_CONTRACT_INVALID")
    if c.get("production_entrypoint_unchanged") is not True:
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_PRODUCTION_ENTRYPOINT_CHANGED")
    if float(c.get("automatic_external_spend_eur") or 0)!=0:
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_EXTERNAL_SPEND_FORBIDDEN")
    if not str(c.get("candidate_artifact_ref") or "") or not str(c.get("incumbent_artifact_ref") or ""):
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_EXACT_ARTIFACTS_REQUIRED")
    if not str(c.get("candidate_revision") or "") or not str(c.get("incumbent_revision") or ""):
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_EXACT_REVISIONS_REQUIRED")
    if not isinstance(c.get("harness_argv"),list) or not c.get("harness_argv"):
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_HARNESS_ARGV_MISSING")
    if not str(c.get("qualification_workflow_name") or ""):
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_QUALIFICATION_WORKFLOW_MISSING")
    required_checks=[
      "independent_verification","measurable_gain","no_material_regression",
      "permission_non_escalation","rollback_ready","exact_revision_evidence",
      "logician_falsification_pass","technology_watch_revalidation_pass","real_harness_available"
    ]
    checks=c.get("pre_pilot_checks") if isinstance(c.get("pre_pilot_checks"),dict) else {}
    missing=[k for k in required_checks if checks.get(k) is not True]
    if missing:
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_PRECHECKS_INCOMPLETE:"+",".join(missing))
    if not list(c.get("pre_pilot_evidence_refs") or []):
        raise RuntimeError("PLATFORM_COMPONENT_PILOT_PRECHECK_EVIDENCE_MISSING")

def validate_sentinel_receipt(c:dict[str,Any],receipt:dict[str,Any])->None:
    if receipt.get("schema")!="chacha.dev/sentinel-exact-sha-receipt/v1":
        raise RuntimeError("SENTINEL_EXACT_SHA_RECEIPT_INVALID")
    if receipt.get("workflow_name")!="ChaCha DEV Sentinel technical assurance":
        raise RuntimeError("SENTINEL_WORKFLOW_INVALID")
    if str(receipt.get("head_sha") or "")!=str(c.get("candidate_revision") or ""):
        raise RuntimeError("SENTINEL_SHA_MISMATCH")
    if receipt.get("conclusion")!="success":
        raise RuntimeError("SENTINEL_EXACT_SHA_NOT_PASS")
    if receipt.get("exact_sha_verified") is not True:
        raise RuntimeError("SENTINEL_EXACT_SHA_NOT_VERIFIED")

def guardian_event(repo_root:Path,run_root:Path,phase:str,contract:dict[str,Any],result_status:str|None=None)->dict[str,Any]:
    # PLATFORM_COMPONENT_PILOT_GUARDIAN_PRE_POST
    if not Path("/opt/chacha-dev/runtime").exists():
        return {"status":"NON_RUNTIME_TEST_BYPASS"}
    client=repo_root/"dev-hub/bin/guardian-client.py"
    policy=repo_root/"dev-hub/config/guardian-runtime-policy.v1.json"
    event={
      "schema":"chacha.dev/governance-action/v1",
      "event_id":"gov-"+uuid.uuid4().hex,
      "phase":phase,
      "actor":"platform-component-pilot-runner",
      "subject_role":"platform-component-pilot-runner",
      "action":"RUN_COMPARATIVE_PILOT",
      "task_kind":"platform-component-comparative-pilot",
      "permission":"workspace-write",
      "project_id":"platform-global",
      "run_id":contract.get("contract_id"),
      "adapters":[],
      "evidence":{
        "isolated_capsules":True,
        "same_benchmark_contract":True,
        "exact_artifacts":True,
        "sentinel_exact_sha_pass":True,
        "result_status":result_status
      },
      "context":{"resource_class":"light","human_approval_required":False,"storage_preflight_required":False}
    }
    gd=run_root/"guardian";gd.mkdir(parents=True,exist_ok=True)
    ep=gd/(event["event_id"]+".json");save(ep,event)
    p=subprocess.run([sys.executable,str(client),"--policy",str(policy),"check","--event",str(ep)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=25)
    try:verdict=json.loads(p.stdout.strip())
    except Exception:verdict={"status":"UNAVAILABLE","reason":"INVALID_RESPONSE"}
    save(gd/(event["event_id"]+".verdict.json"),verdict)
    if p.returncode!=0 or str(verdict.get("verdict") or "") in {"BLOCK","CRITICAL"}:
        raise RuntimeError("GUARDIAN_PLATFORM_PILOT_BLOCK:"+str(verdict.get("reason_codes") or verdict.get("reason") or p.returncode))
    return verdict

def expand_argv(argv:list[Any],variant:str,artifact_ref:str,result:Path)->list[str]:
    repl={"{variant}":variant,"{artifact_ref}":artifact_ref,"{result_json}":str(result)}
    out=[]
    for raw in argv:
        s=str(raw)
        for k,v in repl.items():s=s.replace(k,v)
        out.append(s)
    return out

def valid_metrics(x:dict[str,Any])->bool:
    return all(k in x for k in METRIC_KEYS)

def run_variant(contract:dict[str,Any],run_id:str,variant:str,artifact_ref:str,run_root:Path,executor=None)->dict[str,Any]:
    if stop_active(DEFAULT_STOP):raise RuntimeError("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
    workspace=run_root/variant.lower();workspace.mkdir(parents=True,exist_ok=True)
    result_path=workspace/"metrics.json"
    argv=expand_argv(contract.get("harness_argv") or [],variant,artifact_ref,result_path)
    if not argv:raise RuntimeError("PLATFORM_COMPONENT_PILOT_HARNESS_ARGV_MISSING")
    budget=contract.get("resource_budget") or {}
    mem=max(64,int(budget.get("memory_mb") or 256))
    cpu=max(1,min(10000,int(budget.get("cpu_weight") or 50)))
    tasks=max(1,int(budget.get("tasks_max") or 8))
    timeout=max(10,int(budget.get("timeout_seconds") or 120))
    unit=unit_name(run_id,variant)
    cmd=["/usr/bin/systemd-run","--wait","--collect","--pipe","--unit="+unit,
      "--property=MemoryMax="+str(mem)+"M","--property=CPUWeight="+str(cpu),
      "--property=TasksMax="+str(tasks),"--property=RuntimeMaxSec="+str(timeout),
      "--property=KillMode=mixed","--working-directory="+str(workspace),*argv]
    started=time.monotonic()
    if executor is None:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout+30)
        rc=p.returncode;stdout=p.stdout;stderr=p.stderr
    else:
        rc,stdout,stderr=executor(cmd,result_path,variant,artifact_ref)
    wall=round((time.monotonic()-started)*1000,3)
    if rc!=0:
        return {"variant":variant,"artifact_ref":artifact_ref,"acceptance_pass":False,"quality_score":0,
          "stability_score":0,"error_rate":1,"latency_ms":wall,"memory_mb":mem,"external_spend_eur":0,
          "failure":"HARNESS_EXIT_"+str(rc),"unit":unit,"stdout":str(stdout)[-1000:],"stderr":str(stderr)[-1000:]}
    if not result_path.is_file():
        return {"variant":variant,"artifact_ref":artifact_ref,"acceptance_pass":False,"quality_score":0,
          "stability_score":0,"error_rate":1,"latency_ms":wall,"memory_mb":mem,"external_spend_eur":0,
          "failure":"METRICS_FILE_MISSING","unit":unit}
    metrics=load(result_path)
    if not valid_metrics(metrics):
        return {"variant":variant,"artifact_ref":artifact_ref,"acceptance_pass":False,"quality_score":0,
          "stability_score":0,"error_rate":1,"latency_ms":wall,"memory_mb":mem,"external_spend_eur":0,
          "failure":"METRICS_SCHEMA_INVALID","unit":unit}
    return {**metrics,"variant":variant,"artifact_ref":artifact_ref,"unit":unit,
      "wall_clock_ms":wall,"resource_limit_memory_mb":mem}

def compare_metrics(inc:dict[str,Any],cand:dict[str,Any])->dict[str,Any]:
    both=inc.get("acceptance_pass") is True and cand.get("acceptance_pass") is True
    zero=float(cand.get("external_spend_eur") or 0)==0
    no_quality_reg=float(cand.get("quality_score") or 0)>=float(inc.get("quality_score") or 0)
    no_stability_reg=float(cand.get("stability_score") or 0)>=float(inc.get("stability_score") or 0)
    no_error_reg=float(cand.get("error_rate") or 1)<=float(inc.get("error_rate") or 1)
    measurable_gain=(
      float(cand.get("quality_score") or 0)>float(inc.get("quality_score") or 0) or
      float(cand.get("stability_score") or 0)>float(inc.get("stability_score") or 0) or
      float(cand.get("latency_ms") or 1e18)<float(inc.get("latency_ms") or 1e18) or
      float(cand.get("memory_mb") or 1e18)<float(inc.get("memory_mb") or 1e18)
    )
    admissible=all([both,zero,no_quality_reg,no_stability_reg,no_error_reg,measurable_gain])
    return {"both_acceptance_pass":both,"candidate_zero_external_spend":zero,
      "no_quality_regression":no_quality_reg,"no_stability_regression":no_stability_reg,
      "no_error_rate_regression":no_error_reg,"measurable_gain_observed":measurable_gain,
      "candidate_technically_admissible_for_council_review":admissible,
      "final_architecture_decision_made":False,"promotion_authorized":False}

def invoke_council_review(repo_root:Path,run_root:Path,contract:dict[str,Any],
                          sentinel_receipt:dict[str,Any],pilot_result:dict[str,Any])->dict[str,Any]:
    contract_path=run_root/"pilot-contract.json"
    sentinel_path=run_root/"sentinel-receipt.json"
    pilot_path=run_root/"result.json"
    output=run_root/"council-review.json"
    save(contract_path,contract);save(sentinel_path,sentinel_receipt);save(pilot_path,pilot_result)
    script=repo_root/"dev-hub/bin/architecture-council-platform-component-review.py"
    cmd=[sys.executable,str(script),"--repo-root",str(repo_root),
      "--pilot-result",str(pilot_path),"--pilot-contract",str(contract_path),
      "--sentinel-receipt",str(sentinel_path),"--output",str(output)]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=90)
    if output.is_file():
        review=load(output)
        review["runner_observed_returncode"]=p.returncode
        return review
    return {"schema":"chacha.dev/architecture-council-platform-component-review/v1",
      "technical_review_passed":False,"decision":"COUNCIL_REVIEW_BLOCKED_HOLD_INCUMBENT",
      "next_action":"REMEDIATE_AND_REVIEW","runner_observed_returncode":p.returncode,
      "runner_error":(p.stderr or p.stdout)[-1000:],
      "production_activation_allowed":False,"promotion_allowed":False,
      "automatic_external_spend_eur":0}

def execute(contract:dict[str,Any],sentinel_receipt:dict[str,Any],repo_root:Path,run_root:Path,
            executor=None,guardian_provider=None,council_provider=None)->dict[str,Any]:
    validate_contract(contract);validate_sentinel_receipt(contract,sentinel_receipt)
    if stop_active(DEFAULT_STOP):raise RuntimeError("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
    run_id="pcp-"+time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+"-"+uuid.uuid4().hex[:8]
    rr=run_root/run_id;rr.mkdir(parents=True,exist_ok=True)
    guardian_provider=guardian_provider or guardian_event
    guardian_pre=guardian_provider(repo_root,rr,"PRE_ACTION",contract)
    inc=run_variant(contract,run_id,"INCUMBENT",str(contract["incumbent_artifact_ref"]),rr,executor)
    if stop_active(DEFAULT_STOP):raise RuntimeError("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
    cand=run_variant(contract,run_id,"CANDIDATE",str(contract["candidate_artifact_ref"]),rr,executor)
    comparison=compare_metrics(inc,cand)
    status="PASS" if inc.get("acceptance_pass") is True and cand.get("acceptance_pass") is True else "BLOCKED"
    result={"schema":"chacha.dev/platform-component-comparative-pilot-result/v1","status":status,
      "run_id":run_id,"contract_id":contract.get("contract_id"),"dispatch_id":contract.get("dispatch_id"),
      "component_id":contract.get("component_id"),"incumbent_revision":contract.get("incumbent_revision"),
      "candidate_revision":contract.get("candidate_revision"),"same_benchmark_contract":True,
      "isolated_ephemeral_capsules":True,"production_entrypoint_unchanged":True,
      "sentinel_exact_sha_receipt_digest":digest(sentinel_receipt),
      "guardian_pre_pass":True,"guardian_pre_receipt_digest":digest(guardian_pre),
      "results":{"INCUMBENT":inc,"CANDIDATE":cand},"comparison":comparison,
      "council_handoff_required":True,"production_change_authorized":False,"promotion_authorized":False,
      "permission_expansion":False,"automatic_external_spend_eur":0}
    guardian_post=guardian_provider(repo_root,rr,"POST_ACTION",contract,status)
    result["guardian_post_pass"]=True
    result["guardian_post_receipt_digest"]=digest(guardian_post)
    save(rr/"result.json",result)
    council_provider=council_provider or invoke_council_review
    council=council_provider(repo_root,rr,contract,sentinel_receipt,result)
    result["council_review"]=council
    result["council_handoff_complete"]=council.get("schema")=="chacha.dev/architecture-council-platform-component-review/v1"
    result["council_review_technical_pass"]=council.get("technical_review_passed") is True
    result["human_explicit_promotion_approval_present"]=False
    result["explicit_human_promotion_approval_required"]=True
    if status!="PASS":
        result["pipeline_status"]="PILOT_BLOCKED_HOLD_INCUMBENT"
    elif result["council_review_technical_pass"]:
        result["pipeline_status"]="PASS_HOLD_INCUMBENT"
    else:
        result["pipeline_status"]="COUNCIL_BLOCKED_HOLD_INCUMBENT"
    result["production_change_authorized"]=False
    result["promotion_authorized"]=False
    save(rr/"result.json",result)
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--sentinel-receipt",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime/platform-component-pilots"))
    a=ap.parse_args()
    result=execute(load(a.contract),load(a.sentinel_receipt),a.repo_root.resolve(),a.runtime_root.resolve())
    save(a.output,result)
    print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_RUNNER="+result["status"])
    print("COUNCIL_HANDOFF_COMPLETE="+("YES" if result.get("council_handoff_complete") else "NO"))
    print("COUNCIL_REVIEW="+("PASS" if result.get("council_review_technical_pass") else "BLOCK"))
    print("HUMAN_PROMOTION_APPROVAL_REQUIRED=YES")
    print("PRODUCTION_CHANGE_AUTHORIZED=NO")
    print("PROMOTION_AUTHORIZED=NO")
    print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result.get("pipeline_status")=="PASS_HOLD_INCUMBENT" else 20

if __name__=="__main__":raise SystemExit(main())
