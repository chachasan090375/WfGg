#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
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

POLICY_SCHEMA="chacha.dev/capability-build-loop/v1"
REQUEST_SCHEMA="chacha.dev/capability-build-request/v1"
RESULT_SCHEMA="chacha.dev/capability-build-result/v1"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value

def save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def digest_file(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def run(argv:list[str|Path],cwd:Path|None=None,stdout_path:Path|None=None)->subprocess.CompletedProcess[str]:
    args=[str(x) for x in argv]
    proc=subprocess.run(args,cwd=str(cwd) if cwd else None,text=True,
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if stdout_path is not None:
        stdout_path.write_text(proc.stdout,encoding="utf-8")
    if proc.returncode!=0:
        raise SystemExit(
          "COMMAND_FAILED="+json.dumps({
            "argv":args,"returncode":proc.returncode,
            "stdout":proc.stdout[-4000:],"stderr":proc.stderr[-4000:]
          },ensure_ascii=False)
        )
    return proc

def validate_slug(value:str,label:str)->str:
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}",value):
        raise SystemExit(f"{label}_INVALID")
    return value

def validate_request(req:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if req.get("schema")!=REQUEST_SCHEMA:
        raise SystemExit("BUILD_REQUEST_SCHEMA_INVALID")
    if policy.get("schema")!=POLICY_SCHEMA:
        raise SystemExit("BUILD_POLICY_SCHEMA_INVALID")
    profile_id=str(req.get("profile") or "")
    profile=(policy.get("profiles") or {}).get(profile_id)
    blockers=[]
    if not isinstance(profile,dict):
        blockers.append("UNSUPPORTED_BUILD_PROFILE")
        profile={}
    cap=validate_slug(str(req.get("capability") or ""),"CAPABILITY")
    provider=validate_slug(str(req.get("provider_id") or ""),"PROVIDER")
    adapter=validate_slug(str(req.get("adapter_id") or ""),"ADAPTER")
    supports=req.get("supports")
    if supports!=profile.get("supports"):
        blockers.append("SUPPORTS_OUTSIDE_PROFILE")
    if str(req.get("execution") or "")!=str(profile.get("execution") or ""):
        blockers.append("EXECUTION_OUTSIDE_PROFILE")
    if bool(req.get("network_access")) is not False or profile.get("network_access") is not False:
        blockers.append("NETWORK_ACCESS_FORBIDDEN")
    if bool(req.get("credentials_required")) is not False or profile.get("credentials_required") is not False:
        blockers.append("CREDENTIALS_FORBIDDEN")
    if bool(req.get("production_capable")) is not False or profile.get("production_capable") is not False:
        blockers.append("PRODUCTION_CAPABILITY_FORBIDDEN")
    try: spend=float(req.get("automatic_external_spend_eur") or 0)
    except Exception: spend=999999.0
    if spend!=0:
        blockers.append("NONZERO_EXTERNAL_SPEND")
    tw=req.get("technology_watch") if isinstance(req.get("technology_watch"),dict) else {}
    if tw.get("consulted") is not True:
        blockers.append("TECHNOLOGY_WATCH_REQUIRED")
    council=req.get("architecture_council") if isinstance(req.get("architecture_council"),dict) else {}
    if council.get("decision")!="APPROVED" or not council.get("decision_id"):
        blockers.append("ARCHITECTURE_COUNCIL_APPROVAL_REQUIRED")
    return {
      "capability":cap,"provider_id":provider,"adapter_id":adapter,
      "profile_id":profile_id,"profile":profile,"blockers":blockers,
      "eligible":not blockers,"automatic_external_spend_eur":spend
    }

def generated_source(adapter:str,provider:str,capability:str)->str:
    return f'''#!/usr/bin/env python3
import datetime
import hashlib
import json
import sys

ADAPTER_ID={adapter!r}
PROVIDER_ID={provider!r}
CAPABILITY_ID={capability!r}

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def result(status, project, task_id, summary, outputs=None, evidence=None):
    return {{
      "schema":"chacha.dev/task-result/v1",
      "project":project,
      "task_id":task_id,
      "producer":ADAPTER_ID,
      "status":status,
      "summary":summary,
      "observed_at":now_iso(),
      "outputs":outputs or [],
      "evidence":evidence or [],
      "verification":{{"status":"UNVERIFIED","method":"none"}}
    }}

def main():
    try:
        envelope=json.load(sys.stdin)
    except Exception:
        print(json.dumps(result("BLOCKED","","","INVALID_JSON_INPUT")))
        return 2
    project=str(envelope.get("project") or "")
    task=envelope.get("task") if isinstance(envelope.get("task"),dict) else {{}}
    task_id=str(task.get("id") or "")
    permission=str(task.get("permission") or "")
    bindings=envelope.get("bindings") if isinstance(envelope.get("bindings"),list) else []
    binding=next((b for b in bindings if isinstance(b,dict)
                  and b.get("capability")==CAPABILITY_ID
                  and b.get("provider")==PROVIDER_ID
                  and b.get("adapter")==ADAPTER_ID),None)
    if envelope.get("schema")!="chacha.dev/dispatch-envelope/v1":
        out=result("BLOCKED",project,task_id,"INPUT_SCHEMA_INVALID")
    elif permission!="read":
        out=result("BLOCKED",project,task_id,"PERMISSION_NOT_ALLOWED")
    elif binding is None:
        out=result("BLOCKED",project,task_id,"BINDING_MISMATCH")
    else:
        details={{"capability":CAPABILITY_ID,"provider":PROVIDER_ID,
                 "adapter":ADAPTER_ID,"network_access":False,
                 "credentials_used":False,"production_mutation":False}}
        raw=json.dumps(details,sort_keys=True,separators=(",",":")).encode()
        out=result("OK",project,task_id,"SAFE_STRUCTURED_READ_ADAPTER_OK",
                   outputs=[{{"type":"artifact","id":CAPABILITY_ID+"-status"}}],
                   evidence=[{{"source":"generated-safe-template",
                              "digest":"sha256:"+hashlib.sha256(raw).hexdigest(),
                              "observed_at":now_iso(),"details":details}}])
    print(json.dumps(out,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
'''

def static_source_guard(source_path:Path,policy:dict[str,Any])->None:
    source=source_path.read_text(encoding="utf-8")
    tree=ast.parse(source)
    forbidden_imports=set(policy.get("forbidden_python_imports") or [])
    forbidden_calls=set(policy.get("forbidden_python_calls") or [])
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for alias in node.names:
                root=alias.name.split(".",1)[0]
                if root in forbidden_imports:
                    raise SystemExit(f"GENERATED_SOURCE_FORBIDDEN_IMPORT:{root}")
        elif isinstance(node,ast.ImportFrom):
            root=(node.module or "").split(".",1)[0]
            if root in forbidden_imports:
                raise SystemExit(f"GENERATED_SOURCE_FORBIDDEN_IMPORT:{root}")
        elif isinstance(node,ast.Call):
            name=None
            if isinstance(node.func,ast.Name):
                name=node.func.id
            elif isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
                name=node.func.value.id+"."+node.func.attr
            if name in forbidden_calls:
                raise SystemExit(f"GENERATED_SOURCE_FORBIDDEN_CALL:{name}")

def materialize(req:dict[str,Any],policy:dict[str,Any],repo_root:Path,workspace:Path,
                base_registry:Path)->dict[str,Path|str]:
    v=validate_request(req,policy)
    if not v["eligible"]:
        raise SystemExit("BUILD_SPECIALIST_REQUIRED:"+",".join(v["blockers"]))
    capability=str(v["capability"]);provider=str(v["provider_id"]);adapter=str(v["adapter_id"])
    registry=load(base_registry)
    if provider in (registry.get("providers") or {}):
        raise SystemExit("PROVIDER_ALREADY_REGISTERED")
    if adapter in (registry.get("adapters") or {}):
        raise SystemExit("ADAPTER_ALREADY_REGISTERED")

    gen_dir=repo_root/"dev-hub/generated/v641"
    gen_dir.mkdir(parents=True,exist_ok=True)
    source_path=gen_dir/(adapter+".py")
    source_path.write_text(generated_source(adapter,provider,capability),encoding="utf-8")
    os.chmod(source_path,0o755)
    static_source_guard(source_path,policy)

    workspace.mkdir(parents=True,exist_ok=True)
    registry_path=workspace/"provider-adapters.json"
    reg=json.loads(json.dumps(registry))
    reg.setdefault("providers",{})[provider]={
      "adapter":adapter,"kind":"generated-safe-local-runtime","execution":"vps"
    }
    reg.setdefault("adapters",{})[adapter]={
      "status":"DESIGNED","executable":None,"supports":["read"]
    }
    save(registry_path,reg)

    fixture={
      "schema":"chacha.dev/dispatch-envelope/v1",
      "project":str(req.get("project_id") or "v641-build-project"),
      "transition":"BUILD->VERIFY",
      "run_id":"v641-"+adapter+"-sandbox",
      "wave":1,
      "task":{
        "id":"v641-"+capability+"-probe","kind":"verification","description":"V6.41 safe generated adapter probe",
        "owner_role":"platform-engineer","permission":"read",
        "outputs":[{"type":"artifact","id":capability+"-status"}],
        "verification":{"required":True,"mode":"machine","self_certification_allowed":False,
                        "required_evidence":["source","timestamp","digest"]}
      },
      "bindings":[{
        "capability":capability,"provider":provider,"adapter":adapter,
        "fallback_used":False,"health_state":"HEALTHY"
      }],
      "policy_context":{
        "resource_class":"light","requires_storage_preflight":False,
        "human_approval_required":False,"approval_id":None,"timeout_seconds":20
      },
      "workspace":None,
      "metadata":{
        "certification":{"sandbox":True,"network_scope":"loopback-only"},
        "http_smoke":{"url":"http://127.0.0.1/v641-no-network-used"},
        "v641_safe_adapter":{"network_access":False,"credentials_required":False}
      }
    }
    fixture_path=workspace/"fixture.json";save(fixture_path,fixture)

    rel_source=source_path.relative_to(repo_root)
    provisioning={
      "schema":"chacha.dev/adapter-provisioning/v1",
      "target_root":"/opt/chacha-dev/adapters",
      "sandbox_root_override_allowed":True,
      "probe_timeout_seconds":10,
      "adapters":{
        adapter:{
          "source":str(rel_source),
          "namespace":provider,
          "version":str(v["profile"].get("adapter_version") or "0.1.0"),
          "executable_name":adapter,
          "mode":"0755",
          "current_link_name":"current",
          "probe":{
            "input":fixture,
            "expected_schema":"chacha.dev/task-result/v1",
            "expected_status":"OK",
            "expected_producer":adapter,
            "expected_verification_status":"UNVERIFIED"
          }
        }
      }
    }
    provisioning_path=workspace/"adapter-provisioning.json";save(provisioning_path,provisioning)

    rollback={
      "schema":"chacha.dev/adapter-rollbacks/v1",
      "principles":{"rollback_is_explicit":True},
      "adapters":{
        adapter:{
          "enabled":True,"from_status":"ENABLED","target_status":"DISABLED",
          "owner_role":"platform-engineer",
          "triggers":["repeatable-runtime-failure","provider-health-unavailable","policy-or-security-block"],
          "executable_strategy":"retain-for-forensics",
          "steps":[
            "stop scheduling new tasks to "+adapter,
            "apply ENABLED->DISABLED through adapter promotion",
            "preserve build and promotion receipts"
          ],
          "verification":[
            "adapter registry status is DISABLED",
            "scheduler no longer selects "+adapter
          ]
        }
      }
    }
    rollback_path=workspace/"adapter-rollbacks.json";save(rollback_path,rollback)
    return {
      "capability":capability,"provider":provider,"adapter":adapter,
      "source":source_path,"registry":registry_path,"fixture":fixture_path,
      "provisioning":provisioning_path,"rollback":rollback_path
    }

def build_pilot(req:dict[str,Any],policy:dict[str,Any],repo_root:Path,workspace:Path,
                runtime_root:Path,base_registry:Path,output:Path,overlay:Path)->dict[str,Any]:
    m=materialize(req,policy,repo_root,workspace,base_registry)
    adapter=str(m["adapter"]);provider=str(m["provider"]);capability=str(m["capability"])
    registry=Path(m["registry"]);fixture=Path(m["fixture"]);source=Path(m["source"])

    py=sys.executable
    bin_dir=repo_root/"dev-hub/bin"
    cfg=repo_root/"dev-hub/config"

    contract_report=workspace/"contract-static.json"
    run([py,bin_dir/"adapter-contract-harness.py","--registry",registry,
         "--policy",cfg/"adapter-contract.v1.json","--report",contract_report])
    cr=load(contract_report)
    if (cr.get("static") or {}).get("status")!="PASS":
        raise SystemExit("STATIC_CONTRACT_FAILED")

    static_ev={
      "schema":"chacha.dev/adapter-promotion-evidence/v1","adapter":adapter,
      "observed_at":now_iso(),
      "evidence":{"static-contract-pass":{"status":"PASS","source":"v641:contract-harness","observed_at":now_iso()}},
      "approvals":[]
    }
    static_ev_path=workspace/"static-evidence.json";save(static_ev_path,static_ev)
    contract_receipt=workspace/"contract-ok-receipt.json"
    run([py,bin_dir/"adapter-promotion.py","--registry",registry,
         "--contract",cfg/"adapter-contract.v1.json","--policy",cfg/"adapter-promotion.v1.json",
         "--evidence",static_ev_path,"--json","apply","--adapter",adapter,
         "--target","CONTRACT_OK","--actor","capability-build-loop",
         "--receipt",contract_receipt,"--apply"],stdout_path=workspace/"contract-ok-report.json")

    provision_receipt=workspace/"provisioning-receipt.json"
    run([py,bin_dir/"adapter-provision.py","--policy",m["provisioning"],"--root",runtime_root,
         "apply","--adapter",adapter,"--actor","capability-build-loop",
         "--receipt",provision_receipt,"--apply"])
    run([py,bin_dir/"adapter-provision.py","--policy",m["provisioning"],"--root",runtime_root,
         "verify","--adapter",adapter,"--receipt",provision_receipt])
    pr=load(provision_receipt)
    executable=Path(str(pr["executable_path"]))

    runtime_registry=workspace/"registry-runtime-contract.json"
    rr=load(registry);rr["adapters"][adapter]["executable"]=str(executable);save(runtime_registry,rr)

    results=[]
    for idx in range(3):
        p=subprocess.run([str(executable)],input=fixture.read_text(encoding="utf-8"),
                         text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        if p.returncode!=0:
            raise SystemExit("GENERATED_ADAPTER_RUNTIME_FAILED:"+p.stderr[-2000:])
        result_path=workspace/f"task-result-{idx+1}.json"
        result_path.write_text(p.stdout,encoding="utf-8")
        rv=load(result_path)
        if rv.get("status")!="OK" or rv.get("producer")!=adapter:
            raise SystemExit("GENERATED_ADAPTER_RESULT_INVALID")
        results.append(result_path)

    runtime_report=workspace/"contract-runtime.json"
    run([py,bin_dir/"adapter-contract-harness.py","--registry",runtime_registry,
         "--policy",cfg/"adapter-contract.v1.json","--report",runtime_report,
         "--adapter",adapter,"--fixture",fixture,"--runtime"])

    base_ev=workspace/"base-evidence.json"
    run([py,bin_dir/"adapter-certification.py","--adapter",adapter,
         "--contract-report",runtime_report,"--fixture",fixture,
         "--task-result",results[0],"--output",base_ev])
    pilot_ev=workspace/"pilot-evidence.json"
    run([py,bin_dir/"adapter-provisioning-evidence.py","--adapter",adapter,
         "--base-evidence",base_ev,"--receipt",provision_receipt,"--output",pilot_ev])
    pilot_receipt=workspace/"pilot-receipt.json"
    run([py,bin_dir/"adapter-promotion.py","--registry",registry,
         "--contract",cfg/"adapter-contract.v1.json","--policy",cfg/"adapter-promotion.v1.json",
         "--evidence",pilot_ev,"--json","apply","--adapter",adapter,"--target","PILOT",
         "--executable",executable,"--actor","capability-build-loop",
         "--receipt",pilot_receipt,"--apply"],stdout_path=workspace/"pilot-report.json")

    health={
      "schema":"chacha.dev/provider-health-snapshot/v1",
      "providers":{provider:{"state":"HEALTHY","checked_at":now_iso(),"source":"v641-sandbox"}}
    }
    health_path=workspace/"health.json";save(health_path,health)
    enable_ev=workspace/"enablement-evidence.json"
    cmd=[py,bin_dir/"adapter-enablement-evidence.py","--policy",cfg/"adapter-enablement.v1.json",
         "--adapter",adapter,"--provider",provider,"--health",health_path,
         "--rollbacks",m["rollback"],"--output",enable_ev]
    for result in results:
        cmd.extend(["--result",result])
    run(cmd)
    enabled_receipt=workspace/"enabled-receipt.json"
    run([py,bin_dir/"adapter-promotion.py","--registry",registry,
         "--contract",cfg/"adapter-contract.v1.json","--policy",cfg/"adapter-promotion.v1.json",
         "--evidence",enable_ev,"--json","apply","--adapter",adapter,"--target","ENABLED",
         "--actor","capability-build-loop","--receipt",enabled_receipt,"--apply"],
        stdout_path=workspace/"enabled-report.json")

    final_reg=load(registry)
    final_adapter=final_reg["adapters"][adapter]
    if final_adapter.get("status")!="ENABLED":
        raise SystemExit("SANDBOX_ENABLEMENT_NOT_REACHED")
    overlay_value={
      "schema":"chacha.dev/capability-overlay/v1",
      "capabilities":{
        capability:{
          "class":"execution",
          "providers":[{
            "id":provider,"status":str(policy.get("capability_provider_status_for_same_project_resume") or "PILOT"),
            "health":"runtime-check","cost_class":"included",
            "scope":"project-local-built-adapter","fallback":[]
          }],
          "generated_by":"capability-build-loop",
          "selected_adapter":adapter,
          "promotion_state":"PROJECT_LOCAL_BUILT_PILOT",
          "automatic_external_spend_eur":0
        }
      }
    }
    save(overlay,overlay_value)

    result={
      "schema":RESULT_SCHEMA,"status":"PASS",
      "project_id":req.get("project_id"),
      "capability":capability,"provider":provider,"adapter":adapter,
      "profile":req.get("profile"),
      "generated_source":str(source),
      "generated_source_digest":digest_file(source),
      "sandbox_executable":str(executable),
      "sandbox_executable_digest":pr.get("executable_digest"),
      "adapter_status":"ENABLED",
      "same_project_resume_allowed":True,
      "durable_adoption":"PENDING_PROJECT_SUCCESS",
      "production_capable":False,
      "network_access":False,
      "credentials_required":False,
      "automatic_external_spend_eur":0,
      "artifacts":{
        "registry":str(registry),"fixture":str(fixture),
        "contract_report":str(runtime_report),
        "provisioning_receipt":str(provision_receipt),
        "pilot_receipt":str(pilot_receipt),
        "enabled_receipt":str(enabled_receipt),
        "enablement_evidence":str(enable_ev),
        "capability_overlay":str(overlay)
      },
      "observed_at":now_iso()
    }
    save(output,result)
    return result

def materialization_gate(repo_root:Path,workspace:Path,dynamic_registry:Path,mode:str,
                         manifest:dict[str,Any]|None=None,component_id:str|None=None)->dict[str,Any]:
    gate=repo_root/"dev-hub/bin/universal-materialization-gate.py"
    policy=repo_root/"dev-hub/config/canonical-component-registry.v1.json"
    out=workspace/("materialization-"+mode+".json")
    cmd=[sys.executable,gate,"--mode",mode,"--policy",policy,"--dynamic-registry",dynamic_registry,"--output",out]
    if manifest is not None:
        mp=workspace/"materialization-manifest.json";save(mp,manifest);cmd.extend(["--manifest",mp])
    if component_id:cmd.extend(["--component-id",component_id])
    run(cmd)
    receipt=load(out)
    if receipt.get("status")!="PASS":raise SystemExit("UNIVERSAL_MATERIALIZATION_GATE_NOT_PASS")
    return receipt

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--request",type=Path,required=True)
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--base-registry",type=Path,required=True)
    ap.add_argument("--workspace",type=Path,required=True)
    ap.add_argument("--dynamic-registry",type=Path,default=Path("/opt/chacha-dev/runtime/canonical-registry/dynamic-components.json"))
    sub=ap.add_subparsers(dest="command",required=True)
    sub.add_parser("plan")
    build=sub.add_parser("build-pilot")
    build.add_argument("--runtime-root",type=Path,required=True)
    build.add_argument("--output",type=Path,required=True)
    build.add_argument("--overlay",type=Path,required=True)
    build.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    policy=load(a.policy);req=load(a.request)
    v=validate_request(req,policy)

    if a.command=="plan":
        out={
          "schema":"chacha.dev/capability-build-plan/v1",
          "status":"READY" if v["eligible"] else "BUILD_SPECIALIST_REQUIRED",
          "eligible":v["eligible"],"blockers":v["blockers"],
          "capability":v["capability"],"provider":v["provider_id"],"adapter":v["adapter_id"],
          "profile":v["profile_id"],"automatic_external_spend_eur":v["automatic_external_spend_eur"]
        }
        print(json.dumps(out,indent=2,ensure_ascii=False))
        return 0 if v["eligible"] else 2

    if not a.apply:
        print("EXPLICIT_APPLY_FLAG_REQUIRED")
        return 2
    workspace=a.workspace.resolve();workspace.mkdir(parents=True,exist_ok=True)
    materialization_manifest={
      "schema":"chacha.dev/component-materialization-manifest/v1",
      "component_id":str(v["adapter_id"]),"purpose":"Capability Foundry generated adapter for "+str(v["capability"]),
      "governance_class":"CONNECTOR_ADAPTER","owner_foundry":"capability-foundry",
      "scope":"PROJECT","project_id":str(req.get("project_id") or "unknown"),
      "permissions":["read"],"budget_policy":"ZERO_INCREMENTAL_COST_DEFAULT",
      "health_contract":"ADAPTER_HEALTH_PROBE","observability":"CANONICAL_REGISTRY_AND_ADAPTER_TELEMETRY",
      "lifecycle":"MATERIALIZING","termination_policy":"RETIRE_VIA_INTENDANT",
      "retention_policy":"ADAPTER_CLASS_DEFAULT_RETENTION","purge_policy":"UNIVERSAL_HYGIENE",
      "rollback_policy":"ROLLBACK_REQUIRED","compatibility":"ADAPTER_CONTRACT_AND_PILOT_REQUIRED",
      "materialization_gate_required":True,
      "birth_contract":{"schema":"chacha.dev/component-birth-contract/v1","status":"PENDING_CANONICAL_REGISTRATION",
                        "owner_foundry":"capability-foundry","automatic_external_spend_eur":0},
      "automatic_external_spend_eur":0
    }
    gate=materialization_gate(a.repo_root.resolve(),workspace,a.dynamic_registry.resolve(),"register",materialization_manifest)
    cid=str(gate.get("component_id") or "")
    try:
        result=build_pilot(req,policy,a.repo_root.resolve(),workspace,
                           a.runtime_root.resolve(),a.base_registry.resolve(),
                           a.output.resolve(),a.overlay.resolve())
    except BaseException:
        if cid:materialization_gate(a.repo_root.resolve(),workspace,a.dynamic_registry.resolve(),"retire",component_id=cid)
        raise
    materialization_gate(a.repo_root.resolve(),workspace,a.dynamic_registry.resolve(),"activate",component_id=cid)
    print("CHACHA_DEV_V641_SAFE_ADAPTER_BUILD=PASS")
    print("CHACHA_DEV_V641_CONTRACT_OK=PASS")
    print("CHACHA_DEV_V641_SANDBOX_PILOT=PASS")
    print("CHACHA_DEV_V641_REPEATABLE_RUNS=3")
    print("CHACHA_DEV_V641_SANDBOX_ENABLED=PASS")
    print("CHACHA_DEV_V641_SAME_PROJECT_RESUME_ALLOWED=YES")
    print("CHACHA_DEV_V641_DURABLE_ADOPTION=PENDING_PROJECT_SUCCESS")
    print("CHACHA_DEV_V641_NETWORK_ACCESS=NO")
    print("CHACHA_DEV_V641_CREDENTIALS_REQUIRED=NO")
    print("CHACHA_DEV_V641_PRODUCTION_CAPABLE=NO")
    print("CHACHA_DEV_V641_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
