#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def run(cmd):
    return subprocess.run([str(x) for x in cmd],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)

spec=importlib.util.spec_from_file_location("platform_component_adapter_registry_writer",BIN/"platform-component-adapter-registry-writer.py")
assert spec and spec.loader
writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(writer)

policy=load(CFG/"platform-component-adapter-registry-writer.v1.json")
writer.validate_policy(policy)
canonical=load(CFG/"platform-component-apply-adapter-registry.v1.json")
assert canonical["default_admission"]=="DENY" and canonical["adapters"]=={},canonical

binding={
 "adapter_id":"branch-foundry-source-integrator-v1","status":"QUALIFIED",
 "candidate_owner":"branch-foundry","apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
 "reversible":True,"rollback_adapter_id":"branch-foundry-source-integrator-v1",
 "exact_revision_enforced":True,
 "executable":"/opt/chacha-dev/adapters/platform-component/branch-foundry-source-integrator/current/branch-foundry-source-integrator",
 "qualification_workflow_name":"ChaCha DEV Branch Foundry source integrator qualification",
 "direct_runtime_mutation":False,"production_activation":False,
 "production_deployment":False,"merge_to_production_branch":False,
 "automatic_apply":False,"automatic_external_spend_eur":0
}

with tempfile.TemporaryDirectory(prefix="adapter-registry-writer-") as raw:
    td=Path(raw);repo=td/"repo";runtime=td/"runtime"
    registry_path=repo/"dev-hub/config/platform-component-apply-adapter-registry.v1.json"
    before=load(CFG/"platform-component-apply-adapter-registry.v1.json")
    before["adapters"]["unrelated-component"]={
      "adapter_id":"unrelated-safe-adapter","status":"QUALIFIED","candidate_owner":"branch-foundry",
      "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION","reversible":True,
      "rollback_adapter_id":"unrelated-safe-adapter","exact_revision_enforced":True,
      "executable":"/opt/chacha-dev/adapters/platform-component/unrelated/current/unrelated",
      "qualification_workflow_name":"Unrelated qualification",
      "direct_runtime_mutation":False,"production_activation":False,
      "production_deployment":False,"merge_to_production_branch":False,
      "automatic_apply":False,"automatic_external_spend_eur":0
    }
    save(registry_path,before)
    after=json.loads(json.dumps(before));after["adapters"]["central-orchestrator"]=binding
    contract={
      "schema":"chacha.dev/platform-component-adapter-registration-contract/v1",
      "registration_id":"pcar-test-001","project":"chacha-dev-platform","actor":"central-orchestrator",
      "issued_by_project_control":True,"human_approval_verified":True,
      "approval_id":"adapter-registration-test","approval_actor":"human-platform-owner",
      "approval_evidence":"platform-component-adapter-binding-proposal:sha256:test",
      "binding_proposal_digest":"sha256:"+"a"*64,
      "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
      "candidate_revision":"b"*40,"incumbent_revision":"c"*40,
      "candidate_artifact_ref":"git:candidate@"+"b"*40,
      "incumbent_artifact_ref":"git:incumbent@"+"c"*40,
      "adapter_id":"branch-foundry-source-integrator-v1",
      "registry_path":"dev-hub/config/platform-component-apply-adapter-registry.v1.json",
      "registry_key":"central-orchestrator",
      "registry_before_digest":writer.canonical_digest(before),
      "registry_after_digest":writer.canonical_digest(after),
      "exact_registry_binding":binding,
      "registration_authorized":True,
      "registry_mutation_authorized_for_dedicated_writer":True,
      "additive_write_only":True,"overwrite_authorized":False,"delete_authorized":False,
      "default_deny_must_be_preserved":True,"single_use":True,
      "source_integration_authorized":False,
      "post_registration_exact_sha_gates_required":[
        "ChaCha DEV platform adapter binding gate qualification",
        "ChaCha DEV universal evolution coverage sync qualification",
        "ChaCha DEV Sentinel technical assurance"
      ],
      "direct_runtime_mutation_authorized":False,
      "production_activation_authorized":False,"production_deployment_authorized":False,
      "merge_to_production_branch_authorized":False,"automatic_apply":False,
      "automatic_external_spend_eur":0
    }
    contract_path=td/"contract.json";save(contract_path,contract)

    planned=writer.plan(repo,policy,contract)
    assert planned["status"]=="READY",planned
    assert planned["registry_before_digest"]==contract["registry_before_digest"],planned
    assert planned["registry_after_digest"]==contract["registry_after_digest"],planned
    assert planned["commit_performed"] is False and planned["push_performed"] is False,planned
    assert load(registry_path)==before

    # CLI requires the explicit --apply flag and must not mutate without it.
    cli=run([
      sys.executable,BIN/"platform-component-adapter-registry-writer.py",
      "--repo-root",repo,"--policy",CFG/"platform-component-adapter-registry-writer.v1.json",
      "--registration-contract",contract_path,"--runtime-root",runtime,
      "apply","--receipt",td/"noapply-receipt.json"
    ])
    assert cli.returncode==2,(cli.stdout,cli.stderr)
    assert "EXPLICIT_APPLY_FLAG_REQUIRED" in cli.stdout
    assert load(registry_path)==before

    receipt=writer.apply(repo,policy,contract,runtime)
    current=load(registry_path)
    assert receipt["schema"]=="chacha.dev/platform-component-adapter-registry-write-receipt/v1",receipt
    assert receipt["status"]=="PASS",receipt
    assert current["default_admission"]=="DENY",current
    assert current["adapters"]["central-orchestrator"]==binding,current
    assert current["adapters"]["unrelated-component"]==before["adapters"]["unrelated-component"],current
    assert writer.canonical_digest(current)==contract["registry_after_digest"]
    assert receipt["additive_single_key_write"] is True,receipt
    assert receipt["overwrite_performed"] is False and receipt["delete_performed"] is False,receipt
    assert receipt["commit_performed"] is False and receipt["push_performed"] is False,receipt
    assert receipt["post_registration_exact_sha_gates_pending"] is True,receipt
    assert receipt["source_integration_authorized"] is False,receipt
    assert receipt["production_activation"] is False and receipt["production_deployment"] is False,receipt

    rolled=writer.rollback(repo,policy,contract,receipt)
    restored=load(registry_path)
    assert rolled["schema"]=="chacha.dev/platform-component-adapter-registry-rollback-receipt/v1",rolled
    assert rolled["status"]=="PASS" and rolled["rollback_proven"] is True,rolled
    assert restored==before,(restored,before)
    assert restored["adapters"]["unrelated-component"]==before["adapters"]["unrelated-component"]
    assert "central-orchestrator" not in restored["adapters"]

    # The same single-use registration contract cannot mutate a second time.
    try:
        writer.apply(repo,policy,contract,runtime)
    except RuntimeError as e:
        assert "REGISTRATION_CONTRACT_REPLAY_BLOCKED" in str(e),e
    else:
        raise AssertionError("single-use registration contract replay accepted")
    assert load(registry_path)==before

    # Existing target key always blocks overwrite.
    occupied=json.loads(json.dumps(before));occupied["adapters"]["central-orchestrator"]={"adapter_id":"do-not-overwrite"}
    save(registry_path,occupied)
    contract2=json.loads(json.dumps(contract));contract2["registration_id"]="pcar-test-002"
    contract2["registry_before_digest"]=writer.canonical_digest(occupied)
    try:
        writer.plan(repo,policy,contract2)
    except RuntimeError as e:
        assert "REGISTRY_KEY_ALREADY_EXISTS" in str(e),e
    else:
        raise AssertionError("existing registry key overwrite accepted")

    # Path escape is impossible even with an otherwise valid contract.
    save(registry_path,before)
    badpath=json.loads(json.dumps(contract));badpath["registry_path"]="../outside.json"
    try:
        writer.plan(repo,policy,badpath)
    except RuntimeError as e:
        assert "REGISTRY_PATH_CONTRACT_MISMATCH" in str(e),e
    else:
        raise AssertionError("noncanonical registry path accepted")

    # A weakened writer policy fails closed.
    weak=json.loads(json.dumps(policy));weak["principles"]["overwrite_forbidden"]=False
    try:
        writer.validate_policy(weak)
    except RuntimeError as e:
        assert "REGISTRY_WRITER_POLICY_WEAKENED" in str(e),e
    else:
        raise AssertionError("weakened writer policy accepted")

guardian=load(CFG/"guardian-coverage-manifest.v1.json")
assert any(x.get("component_id")=="platform-component-adapter-registry-writer" for x in guardian["expected_components"]),guardian
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(guardian["expected_components"])*12*24

core=load(CFG/"technology-core-watch.v1.json")
crow=next(x for x in core["components"] if x["id"]=="platform-component-adapter-registry-writer")
assert crow["class"]=="execution" and crow["criticality"]=="critical",crow

roles=load(CFG/"guardian-role-contracts.v1.json")
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:platform-component-adapter-registry-writer")
assert set(role["allowed_permissions"])=={"read","plan","workspace-write"},role
assert {"OVERWRITE_ADAPTER_BINDING","DELETE_UNRELATED_BINDING","PRODUCTION_DEPLOY","PROMOTE_COMPONENT","SOURCE_INTEGRATION","MUTATE_RUNTIME"}<=set(role["forbidden_actions"]),role

source=(BIN/"platform-component-adapter-registry-writer.py").read_text(encoding="utf-8")
assert "os.system" not in source
assert "shell=True" not in source
assert "git push" not in source
assert "subprocess" not in source

print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_WRITER=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_EXPLICIT_APPLY=REQUIRED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_SINGLE_KEY=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_OVERWRITE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_UNRELATED_DELETE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_SINGLE_USE=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_ROLLBACK=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_DEFAULT_DENY=PRESERVED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_COMMIT=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_PUSH=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_POST_GATES=PENDING")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_SOURCE_INTEGRATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_GUARDIAN_COVERAGE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
