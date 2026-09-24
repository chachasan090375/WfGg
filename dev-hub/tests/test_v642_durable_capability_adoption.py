#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def save(path:Path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")

def load(path:Path):
    return json.loads(path.read_text(encoding="utf-8"))

def run(args,cwd=None,expect=0):
    p=subprocess.run([str(x) for x in args],cwd=str(cwd) if cwd else None,
                     text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p.returncode==expect,{"args":[str(x) for x in args],"rc":p.returncode,
                                "stdout":p.stdout,"stderr":p.stderr}
    return p

def sha256_file(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def project_control_proof(root:Path,project_id:str,task_id:str,claims_path:Path)->Path:
    verified=root/"verified-task-result.json"
    receipt=root/"project-control-receipt.json"
    claims_digest=sha256_file(claims_path)
    save(verified,{
      "schema":"chacha.dev/task-result/v1","project":project_id,"task_id":task_id,
      "producer":"v642-project-runtime","status":"OK","summary":"Verified project capability success.",
      "observed_at":"2026-09-24T00:00:00+00:00","outputs":[],
      "evidence":[{"source":str(claims_path.resolve()),"digest":claims_digest}],
      "verification":{"status":"VERIFIED","method":"machine","verifier":"verification-broker"}
    })
    save(receipt,{
      "schema":"chacha.dev/control-transaction-receipt/v1",
      "transaction_id":"ctx-v642-test","project":project_id,"operation":"verify-result",
      "status":"COMMITTED","verification_status":"VERIFIED",
      "verified_result":str(verified),"report":str(root/"verification-report.json"),
      "updated_at":"2026-09-24T00:00:00+00:00"
    })
    return receipt

with tempfile.TemporaryDirectory(prefix="v642-e2e-") as td_raw:
    td=Path(td_raw)
    repo=td/"repo"
    shutil.copytree(ROOT/"dev-hub",repo/"dev-hub")
    build_work=td/"build-work"
    sandbox_runtime=td/"sandbox-runtime"
    build_request=td/"build-request.json"

    capability="v642-durable-read"
    provider="v642-durable-provider"
    adapter="v642-durable-adapter"
    project="v642-project-one"

    request={
      "schema":"chacha.dev/capability-build-request/v1",
      "project_id":project,
      "capability":capability,
      "provider_id":provider,
      "adapter_id":adapter,
      "profile":"structured-read-v1",
      "execution":"vps",
      "supports":["read"],
      "network_access":False,
      "credentials_required":False,
      "production_capable":False,
      "automatic_external_spend_eur":0,
      "technology_watch":{"consulted":True,"candidate_source":"v642-e2e"},
      "architecture_council":{"decision":"APPROVED","decision_id":"v642-build-council"}
    }
    save(build_request,request)

    build_result=td/"build-result.json"
    build_overlay=td/"build-overlay.json"
    run([
      "python3",repo/"dev-hub/bin/capability-build-loop.py",
      "--policy",repo/"dev-hub/config/capability-build-loop.v1.json",
      "--request",build_request,"--repo-root",repo,
      "--base-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--workspace",build_work,"build-pilot",
      "--runtime-root",sandbox_runtime,
      "--output",build_result,"--overlay",build_overlay,"--apply"
    ])

    br=load(build_result)
    assert br["status"]=="PASS" and br["adapter_status"]=="ENABLED",br
    assert br["durable_adoption"]=="PENDING_PROJECT_SUCCESS",br

    candidate=td/"candidate.json"
    save(candidate,{
      "schema":"chacha.dev/capability-adoption-candidate/v1",
      "source_kind":"BUILT_ADAPTER",
      "project_id":project,
      "capability":capability,"provider":provider,"adapter":adapter,
      "build_result":str(build_result),
      "production_capable":False,"network_access":False,"credentials_required":False,
      "automatic_external_spend_eur":0,
      "adoption_state":"PENDING_PROJECT_SUCCESS"
    })

    success=td/"success.json"
    claims=td/"project-success-claims.json"
    claims_value={
      "project_id":project,
      "capability":capability,"provider":provider,"adapter":adapter,
      "status":"PASS","project_success":True,
      "quality_gates_pass":True,"runtime_use_count":3,"incident_count":0,
      "technology_watch_revalidated":True,
      "architecture_council":{"decision":"APPROVED","decision_id":"v642-adopt-council"},
      "automatic_external_spend_eur":0,
      "evidence_refs":["evidence:v642-project-success","evidence:v642-runtime-use"]
    }
    save(claims,claims_value)
    pc_receipt=project_control_proof(td,project,"v642-project-success",claims)
    save(success,{
      "schema":"chacha.dev/capability-project-success/v1",
      **claims_value,
      "verification_status":"VERIFIED",
      "project_control_receipt":str(pc_receipt),
      "verified_task_id":"v642-project-success",
      "verified_claims_path":str(claims),
      "verified_claims_digest":sha256_file(claims)
    })

    durable=td/"runtime/registries/durable.json"
    adapter_root=td/"runtime/adapters"
    archive=td/"runtime/sources"
    evidence=td/"runtime/evidence"
    experience_db=td/"runtime/knowledge/experience.db"
    memory_db=td/"runtime/knowledge/central-memory.db"
    memory_snapshot=td/"runtime/knowledge/central-memory.json"
    receipt=td/"adoption-receipt.json"

    adopted=run([
      "python3",repo/"dev-hub/bin/durable-capability-registry.py","adopt",
      "--policy",repo/"dev-hub/config/durable-capability-adoption.v1.json",
      "--candidate",candidate,"--success",success,
      "--base-capability-registry",repo/"dev-hub/config/capability-registry.v1.json",
      "--base-provider-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--registry",durable,"--repo-root",repo,"--adapter-root",adapter_root,
      "--source-archive-root",archive,"--evidence-root",evidence,
      "--experience-db",experience_db,"--central-memory-db",memory_db,
      "--central-memory-snapshot",memory_snapshot,"--memory-refresh",
      "--actor","central-orchestrator","--receipt",receipt,"--apply"
    ])
    assert "CHACHA_DEV_V642_DURABLE_ADOPTION=PASS" in adopted.stdout,adopted.stdout

    rr=load(receipt)
    assert rr["status"]=="COMMITTED" and rr["applied"] is True,rr
    assert Path(rr["durable_executable"]).is_file(),rr
    assert Path(rr["source_archive"]).is_file(),rr
    reg=load(durable)
    aid=rr["adoption_id"]
    assert reg["adoptions"][aid]["status"]=="ADOPTED",reg
    assert reg["capabilities"][capability]["providers"][0]["status"]=="ADOPT",reg
    assert reg["adapters"][adapter]["status"]=="ENABLED",reg
    assert reg["adapters"][adapter]["executable"]==rr["durable_executable"],reg

    merged_caps=td/"merged-capabilities.json"
    merged_providers=td/"merged-providers.json"
    merged=run([
      "python3",repo/"dev-hub/bin/durable-capability-registry.py","merge",
      "--base-capability-registry",repo/"dev-hub/config/capability-registry.v1.json",
      "--base-provider-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--registry",durable,"--output-capabilities",merged_caps,
      "--output-providers",merged_providers,"--require-executables"
    ])
    assert "CHACHA_DEV_V642_DURABLE_REUSE_COUNT=1" in merged.stdout,merged.stdout
    mc=load(merged_caps);mp=load(merged_providers)
    assert capability in mc["capabilities"],mc
    assert provider in mp["providers"] and adapter in mp["adapters"],mp
    assert mp["adapters"][adapter]["status"]=="ENABLED",mp

    # A second project requiring the same capability now has NO gap.
    # Import the candidate repo exactly as a runtime would: its sibling helper
    # modules live in dev-hub/bin and must be resolvable.
    temp_bin=str(repo/"dev-hub/bin")
    if temp_bin not in sys.path:
        sys.path.insert(0,temp_bin)
    spec=importlib.util.spec_from_file_location("v642_orchestrator",repo/"dev-hub/bin/autonomous-project-orchestrator.py")
    orch=importlib.util.module_from_spec(spec);spec.loader.exec_module(orch)
    preplan=td/"project-two-preplan.json"
    contract=td/"project-two-contract.json"
    gaps=td/"project-two-gaps.json"
    save(preplan,{"packages":[{"domain":"product","capabilities":[capability]}]})
    save(contract,{"capability_hints":[{"id":capability,"domain":"product"}]})
    orch.capability_gaps(preplan,contract,merged_caps,"v642-project-two",gaps)
    assert load(gaps)["missing_capabilities"]==[],load(gaps)

    health=td/"health.json"
    save(health,{"schema":"chacha.dev/provider-health-snapshot/v1",
                 "providers":{provider:{"state":"HEALTHY","observed_at":"V642"}}})
    graph=td/"graph.json"
    save(graph,{"schema":"chacha.dev/task-graph/v1","project":"v642-project-two",
                "transition":"BUILD->VERIFY",
                "tasks":[{"id":"reuse-durable-capability","kind":"verification",
                          "permission":"read","capabilities":[capability],"depends_on":[]}]})
    exec_plan=td/"execution-plan.json"
    run([
      "python3",repo/"dev-hub/bin/execution-scheduler.py",
      "--graph",graph,"--registry",merged_caps,"--health",health,
      "--policy",repo/"dev-hub/config/execution-scheduler.v1.json",
      "--output",exec_plan
    ])
    ep=load(exec_plan)
    assert ep["summary"]["scheduled_count"]==1 and ep["summary"]["blocked_count"]==0,ep
    binding=ep["waves"][0]["tasks"][0]["provider_bindings"][0]
    assert binding["provider"]==provider and binding["capability"]==capability,binding

    # Official memory event was recorded and assimilated, but a single project
    # does not magically become globally trusted.
    db=sqlite3.connect(experience_db)
    rows=db.execute("SELECT learner,outcome,payload FROM experience").fetchall()
    assert any(r[0]=="capability-durable-adoption" and r[1]=="success" for r in rows),rows
    memory=load(memory_snapshot)
    assert memory["schema"]=="chacha.dev/central-memory-assimilation/v1",memory
    assert memory["single_observation_never_trusted"] is True,memory
    assert memory["trusted_generalizable_count"]==0,memory

    # Replaying the same verified success is idempotent.
    receipt2=td/"adoption-receipt-2.json"
    replay=run([
      "python3",repo/"dev-hub/bin/durable-capability-registry.py","adopt",
      "--policy",repo/"dev-hub/config/durable-capability-adoption.v1.json",
      "--candidate",candidate,"--success",success,
      "--base-capability-registry",repo/"dev-hub/config/capability-registry.v1.json",
      "--base-provider-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--registry",durable,"--repo-root",repo,"--adapter-root",adapter_root,
      "--source-archive-root",archive,"--evidence-root",evidence,
      "--experience-db",experience_db,"--actor","central-orchestrator",
      "--receipt",receipt2,"--apply"
    ])
    assert load(receipt2)["status"]=="IDEMPOTENT",load(receipt2)
    assert "CHACHA_DEV_V642_DURABLE_ADOPTION_APPLIED=NO" in replay.stdout,replay.stdout

    # Rollback removes durable selection but deliberately retains binary/source
    # for forensics.
    rollback_receipt=td/"rollback.json"
    run([
      "python3",repo/"dev-hub/bin/durable-capability-registry.py","rollback",
      "--registry",durable,"--adoption-id",aid,"--actor","central-orchestrator",
      "--receipt",rollback_receipt,"--apply"
    ])
    rb=load(rollback_receipt)
    assert rb["status"]=="ROLLED_BACK" and rb["adapter_binary_retained_for_forensics"] is True,rb
    assert Path(rr["durable_executable"]).is_file(),rr
    assert Path(rr["source_archive"]).is_file(),rr

    merged_caps_after=td/"merged-capabilities-after.json"
    merged_providers_after=td/"merged-providers-after.json"
    run([
      "python3",repo/"dev-hub/bin/durable-capability-registry.py","merge",
      "--base-capability-registry",repo/"dev-hub/config/capability-registry.v1.json",
      "--base-provider-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--registry",durable,"--output-capabilities",merged_caps_after,
      "--output-providers",merged_providers_after,"--require-executables"
    ])
    assert capability not in load(merged_caps_after)["capabilities"],load(merged_caps_after)

# Production/network/credential adoption keeps a separate human boundary.
with tempfile.TemporaryDirectory(prefix="v642-human-boundary-") as td_raw:
    td=Path(td_raw)
    candidate=td/"candidate.json";success=td/"success.json";receipt=td/"receipt.json"
    save(candidate,{
      "schema":"chacha.dev/capability-adoption-candidate/v1",
      "source_kind":"EXISTING_PROVIDER","project_id":"v642-protected-project",
      "capability":"v642-protected-capability",
      "provider":"cloudflare-pages-production","adapter":"cloudflare-pages-production-adapter",
      "build_result":None,"production_capable":True,"network_access":True,
      "credentials_required":True,"automatic_external_spend_eur":0
    })
    protected_claims=td/"protected-success-claims.json"
    protected_claims_value={
      "project_id":"v642-protected-project","capability":"v642-protected-capability",
      "provider":"cloudflare-pages-production","adapter":"cloudflare-pages-production-adapter",
      "status":"PASS","project_success":True,
      "quality_gates_pass":True,"runtime_use_count":1,"incident_count":0,
      "technology_watch_revalidated":True,
      "architecture_council":{"decision":"APPROVED","decision_id":"v642-protected-council"},
      "automatic_external_spend_eur":0,"evidence_refs":["evidence:protected"]
    }
    save(protected_claims,protected_claims_value)
    protected_pc_receipt=project_control_proof(td,"v642-protected-project","v642-protected-success",protected_claims)
    save(success,{
      "schema":"chacha.dev/capability-project-success/v1",
      **protected_claims_value,
      "verification_status":"VERIFIED",
      "project_control_receipt":str(protected_pc_receipt),
      "verified_task_id":"v642-protected-success",
      "verified_claims_path":str(protected_claims),
      "verified_claims_digest":sha256_file(protected_claims)
    })
    p=run([
      "python3",BIN/"durable-capability-registry.py","adopt",
      "--policy",CFG/"durable-capability-adoption.v1.json",
      "--candidate",candidate,"--success",success,
      "--base-capability-registry",CFG/"capability-registry.v1.json",
      "--base-provider-registry",CFG/"provider-adapters.v1.json",
      "--registry",td/"durable.json","--repo-root",ROOT,"--adapter-root",td/"adapters",
      "--source-archive-root",td/"sources","--evidence-root",td/"evidence",
      "--experience-db",td/"experience.db","--actor","central-orchestrator",
      "--receipt",receipt,"--apply"
    ],expect=1)
    assert "DURABLE_ADOPTION_HUMAN_APPROVAL_REQUIRED" in (p.stderr+p.stdout),p.stderr+p.stdout

# Static integration invariants in the central brain.
orch_text=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"durable-capability-registry.py"' in orch_text
assert 'capability_gaps(pre,contract,durable_caps,pid,gapreq)' in orch_text
assert '"--capabilities",durable_caps' in orch_text
assert '"--provider-adapters",durable_providers' in orch_text
assert '"schema":"chacha.dev/capability-adoption-candidates/v1"' in orch_text
assert '"adoption_state":"PENDING_PROJECT_SUCCESS"' in orch_text
assert '"durable_registry_merged_before_gap_detection":True' in orch_text

print("CHACHA_DEV_V642_VERIFIED_SUCCESS_BEFORE_ADOPTION=PASS")
print("CHACHA_DEV_V642_PROJECT_CONTROL_COMMITTED_PROOF=PASS")
print("CHACHA_DEV_V642_SUCCESS_CLAIMS_BOUND_TO_VERIFIED_RESULT=PASS")
print("CHACHA_DEV_V642_RELEASE_INDEPENDENT_DURABLE_REGISTRY=PASS")
print("CHACHA_DEV_V642_DURABLE_ADAPTER_REPROBE=PASS")
print("CHACHA_DEV_V642_CROSS_PROJECT_REUSE_WITHOUT_REBUILD=PASS")
print("CHACHA_DEV_V642_EXPERIENCE_MEMORY_EVENT=PASS")
print("CHACHA_DEV_V642_SINGLE_PROJECT_NOT_GLOBAL_TRUST=PASS")
print("CHACHA_DEV_V642_IDEMPOTENT_ADOPTION=PASS")
print("CHACHA_DEV_V642_ROLLBACK_RETAINS_FORENSICS=PASS")
print("CHACHA_DEV_V642_PROTECTED_ADOPTION_HUMAN_BOUNDARY=PASS")
print("CHACHA_DEV_V642_DURABLE_REGISTRY_MERGED_BEFORE_GAPS=PASS")
print("CHACHA_DEV_V642_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
