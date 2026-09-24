#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/platform-component-adapter-binding-gate/v1"
PROPOSAL_SCHEMA="chacha.dev/platform-component-adapter-binding-proposal/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def digest_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return "sha256:"+h.hexdigest()

def under(path:Path,root:Path)->bool:
    try:path.resolve(strict=False).relative_to(root.resolve(strict=False));return True
    except Exception:return False

def workflow_success(runs:dict[str,Any],name:str,revision:str)->bool:
    return any(
      isinstance(x,dict) and x.get("name")==name and x.get("head_sha")==revision and
      x.get("status")=="completed" and x.get("conclusion")=="success"
      for x in (runs.get("workflow_runs") or [])
    )

def evaluate(repo_root:Path,gate_policy:dict[str,Any],promotion_gate:dict[str,Any],
             registry:dict[str,Any],adapter_policy:dict[str,Any],
             provisioning_policy:dict[str,Any],receipt:dict[str,Any],
             runs:dict[str,Any],qualification_revision:str)->dict[str,Any]:
    principles=gate_policy.get("principles") if isinstance(gate_policy.get("principles"),dict) else {}
    contract=promotion_gate.get("controlled_apply_contract") if isinstance(promotion_gate.get("controlled_apply_contract"),dict) else {}
    component=str(contract.get("component_id") or promotion_gate.get("component_id") or "")
    owner=str(contract.get("candidate_owner") or "")
    adapter_id=str(adapter_policy.get("adapter_id") or "")
    prov=((provisioning_policy.get("adapters") or {}).get(adapter_id) or {}) if adapter_id else {}
    source_rel=str(prov.get("source") or "")
    source=(repo_root/source_rel).resolve() if source_rel else Path("/nonexistent")
    exe=Path(str(receipt.get("executable_path") or ""))
    trusted_root=Path(str(principles.get("trusted_executable_root") or "/nonexistent"))
    operations=adapter_policy.get("operations") if isinstance(adapter_policy.get("operations"),dict) else {}
    safety=adapter_policy.get("safety") if isinstance(adapter_policy.get("safety"),dict) else {}
    qualification=adapter_policy.get("qualification") if isinstance(adapter_policy.get("qualification"),dict) else {}
    existing=((registry.get("adapters") or {}).get(component)) if component else None
    required_workflows=[str(x) for x in gate_policy.get("required_exact_sha_workflows") or [] if str(x)]
    exact_sha_ok=bool(re.fullmatch(r"[0-9a-f]{40}",qualification_revision or ""))
    source_digest=digest_file(source) if source.is_file() else None

    checks={
      "gate_policy_schema":gate_policy.get("schema")=="chacha.dev/platform-component-adapter-binding-gate-policy/v1",
      "proposal_only_purpose":gate_policy.get("purpose")=="PROPOSE_COMPONENT_SPECIFIC_APPLY_ADAPTER_BINDING_ONLY",
      "promotion_gate_schema":promotion_gate.get("schema")=="chacha.dev/platform-component-promotion-gate/v1",
      "promotion_gate_authorized":promotion_gate.get("status")=="PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",
      "human_approval_verified":promotion_gate.get("human_approval_verified") is True,
      "controlled_apply_contract_present":contract.get("schema")=="chacha.dev/platform-component-controlled-apply-contract/v1",
      "component_present":bool(component),
      "candidate_owner_present":bool(owner),
      "candidate_revision_exact":bool(re.fullmatch(r"[0-9a-f]{40}",str(contract.get("candidate_revision") or ""))),
      "incumbent_revision_exact":bool(re.fullmatch(r"[0-9a-f]{40}",str(contract.get("incumbent_revision") or ""))),
      "candidate_artifact_present":bool(str(contract.get("candidate_artifact_ref") or "")),
      "incumbent_artifact_present":bool(str(contract.get("incumbent_artifact_ref") or "")),
      "source_only_contract":contract.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "contract_runtime_mutation_forbidden":contract.get("direct_runtime_mutation_authorized") is False,
      "contract_production_activation_forbidden":contract.get("production_activation_authorized") is False,
      "contract_production_deployment_forbidden":contract.get("production_deployment_authorized") is False,
      "contract_production_merge_forbidden":contract.get("merge_to_production_branch_authorized") is False,
      "registry_schema":registry.get("schema")=="chacha.dev/platform-component-apply-adapter-registry/v1",
      "registry_default_deny":registry.get("default_admission")=="DENY",
      "component_not_already_bound":existing is None,
      "adapter_policy_schema":adapter_policy.get("schema")=="chacha.dev/platform-component-branch-foundry-source-integrator/v1",
      "adapter_policy_qualified":adapter_policy.get("status")=="QUALIFIED",
      "adapter_not_live_registered":qualification.get("registered_for_live_component") is False,
      "adapter_owner_matches":adapter_policy.get("candidate_owner")==owner,
      "adapter_mode_matches":adapter_policy.get("mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "adapter_apply_and_rollback_only":set(operations.get("allowed") or [])=={"apply","rollback"},
      "adapter_fixed_argv":operations.get("fixed_argv") is True,
      "adapter_shell_interpolation_forbidden":operations.get("shell_interpolation") is False,
      "adapter_reversible":safety.get("reversible") is True,
      "adapter_exact_revision":safety.get("exact_revision_enforced") is True,
      "adapter_runtime_mutation_forbidden":safety.get("direct_runtime_mutation") is False,
      "adapter_production_activation_forbidden":safety.get("production_activation") is False,
      "adapter_production_deployment_forbidden":safety.get("production_deployment") is False,
      "adapter_production_merge_forbidden":safety.get("merge_to_production_branch") is False,
      "adapter_automatic_apply_forbidden":safety.get("automatic_apply") is False,
      "adapter_zero_external_spend":float(safety.get("automatic_external_spend_eur") or 0)==0,
      "provisioning_policy_schema":provisioning_policy.get("schema")=="chacha.dev/adapter-provisioning/v1",
      "provisioning_entry_present":isinstance(prov,dict) and bool(prov),
      "provisioning_version_matches":str(prov.get("version") or "")==str(receipt.get("version") or "") and bool(prov.get("version")),
      "provisioning_source_matches":source_rel=="dev-hub/adapters/platform-component-branch-foundry-source-integrator.py",
      "receipt_schema":receipt.get("schema")=="chacha.dev/adapter-provisioning-receipt/v1",
      "receipt_adapter_matches":receipt.get("adapter")==adapter_id and bool(adapter_id),
      "receipt_applied":receipt.get("applied") is True,
      "receipt_probe_pass":((receipt.get("probe") or {}).get("status")=="PASS"),
      "source_file_present":source.is_file(),
      "source_digest_matches_receipt":bool(source_digest) and source_digest==receipt.get("source_digest"),
      "installed_digest_matches_source":bool(source_digest) and receipt.get("installed_digest")==source_digest,
      "executable_digest_matches_source":bool(source_digest) and receipt.get("executable_digest")==source_digest,
      "executable_under_trusted_root":bool(str(exe)) and under(exe,trusted_root),
      "qualification_revision_exact_sha":exact_sha_ok,
      "all_required_exact_sha_workflows_success":exact_sha_ok and bool(required_workflows) and all(workflow_success(runs,w,qualification_revision) for w in required_workflows),
      "automatic_registration_forbidden":principles.get("automatic_registration_forbidden") is True,
      "registry_mutation_forbidden":principles.get("registry_mutation_forbidden") is True,
      "protected_registration_required":principles.get("protected_registration_required") is True,
      "gate_zero_external_spend":float(principles.get("automatic_external_spend_eur") or 0)==0,
    }
    blockers=sorted(k for k,v in checks.items() if not v)
    ready=not blockers
    proposal=None
    if ready:
        proposal={
          "schema":PROPOSAL_SCHEMA,
          "component_id":component,
          "candidate_owner":owner,
          "candidate_revision":contract.get("candidate_revision"),
          "incumbent_revision":contract.get("incumbent_revision"),
          "candidate_artifact_ref":contract.get("candidate_artifact_ref"),
          "incumbent_artifact_ref":contract.get("incumbent_artifact_ref"),
          "approval_id":contract.get("approval_id"),
          "approval_actor":contract.get("approval_actor"),
          "approval_evidence":contract.get("approval_evidence"),
          "technical_review_digest":contract.get("technical_review_digest"),
          "qualification_revision":qualification_revision,
          "binding":{
            "adapter_id":adapter_id,
            "status":"QUALIFIED",
            "candidate_owner":owner,
            "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
            "reversible":True,
            "rollback_adapter_id":adapter_id,
            "exact_revision_enforced":True,
            "executable":str(exe),
            "qualification_workflow_name":"ChaCha DEV Branch Foundry source integrator qualification",
            "direct_runtime_mutation":False,
            "production_activation":False,
            "production_deployment":False,
            "merge_to_production_branch":False,
            "automatic_apply":False,
            "automatic_external_spend_eur":0
          },
          "provisioned_byte_digest":source_digest,
          "registration_authorized":False,
          "registry_mutation_authorized":False,
          "protected_registration_required":True,
          "automatic_registration":False,
          "automatic_external_spend_eur":0
        }
    return {
      "schema":SCHEMA,"generated_at":now_iso(),"status":"BINDING_PROPOSAL_READY_AWAIT_PROTECTED_REGISTRATION" if ready else "BLOCKED",
      "component_id":component,"candidate_revision":contract.get("candidate_revision"),
      "checks":checks,"blockers":blockers,"proposal_created":proposal is not None,
      "binding_proposal":proposal,"registration_authorized":False,
      "registry_mutation_authorized":False,"automatic_registration":False,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--promotion-gate",type=Path,required=True)
    ap.add_argument("--registry",type=Path,required=True)
    ap.add_argument("--adapter-policy",type=Path,required=True)
    ap.add_argument("--provisioning-policy",type=Path,required=True)
    ap.add_argument("--provisioning-receipt",type=Path,required=True)
    ap.add_argument("--qualification-runs",type=Path,required=True)
    ap.add_argument("--qualification-revision",required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    result=evaluate(a.repo_root.resolve(),load(a.policy),load(a.promotion_gate),load(a.registry),
                    load(a.adapter_policy),load(a.provisioning_policy),load(a.provisioning_receipt),
                    load(a.qualification_runs),a.qualification_revision)
    save(a.output,result)
    print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_GATE="+result["status"])
    print("BINDING_PROPOSAL_CREATED="+("YES" if result["proposal_created"] else "NO"))
    print("REGISTRATION_AUTHORIZED=NO")
    print("REGISTRY_MUTATION_AUTHORIZED=NO")
    print("AUTOMATIC_REGISTRATION=NO")
    print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"]=="BINDING_PROPOSAL_READY_AWAIT_PROTECTED_REGISTRATION" else 20

if __name__=="__main__":raise SystemExit(main())
