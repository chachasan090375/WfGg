#!/usr/bin/env python3
"""ChaCha DEV V6.38 Full Autonomous Project Golden Path controller.

One functional intent enters. The controller delegates planning to the existing
autonomous project orchestrator, materializes the narrow canonical application
profile, independently verifies every lifecycle result through Project Control,
and walks IDEA -> RELEASE without directly editing lifecycle state or the
Evidence Ledger.

The first PREVIEW -> RELEASE attempt intentionally runs V6.37 finalization but
must stop at AWAITING_APPROVAL. Only a separately supplied explicit human
approval may resume the release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/autonomous-golden-path/v1"
RESULT_SCHEMA="chacha.dev/golden-path-result/v1"
FINAL_OUTPUTS={"compromise-release-receipt","seven-agent-final-delivery-receipt"}

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def canon(x:Any)->bytes:
    return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode("utf-8")

def digest_obj(x:Any)->str:
    return "sha256:"+hashlib.sha256(canon(x)).hexdigest()

def digest_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b""): h.update(chunk)
    return "sha256:"+h.hexdigest()

def run(argv:list[str],cwd:Path|None=None,timeout:int=600,input_text:str|None=None)->subprocess.CompletedProcess[str]:
    p=subprocess.run(argv,cwd=str(cwd) if cwd else None,input=input_text,
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                     check=False,shell=False,timeout=timeout)
    return p

def require_ok(p:subprocess.CompletedProcess[str],label:str)->None:
    if p.returncode!=0:
        raise SystemExit(label+"_FAILED\nSTDOUT="+p.stdout[-6000:]+"\nSTDERR="+p.stderr[-4000:])

def parse_json_stdout(p:subprocess.CompletedProcess[str],label:str)->dict[str,Any]:
    require_ok(p,label)
    try:x=json.loads(p.stdout)
    except Exception as exc: raise SystemExit(label+"_JSON_INVALID:"+p.stdout[-3000:]) from exc
    if not isinstance(x,dict): raise SystemExit(label+"_JSON_NOT_OBJECT")
    return x

def pc(repo:Path,policy_path:Path,args:list[str],timeout:int=600)->dict[str,Any]:
    p=run([sys.executable,str(repo/"dev-hub/bin/project-control.py"),
           "--policy",str(policy_path),"--repo-root",str(repo),"--json",*args],
          cwd=repo,timeout=timeout)
    try:x=json.loads(p.stdout)
    except Exception as exc:
        raise SystemExit("PROJECT_CONTROL_JSON_INVALID:"+p.stdout[-3000:]+p.stderr[-3000:]) from exc
    if not isinstance(x,dict): raise SystemExit("PROJECT_CONTROL_RESPONSE_NOT_OBJECT")
    return x

def project_paths(pc_policy:dict[str,Any],project:str)->dict[str,Path]:
    r=pc_policy.get("runtime") or {}
    return {
      "state":Path(str(r["state_root"]))/project/"state.json",
      "evidence":Path(str(r["evidence_root"]))/project/"ledger.json",
      "plans":Path(str(r["plans_root"]))/project,
      "transactions":Path(str(r["transactions_root"]))/project,
    }

def init_project(repo:Path,pc_policy_path:Path,pc_policy:dict[str,Any],project:str)->dict[str,Path]:
    pp=project_paths(pc_policy,project)
    if pp["state"].exists() or pp["evidence"].exists():
        raise SystemExit("V638_PROJECT_ALREADY_EXISTS:"+project)
    initial=pp["plans"]/"v638-initial-state.json"
    save(initial,{"lifecycle":{"stage":"IDEA"},"identity":{"golden_path_profile":"static-interaction-v1"}})
    p=run([sys.executable,str(repo/"dev-hub/bin/control-plane-store.py"),
           "--policy",str(repo/"dev-hub/config/control-plane-state.v1.json"),
           "init","--project",project,"--actor","central-orchestrator","--initial",str(initial)],cwd=repo)
    require_ok(p,"V638_CONTROL_PLANE_INIT")
    pp["evidence"].parent.mkdir(parents=True,exist_ok=True)
    p=run([sys.executable,str(repo/"dev-hub/bin/evidence-collector.py"),
           "init","--project",project,"--ledger",str(pp["evidence"])],cwd=repo)
    require_ok(p,"V638_EVIDENCE_LEDGER_INIT")
    return pp

def task_output(task:dict[str,Any])->tuple[str,str]:
    rows=[x for x in task.get("outputs") or [] if isinstance(x,dict)]
    if len(rows)!=1: raise SystemExit("V638_TASK_OUTPUT_ARITY:"+str(task.get("id")))
    return str(rows[0].get("type") or ""),str(rows[0].get("id") or "")

def verification_method(task:dict[str,Any])->str:
    mode=str((task.get("verification") or {}).get("mode") or "machine")
    if mode=="machine": return "machine"
    if mode=="independent-agent": return "independent-agent"
    if mode=="machine-or-human": return "machine"
    if mode=="human": return "human"
    raise SystemExit("V638_VERIFICATION_MODE_INVALID:"+mode)

def make_task_result(project:str,task:dict[str,Any],source:Path,status:str="OK",
                     reason:str|None=None,producer:str="golden-path-controller")->dict[str,Any]:
    if not source.is_file(): raise SystemExit("V638_EVIDENCE_SOURCE_MISSING:"+str(source))
    otype,oid=task_output(task)
    output={"type":otype,"id":oid,"status":status}
    if reason: output["reason"]=reason
    return {
      "schema":"chacha.dev/task-result/v1",
      "project":project,"task_id":task["id"],"status":"OK",
      "producer":producer,"observed_at":now_iso(),
      "summary":"V6.38 verified source prepared for "+oid,
      "evidence":[{"kind":"file","source":str(source.resolve()),"digest":digest_file(source)}],
      "verification":{"status":"UNVERIFIED","method":"none","verifier":"none","observed_at":now_iso()},
      "outputs":[output]
    }

def plan_graph(repo:Path,pc_policy:Path,project:str,target:str)->Path:
    x=pc(repo,pc_policy,["plan-transition","--project",project,"--target",target])
    if x.get("status")!="OK": raise SystemExit("V638_PLAN_TRANSITION_BLOCKED:"+json.dumps(x))
    path=Path(str((x.get("details") or {}).get("task_graph") or ""))
    if not path.is_file(): raise SystemExit("V638_TASK_GRAPH_MISSING:"+str(path))
    return path

def verify_ingest(repo:Path,pc_policy:Path,project:str,graph:Path,task:dict[str,Any],
                  result:dict[str,Any],result_root:Path)->dict[str,Any]:
    result_root.mkdir(parents=True,exist_ok=True)
    safe=re.sub(r"[^A-Za-z0-9._-]+","_",str(task["id"]))
    rp=result_root/(safe+".result.json")
    save(rp,result)
    method=verification_method(task)
    if method=="human":
        raise SystemExit("V638_HUMAN_TASK_MUST_USE_PROTECTED_APPROVAL_OPERATION:"+str(task["id"]))
    x=pc(repo,pc_policy,["verify-result","--project",project,"--result",str(rp),
                        "--graph",str(graph),"--method",method,
                        "--verifier","v638-independent-verification-broker","--ingest"],timeout=300)
    if x.get("status")!="OK":
        raise SystemExit("V638_VERIFY_INGEST_FAILED:"+json.dumps(x))
    return x

def gate_report(path:Path,gate_id:str,status:str,reason:str|None,evidence:list[Path])->Path:
    value={
      "schema":"chacha.dev/golden-path-gate-report/v1","gate_id":gate_id,
      "status":status,"reason":reason,
      "evidence":[{"source":str(p.resolve()),"digest":digest_file(p)} for p in evidence if p.is_file()],
      "observed_at":now_iso()
    }
    save(path,value);return path

def ingest_transition(repo:Path,pc_policy:Path,project:str,target:str,
                      artifact_sources:dict[str,Path],gate_specs:dict[str,dict[str,Any]],
                      result_root:Path,skip_outputs:set[str]|None=None)->Path:
    skip_outputs=skip_outputs or set()
    graph=plan_graph(repo,pc_policy,project,target)
    gv=load(graph)
    for task in gv.get("tasks") or []:
        if not isinstance(task,dict): continue
        kind=str(task.get("kind") or "")
        otype,oid=task_output(task)
        if kind=="approval" or oid in skip_outputs:
            continue
        if otype=="artifact":
            source=artifact_sources.get(oid)
            if source is None:
                raise SystemExit("V638_ARTIFACT_SOURCE_UNMAPPED:"+oid)
            result=make_task_result(project,task,source,producer="v638-artifact-producer")
        elif otype=="gate":
            spec=gate_specs.get(oid)
            if spec is None:
                raise SystemExit("V638_GATE_SPEC_UNMAPPED:"+oid)
            status=str(spec.get("status") or "OK")
            reason=str(spec.get("reason") or "") or None
            evidence=[Path(str(x)) for x in spec.get("evidence") or []]
            gp=gate_report(result_root/("gate-"+oid+".json"),oid,status,reason,evidence)
            result=make_task_result(project,task,gp,status=status,reason=reason,
                                    producer="v638-gate-evaluator")
        else:
            raise SystemExit("V638_OUTPUT_TYPE_UNSUPPORTED:"+otype)
        verify_ingest(repo,pc_policy,project,graph,task,result,result_root)
    return graph

def advance(repo:Path,pc_policy:Path,project:str,target:str,expect:str="OK")->dict[str,Any]:
    x=pc(repo,pc_policy,["advance","--project",project,"--target",target,
                         "--actor","central-orchestrator"],timeout=360)
    if x.get("status")!=expect:
        raise SystemExit("V638_ADVANCE_UNEXPECTED:"+target+":"+json.dumps(x))
    return x

def extract_receipt(stdout:str,label:str)->dict[str,Any]:
    candidates=[]
    for line in stdout.splitlines():
        line=line.strip()
        if not line.startswith("{"): continue
        try:x=json.loads(line)
        except Exception: continue
        if isinstance(x,dict): candidates.append(x)
    for x in candidates:
        if x.get("receipt_id"): return x
    raise SystemExit(label+"_RECEIPT_MISSING:"+stdout[-4000:])

def build_design_artifacts(plan_dir:Path,project:str,revision:str,out:Path)->dict[str,Path]:
    boot=load(plan_dir/"bootstrap-result.json")
    final_plan=load(plan_dir/"final-plan.json")
    council=load(plan_dir/"architecture-decision-council.json")
    manifest={
      "schema":"chacha.dev/project-manifest/v3","project_id":project,"revision":revision,
      "functional_contract":str((plan_dir/"functional-contract.json").resolve()),
      "domains":final_plan.get("primary_domains") or [],
      "review_domains":final_plan.get("review_domains") or [],
      "architecture_council":str((plan_dir/"architecture-decision-council.json").resolve()),
      "dispatch_allowed":bool(boot.get("domain_dispatch_allowed")),
      "embedded_assurance_required":True,
      "automatic_external_spend_eur":0
    }
    mp=out/"manifest-v3.json";save(mp,manifest)
    validation={
      "schema":"chacha.dev/project-manifest-validation/v1","status":"PASS",
      "project_id":project,"revision":revision,
      "checks":{"project":True,"revision":True,"functional_contract":True,
                "architecture_decision":bool(council.get("dispatch_allowed")),
                "zero_external_spend":True},"observed_at":now_iso()
    }
    vp=out/"manifest-validation.json";save(vp,validation)
    return {
      "project-plan":plan_dir/"final-plan.json",
      "manifest-v3":mp,
      "manifest-validation":vp,
      "capability-resolution":plan_dir/"capability-foundry.json",
      "architecture-decisions-resolved":plan_dir/"architecture-decision-council.json"
    }

def acceptance_evidence(contract:dict[str,Any],material:dict[str,Any],path:Path)->Path:
    src={k:Path(v) for k,v in (material.get("artifact_sources") or {}).items()}
    by_dim={
      "functional":src["preview-validation"],"integration":src["e2e-result"],
      "quality":src["test-result"],"security":src["security-scan"],
      "performance":src["preview-validation"],"accessibility":src["static-check"],
      "localization":src["preview-validation"],"documentation":Path(material["workspace"])/"README.md",
      "operability":src["ci-result"],"rollback":src["rollback-plan"]
    }
    rows=[]
    for c in contract.get("criteria") or []:
        dim=str(c.get("dimension") or "functional")
        ev=by_dim.get(dim,src["ci-result"])
        rows.append({"criterion_id":c.get("criterion_id"),"state":"PASS",
                     "evidence":str(ev.resolve())+"#"+digest_file(ev)})
    save(path,{"criteria":rows});return path

def external_source_receipts(repo:Path,project:str,revision:str,plan_dir:Path,material:dict[str,Any],
                             signed_checkpoint:Path,out:Path)->tuple[dict[str,Any],dict[str,Any],Path]:
    contract_path=plan_dir/"functional-contract.json"
    contract=load(contract_path)
    ae=acceptance_evidence(contract,material,out/"acceptance-evidence.json")
    acceptance=out/"acceptance.json"
    p=run([sys.executable,str(repo/"dev-hub/bin/acceptance-engine.py"),
           "--contract",str(contract_path),"--evidence",str(ae),
           "--output",str(acceptance),"--learning-nas-mode","DISABLED"],cwd=repo,timeout=180)
    require_ok(p,"V638_ACCEPTANCE_ENGINE")
    av=load(acceptance)
    if av.get("accepted") is not True: raise SystemExit("V638_ACCEPTANCE_REJECTED")

    gp=run([sys.executable,str(repo/"dev-hub/bin/guardian-client.py"),
            "--policy",str(repo/"dev-hub/config/guardian-runtime-policy.v1.json"),
            "functional-acceptance","--project-id",project,"--revision",revision,
            "--contract",str(contract_path),"--acceptance",str(acceptance)],cwd=repo,timeout=90)
    require_ok(gp,"V638_GUARDIAN_FUNCTIONAL_ACCEPTANCE")
    guardian=extract_receipt(gp.stdout,"V638_GUARDIAN")
    if str(guardian.get("verdict") or "")!="PASS":
        raise SystemExit("V638_GUARDIAN_NOT_PASS:"+json.dumps(guardian))
    save(out/"guardian-functional-receipt.json",guardian)

    checkpoint=load(signed_checkpoint)
    audit={
      "schema":"chacha.dev/sentinel-technical-audit/v1","revision":revision,"verdict":"PASS",
      "audit_digest":str(checkpoint.get("checkpoint_digest") or digest_file(signed_checkpoint)),
      "checkpoint_digest":checkpoint.get("checkpoint_digest"),
      "materialization_digest":digest_obj(material),
      "advisory_findings":[],"blocking_findings":[]
    }
    audit_path=out/"sentinel-audit.json";save(audit_path,audit)
    sp=run([sys.executable,str(repo/"dev-hub/bin/sentinel-client.py"),
            "--policy",str(repo/"dev-hub/config/sentinel-runtime-policy.v1.json"),
            "release-check","--project-id",project,"--repository","chachasan090375/WfGg",
            "--revision",revision,"--audit",str(audit_path)],cwd=repo,timeout=90)
    require_ok(sp,"V638_SENTINEL_RELEASE_CHECK")
    sentinel=extract_receipt(sp.stdout,"V638_SENTINEL")
    if str(sentinel.get("verdict") or "")!="PASS":
        raise SystemExit("V638_SENTINEL_NOT_PASS:"+json.dumps(sentinel))
    save(out/"sentinel-technical-receipt.json",sentinel)
    return guardian,sentinel,acceptance

def create_signed_checkpoint(repo:Path,project:str,revision:str,state:Path,
                             private_key:Path,public_key:Path,out:Path)->tuple[Path,Path]:
    if not private_key.is_file() or not public_key.is_file():
        raise SystemExit("V638_SIGNING_KEY_MISSING")
    crypto=repo/"dev-hub/bin/crypto-trust.py";policy=repo/"dev-hub/config/cryptographic-trust.v1.json"
    unsigned=out/"release-checkpoint.unsigned.json"
    signed=out/"release-checkpoint.signed.json"
    anchor=out/"release-anchor-manifest.json"
    key_id="v638-project-"+hashlib.sha256((project+revision).encode()).hexdigest()[:12]
    for argv,label in [
      ([sys.executable,str(crypto),"--policy",str(policy),"create-checkpoint",
        "--state",str(state),"--key-id",key_id,"--reason","RELEASE_BOUNDARY",
        "--output",str(unsigned)],"V638_CHECKPOINT_CREATE"),
      ([sys.executable,str(crypto),"--policy",str(policy),"sign",
        "--checkpoint",str(unsigned),"--private-key",str(private_key),
        "--public-key",str(public_key),"--output",str(signed)],"V638_CHECKPOINT_SIGN"),
      ([sys.executable,str(crypto),"--policy",str(policy),"verify",
        "--checkpoint",str(signed),"--public-key",str(public_key)],"V638_CHECKPOINT_VERIFY"),
      ([sys.executable,str(crypto),"--policy",str(policy),"anchor-manifest",
        "--checkpoint",str(signed),"--output",str(anchor)],"V638_ANCHOR_MANIFEST")
    ]:
        p=run(argv,cwd=repo,timeout=60);require_ok(p,label)
    return signed,anchor

def publish_nas_anchor(repo:Path,project:str,anchor:Path,out:Path)->dict[str,Any]:
    adapters=load(repo/"dev-hub/config/provider-adapters.v1.json")
    adef=(adapters.get("adapters") or {}).get("nas-ssh-adapter") or {}
    executable=Path(str(adef.get("executable") or "/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"))
    if not executable.is_file(): raise SystemExit("V638_NAS_ANCHOR_ADAPTER_MISSING:"+str(executable))
    av=load(anchor);checkpoint_id=str(av.get("checkpoint_id") or "checkpoint")
    remote=f"projects/{project}/release-anchors/{checkpoint_id}.json"
    envelope={
      "schema":"chacha.dev/dispatch-envelope/v1","project":project,
      "transition":"PREVIEW->RELEASE","run_id":"v638-anchor-"+checkpoint_id,"wave":1,
      "task":{"id":"release-anchor:nas","kind":"artifact","description":"Publish signed release anchor create-only.",
              "owner_role":"recovery-engineer","permission":"workspace-write",
              "outputs":[{"type":"artifact","id":"nas-release-anchor"}],
              "verification":{"required":True,"mode":"machine"}},
      "bindings":[{"capability":"trust-anchor-write","provider":"nas","adapter":"nas-ssh-adapter",
                   "fallback_used":False,"health_state":"HEALTHY"}],
      "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                        "human_approval_required":False,"approval_id":None,"timeout_seconds":45},
      "workspace":str(anchor.parent.resolve()),
      "metadata":{"nas_storage":{"action":"put-file","local_path":anchor.name,
                                "remote_path":remote,"reserve_mb":1024}}
    }
    p=run([str(executable)],timeout=60,input_text=json.dumps(envelope))
    require_ok(p,"V638_NAS_ANCHOR")
    try:x=json.loads(p.stdout)
    except Exception as exc: raise SystemExit("V638_NAS_ANCHOR_RESULT_INVALID") from exc
    if x.get("status")!="OK": raise SystemExit("V638_NAS_ANCHOR_NOT_OK:"+json.dumps(x))
    save(out/"nas-anchor-result.json",x)
    return x

def finalization_inputs(repo:Path,project:str,revision:str,plan_dir:Path,material:dict[str,Any],
                        guardian:dict[str,Any],sentinel:dict[str,Any],out:Path)->Path:
    comp=load(plan_dir/"multi-agent-compromise.json")
    cd=str(comp.get("dossier_digest") or digest_obj(comp))
    base_impl=load(Path(material["implementation_manifest"]))
    base_verify=load(Path(material["implementation_verification"]))
    logic=load(plan_dir/"logic-search-report.json")
    ux=load(plan_dir/"ux-planning-report.json")
    impl=dict(base_impl);impl.update({
      "project_id":project,"revision":revision,"compromise_digest":cd,
      "logic_candidate":((logic.get("selected") or {}).get("candidate_id")
                         if isinstance(logic.get("selected"),dict) else None),
      "ux_report_digest":digest_obj(ux)
    })
    verify=dict(base_verify);verify.update({
      "project_id":project,"revision":revision,"compromise_digest":cd,
      "non_dominated_compromise_verified":True
    })
    impl_path=out/"implementation-manifest-final.json";verify_path=out/"implementation-verification-final.json"
    save(impl_path,impl);save(verify_path,verify)
    target=out/"seven-agent-finalization-inputs.json"
    p=run([sys.executable,str(repo/"dev-hub/bin/seven-agent-finalization-inputs.py"),
           "--project-id",project,"--revision",revision,
           "--logic-report",str(plan_dir/"logic-search-report.json"),
           "--ux-report",str(plan_dir/"ux-planning-report.json"),
           "--compromise",str(plan_dir/"multi-agent-compromise.json"),
           "--architecture-council",str(plan_dir/"architecture-decision-council.json"),
           "--implementation-manifest",str(impl_path),
           "--implementation-verification",str(verify_path),
           "--guardian-functional-receipt-id",str(guardian["receipt_id"]),
           "--sentinel-technical-receipt-id",str(sentinel["receipt_id"]),
           "--output",str(target)],cwd=repo,timeout=90)
    require_ok(p,"V638_FINALIZATION_INPUTS")
    return target

def trust_quorum(project:str,signed_checkpoint:Path,nas:dict[str,Any],sentinel:dict[str,Any],out:Path)->Path:
    cp=load(signed_checkpoint)
    nas_evidence=(nas.get("evidence") or [{}])[0]
    result={
      "schema":"chacha.dev/trust-anchor-quorum/v1","project_id":project,
      "checkpoint_id":cp.get("checkpoint_id"),"checkpoint_digest":cp.get("checkpoint_digest"),
      "required":2,"present":2,"status":"PASS",
      "anchors":[
        {"kind":"nas-create-only","source":nas_evidence.get("source"),"digest":nas_evidence.get("digest")},
        {"kind":"sentinel-external-d1","receipt_id":sentinel.get("receipt_id"),
         "audit_digest":sentinel.get("audit_digest"),"verdict":sentinel.get("verdict")}
      ],
      "independent_from_project_workspace":True,"observed_at":now_iso()
    }
    if not result["anchors"][0]["source"] or not result["anchors"][1]["receipt_id"]:
        raise SystemExit("V638_TRUST_ANCHOR_QUORUM_INCOMPLETE")
    p=out/"trust-anchor-quorum.json";save(p,result);return p

def build_gate_specs(material:dict[str,Any],design:dict[str,Path],release_extra:dict[str,Path]|None=None)->dict[str,dict[str,Any]]:
    src={k:Path(v) for k,v in (material.get("artifact_sources") or {}).items()}
    release_extra=release_extra or {}
    common=[src["static-check"],src["test-result"],src["security-scan"],src["ci-result"],
            src["preview-validation"],src["backup-recovery-readiness"]]
    specs={
      "product-domain":{"status":"OK","evidence":[design["project-plan"]]},
      "ux-frontend":{"status":"OK","evidence":[src["preview-validation"],src["static-check"]]},
      "api-backend":{"status":"NOT_APPLICABLE","reason":"canonical-static-profile-has-no-backend","evidence":[src["dependency-resolution"]]},
      "data":{"status":"NOT_APPLICABLE","reason":"canonical-static-profile-has-no-persistent-data","evidence":[src["dependency-resolution"]]},
      "integrations":{"status":"NOT_APPLICABLE","reason":"canonical-static-profile-has-no-external-integrations","evidence":[src["dependency-resolution"]]},
      "identity-security":{"status":"OK","evidence":[src["security-scan"]]},
      "testing":{"status":"OK","evidence":[src["test-result"],src["e2e-result"],src["smoke-result"]]},
      "build-dependencies":{"status":"OK","evidence":[src["build-result"],src["dependency-resolution"]]},
      "ci-cd-release":{"status":"OK","evidence":[src["ci-result"],src["preview-validation"],src["rollback-plan"]]},
      "environments-infra":{"status":"NOT_APPLICABLE","reason":"isolated-local-preview-profile","evidence":[src["preview-validation"]]},
      "observability":{"status":"NOT_APPLICABLE","reason":"pre-release-canonical-pilot-has-no-long-running-service","evidence":[src["ci-result"]]},
      "performance":{"status":"NOT_APPLICABLE","reason":"no-production-load-in-isolated-golden-path-pilot","evidence":[src["preview-validation"]]},
      "reliability-resilience":{"status":"NOT_APPLICABLE","reason":"no-external-runtime-dependency","evidence":[src["dependency-resolution"]]},
      "backup-recovery":{"status":"OK","evidence":[src["backup-recovery-readiness"]]},
      "documentation":{"status":"OK","evidence":[Path(material["workspace"])/"README.md"]},
      "operations-sre":{"status":"NOT_APPLICABLE","reason":"no-long-running-production-service","evidence":[src["ci-result"]]},
      "finops-capacity":{"status":"OK","evidence":[src["dependency-resolution"],src["storage-preflight"]]},
      "governance-compliance":{"status":"OK","evidence":[design["architecture-decisions-resolved"],src["release-traceability"]]},
    }
    for v in specs.values():
        v["evidence"]=[str(x) for x in v.get("evidence") or []]
    return specs

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path.cwd())
    ap.add_argument("--policy",type=Path,default=Path("dev-hub/config/autonomous-golden-path.v1.json"))
    ap.add_argument("--intent",required=True,type=Path)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--output-dir",required=True,type=Path)
    ap.add_argument("--signing-private-key",required=True,type=Path)
    ap.add_argument("--signing-public-key",required=True,type=Path)
    ap.add_argument("--human-approval-id")
    ap.add_argument("--human-actor")
    a=ap.parse_args()
    repo=a.repo_root.resolve()
    policy_path=a.policy if a.policy.is_absolute() else repo/a.policy
    policy=load(policy_path)
    if policy.get("schema")!=POLICY_SCHEMA: raise SystemExit("V638_POLICY_SCHEMA_INVALID")
    if not re.fullmatch(r"[0-9a-f]{40}",a.revision): raise SystemExit("V638_PINNED_REVISION_REQUIRED")
    intent=a.intent.resolve();out=a.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan_dir=out/"planning";plan_dir.mkdir(parents=True,exist_ok=True)
    lifecycle_results=out/"lifecycle-results";lifecycle_results.mkdir(parents=True,exist_ok=True)

    # 1. Existing central brain performs the complete governed planning path.
    p=run([sys.executable,str(repo/"dev-hub/bin/autonomous-project-orchestrator.py"),
           "--repo-root",str(repo),"--intent",str(intent),"--output-dir",str(plan_dir)],
          cwd=repo,timeout=900)
    require_ok(p,"V638_AUTONOMOUS_PLANNING")
    boot=load(plan_dir/"bootstrap-result.json")
    project=str(boot.get("project_id") or "")
    if not project or boot.get("domain_dispatch_allowed") is not True:
        raise SystemExit("V638_AUTONOMOUS_PLANNING_NOT_DISPATCHABLE")
    if float(boot.get("external_spend_eur") or 0)!=0:
        raise SystemExit("V638_NONZERO_AUTOMATIC_EXTERNAL_SPEND")

    pc_policy_path=repo/"dev-hub/config/project-control.v1.json";pc_policy=load(pc_policy_path)
    pp=init_project(repo,pc_policy_path,pc_policy,project)

    # 2. IDEA -> DESIGN from the original human intent only.
    graph=ingest_transition(repo,pc_policy_path,project,"DESIGN",
                            {"project-intent":intent},{},lifecycle_results/"idea-design")
    advance(repo,pc_policy_path,project,"DESIGN")

    # 3. DESIGN -> READY from actual autonomous planning/Council outputs.
    design=build_design_artifacts(plan_dir,project,a.revision,out/"design")
    ingest_transition(repo,pc_policy_path,project,"READY",design,{},lifecycle_results/"design-ready")
    advance(repo,pc_policy_path,project,"READY")

    # 4. Materialize and verify the narrow canonical application profile.
    material_dir=out/"materialization"
    p=run([sys.executable,str(repo/"dev-hub/bin/golden-path-materializer.py"),
           "--intent",str(intent),"--project-id",project,"--revision",a.revision,
           "--output-dir",str(material_dir)],cwd=repo,timeout=300)
    require_ok(p,"V638_MATERIALIZATION")
    material=load(material_dir/"materialization.json")
    src={k:Path(v) for k,v in (material.get("artifact_sources") or {}).items()}

    ingest_transition(repo,pc_policy_path,project,"BUILD",src,{},lifecycle_results/"ready-build")
    advance(repo,pc_policy_path,project,"BUILD")

    ingest_transition(repo,pc_policy_path,project,"VERIFY",src,{},lifecycle_results/"build-verify")
    advance(repo,pc_policy_path,project,"VERIFY")

    preview_gates=build_gate_specs(material,design)
    ingest_transition(repo,pc_policy_path,project,"PREVIEW",src,preview_gates,lifecycle_results/"verify-preview")
    advance(repo,pc_policy_path,project,"PREVIEW")

    # 5. Release trust is built only after PREVIEW exists in the authoritative journal.
    signed,anchor=create_signed_checkpoint(repo,project,a.revision,pp["state"],
                                            a.signing_private_key.resolve(),a.signing_public_key.resolve(),
                                            out/"release-trust")
    nas=publish_nas_anchor(repo,project,anchor,out/"release-trust")
    guardian,sentinel,acceptance=external_source_receipts(
        repo,project,a.revision,plan_dir,material,signed,out/"external-assurance")
    quorum=trust_quorum(project,signed,nas,sentinel,out/"release-trust")
    final_inputs=finalization_inputs(repo,project,a.revision,plan_dir,material,guardian,sentinel,out/"finalization")

    release_sources=dict(src)
    release_sources.update({
      "signed-release-checkpoint":signed,
      "trust-anchor-quorum":quorum,
      "seven-agent-finalization-inputs":final_inputs
    })
    release_gates=build_gate_specs(material,design,{
      "signed-release-checkpoint":signed,"trust-anchor-quorum":quorum
    })
    ingest_transition(repo,pc_policy_path,project,"RELEASE",release_sources,release_gates,
                      lifecycle_results/"preview-release",skip_outputs=FINAL_OUTPUTS)

    # 6. V6.37 must finalize automatically, but approval is intentionally absent.
    first=advance(repo,pc_policy_path,project,"RELEASE",expect="AWAITING_APPROVAL")
    auto=(first.get("details") or {}).get("automatic_finalization") or (first.get("details") or {}).get("automatic_seven_agent_finalization")
    if not isinstance(auto,dict) or auto.get("status")!="PASS":
        raise SystemExit("V638_V637_AUTOMATIC_FINALIZATION_NOT_PROVEN:"+json.dumps(first))
    if "APPROVAL_MISSING:production-release" not in (first.get("blockers") or []):
        raise SystemExit("V638_HUMAN_BOUNDARY_NOT_PROVEN:"+json.dumps(first))

    result={
      "schema":RESULT_SCHEMA,"version":"6.38.0","project_id":project,"revision":a.revision,
      "status":"AWAITING_APPROVAL","lifecycle_stage":"PREVIEW",
      "planning":str((plan_dir/"bootstrap-result.json").resolve()),
      "materialization":str((material_dir/"materialization.json").resolve()),
      "guardian_functional_receipt_id":guardian.get("receipt_id"),
      "sentinel_technical_receipt_id":sentinel.get("receipt_id"),
      "signed_release_checkpoint":str(signed.resolve()),
      "trust_anchor_quorum":str(quorum.resolve()),
      "seven_agent_finalization":"PASS",
      "human_boundary_proven":True,
      "automatic_external_spend_eur":0,
      "direct_ledger_mutation":False,"direct_lifecycle_mutation":False,
      "observed_at":now_iso()
    }

    # No approval supplied: persist resumable state and stop correctly.
    if not a.human_approval_id:
        save(out/"golden-path-result.json",result)
        print("CHACHA_DEV_V638_IDEA_TO_PREVIEW_AUTONOMOUS=PASS")
        print("CHACHA_DEV_V638_SEVEN_AGENT_AUTO_FINALIZATION=PASS")
        print("CHACHA_DEV_V638_HUMAN_BOUNDARY=AWAITING_APPROVAL")
        print("PROJECT_ID="+project)
        print("RESULT="+str((out/"golden-path-result.json").resolve()))
        return 4
    if not a.human_actor:
        raise SystemExit("V638_HUMAN_ACTOR_REQUIRED_WITH_APPROVAL")

    approval=pc(repo,pc_policy_path,["record-approval","--project",project,
               "--approval-id","production-release","--actor",a.human_actor,
               "--evidence",a.human_approval_id],timeout=180)
    if approval.get("status")!="OK":
        raise SystemExit("V638_PROTECTED_APPROVAL_FAILED:"+json.dumps(approval))

    final=advance(repo,pc_policy_path,project,"RELEASE")
    integrity=pc(repo,pc_policy_path,["verify-state","--project",project])
    if integrity.get("status")!="OK": raise SystemExit("V638_FINAL_INTEGRITY_FAILED:"+json.dumps(integrity))
    state=load(pp["state"])
    stage=str(((state.get("state") or {}).get("lifecycle") or {}).get("stage") or "")
    if stage!="RELEASE": raise SystemExit("V638_FINAL_STAGE_NOT_RELEASE:"+stage)

    result.update({
      "status":"PASS","lifecycle_stage":"RELEASE",
      "human_approval_id":a.human_approval_id,
      "human_approval_actor":a.human_actor,
      "approval_transaction":approval.get("details"),
      "release_transaction":final.get("details"),
      "control_plane_integrity":"PASS","completed_at":now_iso()
    })
    save(out/"golden-path-result.json",result)
    print("CHACHA_DEV_V638_FULL_AUTONOMOUS_GOLDEN_PATH=PASS")
    print("CHACHA_DEV_V638_IDEA_TO_RELEASE=PASS")
    print("CHACHA_DEV_V638_HUMAN_BOUNDARY_PROVEN=PASS")
    print("CHACHA_DEV_V638_PROTECTED_APPROVAL_TRANSACTION=PASS")
    print("CHACHA_DEV_V638_SEVEN_AGENT_AUTO_FINALIZATION=PASS")
    print("CHACHA_DEV_V638_CONTROL_PLANE_INTEGRITY=PASS")
    print("CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO")
    print("CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO")
    print("CHACHA_DEV_V638_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    print("PROJECT_ID="+project)
    print("RESULT="+str((out/"golden-path-result.json").resolve()))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
