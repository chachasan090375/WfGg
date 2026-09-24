#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/platform-component-apply-adapter-binding-gate/v1"
REV_RE=re.compile(r"^[0-9a-f]{40}$")
DEDICATED_WORKFLOW="ChaCha DEV Branch Foundry source integrator qualification"
UNIVERSAL_WORKFLOW="ChaCha DEV universal evolution coverage sync qualification"
SENTINEL_WORKFLOW="ChaCha DEV Sentinel technical assurance"
TRUSTED_EXECUTABLE="/opt/chacha-dev/adapters/platform-component/branch-foundry-source-integrator/current/branch-foundry-source-integrator"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def file_digest(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return "sha256:"+h.hexdigest()

def github_runs(repository:str,revision:str)->dict[str,Any]:
    q=urllib.parse.urlencode({"head_sha":revision,"per_page":100})
    req=urllib.request.Request(
      "https://api.github.com/repos/"+repository+"/actions/runs?"+q,
      headers={"User-Agent":"ChaCha-DEV-Adapter-Binding-Gate/1.0","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req,timeout=20) as r:
        x=json.loads(r.read().decode("utf-8"))
    if not isinstance(x,dict):raise ValueError("GITHUB_RUNS_INVALID")
    return x

def workflow_success(runs:dict[str,Any],name:str,revision:str)->bool:
    return any(
      isinstance(x,dict) and x.get("name")==name and x.get("head_sha")==revision and
      x.get("status")=="completed" and x.get("conclusion")=="success"
      for x in (runs.get("workflow_runs") or [])
    )

def evaluate(gate:dict[str,Any],adapter_policy:dict[str,Any],receipt:dict[str,Any],
             registry:dict[str,Any],runs:dict[str,Any],revision:str,source_path:Path)->dict[str,Any]:
    controlled=gate.get("controlled_apply_contract") if isinstance(gate.get("controlled_apply_contract"),dict) else {}
    cid=str(controlled.get("component_id") or gate.get("component_id") or "")
    owner=str(controlled.get("candidate_owner") or "")
    candidate=str(controlled.get("candidate_revision") or "")
    incumbent=str(controlled.get("incumbent_revision") or "")
    safety=adapter_policy.get("safety") if isinstance(adapter_policy.get("safety"),dict) else {}
    qualification=adapter_policy.get("qualification") if isinstance(adapter_policy.get("qualification"),dict) else {}
    reg_principles=registry.get("principles") if isinstance(registry.get("principles"),dict) else {}
    adapters=registry.get("adapters") if isinstance(registry.get("adapters"),dict) else {}
    source_digest=file_digest(source_path) if source_path.is_file() else ""
    checks={
      "revision_exact":REV_RE.fullmatch(revision) is not None,
      "gate_schema":gate.get("schema")=="chacha.dev/platform-component-promotion-gate/v1",
      "gate_authorized":gate.get("status")=="PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY" and gate.get("promotion_authorized") is True,
      "gate_human_approval_verified":gate.get("human_approval_verified") is True,
      "controlled_contract_schema":controlled.get("schema")=="chacha.dev/platform-component-controlled-apply-contract/v1",
      "controlled_source_candidate_only":controlled.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION" and controlled.get("source_candidate_integration_authorized") is True,
      "component_present":bool(cid),
      "candidate_owner_branch_foundry":owner=="branch-foundry",
      "candidate_revision_exact":REV_RE.fullmatch(candidate) is not None,
      "incumbent_revision_exact":REV_RE.fullmatch(incumbent) is not None,
      "candidate_artifact_exact":controlled.get("candidate_artifact_ref")=="git:candidate@"+candidate,
      "incumbent_artifact_exact":controlled.get("incumbent_artifact_ref")=="git:incumbent@"+incumbent,
      "approval_id_present":bool(str(controlled.get("approval_id") or "")),
      "approval_actor_present":bool(str(controlled.get("approval_actor") or "")),
      "approval_evidence_present":bool(str(controlled.get("approval_evidence") or "")),
      "technical_review_digest_present":bool(str(controlled.get("technical_review_digest") or "")),
      "adapter_policy_schema":adapter_policy.get("schema")=="chacha.dev/platform-component-branch-foundry-source-integrator/v1",
      "adapter_status_qualified":adapter_policy.get("status")=="QUALIFIED",
      "adapter_owner_matches":adapter_policy.get("candidate_owner")==owner=="branch-foundry",
      "adapter_mode_source_only":adapter_policy.get("mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "adapter_not_live_registered":qualification.get("registered_for_live_component") is False,
      "adapter_reversible":safety.get("reversible") is True,
      "adapter_exact_revision":safety.get("exact_revision_enforced") is True,
      "adapter_runtime_mutation_forbidden":safety.get("direct_runtime_mutation") is False,
      "adapter_production_activation_forbidden":safety.get("production_activation") is False,
      "adapter_production_deployment_forbidden":safety.get("production_deployment") is False,
      "adapter_production_merge_forbidden":safety.get("merge_to_production_branch") is False,
      "adapter_automatic_apply_forbidden":safety.get("automatic_apply") is False,
      "adapter_zero_external_spend":float(safety.get("automatic_external_spend_eur") or 0)==0,
      "receipt_schema":receipt.get("schema")=="chacha.dev/adapter-provisioning-receipt/v1",
      "receipt_adapter":receipt.get("adapter")=="branch-foundry-source-integrator-v1",
      "receipt_version":receipt.get("version")=="1.0.1",
      "receipt_applied":receipt.get("applied") is True,
      "receipt_probe_pass":(receipt.get("probe") or {}).get("status")=="PASS",
      "receipt_fail_closed_probe":(receipt.get("probe") or {}).get("result_status")=="BLOCKED" and (receipt.get("probe") or {}).get("result_reason")=="APPLY_SCHEMA_INVALID",
      "receipt_digest_chain":bool(source_digest) and receipt.get("source_digest")==receipt.get("installed_digest")==receipt.get("executable_digest")==source_digest,
      "receipt_trusted_executable_path":receipt.get("executable_path")==TRUSTED_EXECUTABLE,
      "registry_schema":registry.get("schema")=="chacha.dev/platform-component-apply-adapter-registry/v1",
      "registry_default_deny":registry.get("default_admission")=="DENY",
      "registry_source_candidate_only":reg_principles.get("source_release_candidate_only") is True,
      "registry_candidate_owner_required":reg_principles.get("candidate_owner_adapter_required") is True,
      "registry_reversible_required":reg_principles.get("reversible_apply_required") is True,
      "registry_rollback_required":reg_principles.get("rollback_adapter_required") is True,
      "registry_auto_apply_forbidden":reg_principles.get("automatic_apply_forbidden") is True,
      "component_not_already_registered":cid not in adapters,
      "dedicated_exact_sha_success":workflow_success(runs,DEDICATED_WORKFLOW,revision),
      "universal_exact_sha_success":workflow_success(runs,UNIVERSAL_WORKFLOW,revision),
      "sentinel_exact_sha_success":workflow_success(runs,SENTINEL_WORKFLOW,revision),
    }
    blockers=sorted(k for k,v in checks.items() if not v)
    if blockers:
        return {
          "schema":SCHEMA,"generated_at":now_iso(),"status":"BLOCKED",
          "component_id":cid,"candidate_owner":owner,"candidate_revision":candidate,
          "qualification_revision":revision,"checks":checks,"blockers":blockers,
          "registry_binding_proposed":False,"registry_mutation_authorized":False,
          "automatic_registration":False,"production_activation_allowed":False,
          "automatic_external_spend_eur":0
        }

    binding={
      "adapter_id":"branch-foundry-source-integrator-v1",
      "status":"QUALIFIED",
      "candidate_owner":"branch-foundry",
      "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "reversible":True,
      "rollback_adapter_id":"branch-foundry-source-integrator-v1",
      "exact_revision_enforced":True,
      "executable":TRUSTED_EXECUTABLE,
      "qualification_workflow_name":DEDICATED_WORKFLOW,
      "qualification_revision":revision,
      "provisioned_executable_digest":receipt.get("executable_digest"),
      "bound_component_id":cid,
      "bound_candidate_revision":candidate,
      "bound_incumbent_revision":incumbent,
      "bound_candidate_artifact_ref":controlled.get("candidate_artifact_ref"),
      "bound_incumbent_artifact_ref":controlled.get("incumbent_artifact_ref"),
      "bound_approval_id":controlled.get("approval_id"),
      "bound_technical_review_digest":controlled.get("technical_review_digest"),
      "direct_runtime_mutation":False,"production_activation":False,
      "production_deployment":False,"merge_to_production_branch":False,
      "automatic_apply":False,"automatic_external_spend_eur":0
    }
    return {
      "schema":SCHEMA,"generated_at":now_iso(),"status":"READY_FOR_CONTROLLED_REGISTRY_INTEGRATION",
      "component_id":cid,"candidate_owner":owner,"candidate_revision":candidate,
      "incumbent_revision":incumbent,"qualification_revision":revision,
      "checks":checks,"blockers":[],
      "registry_binding_proposed":True,"proposed_registry_key":cid,
      "proposed_registry_binding":binding,
      "registry_mutation_authorized":False,"automatic_registration":False,
      "central_orchestrator_registry_integration_required":True,
      "post_registration_exact_sha_qualification_required":True,
      "sentinel_post_registration_exact_sha_required":True,
      "production_activation_allowed":False,"automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--promotion-gate",type=Path,required=True)
    ap.add_argument("--adapter-policy",type=Path,required=True)
    ap.add_argument("--provisioning-receipt",type=Path,required=True)
    ap.add_argument("--adapter-registry",type=Path,required=True)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--github-runs-json",type=Path)
    ap.add_argument("--repository",default="chachasan090375/WfGg")
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    runs=load(a.github_runs_json) if a.github_runs_json else github_runs(a.repository,a.revision)
    source=a.repo_root.resolve()/"dev-hub/adapters/platform-component-branch-foundry-source-integrator.py"
    result=evaluate(load(a.promotion_gate),load(a.adapter_policy),load(a.provisioning_receipt),
                    load(a.adapter_registry),runs,a.revision,source)
    save(a.output,result)
    print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_GATE="+result["status"])
    print("REGISTRY_BINDING_PROPOSED="+("YES" if result.get("registry_binding_proposed") else "NO"))
    print("REGISTRY_MUTATION_AUTHORIZED=NO")
    print("AUTOMATIC_REGISTRATION=NO")
    print("PRODUCTION_ACTIVATION_ALLOWED=NO")
    print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"]=="READY_FOR_CONTROLLED_REGISTRY_INTEGRATION" else 20

if __name__=="__main__":raise SystemExit(main())
