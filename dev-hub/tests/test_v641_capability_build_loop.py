#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
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

def run(args,cwd=None):
    p=subprocess.run([str(x) for x in args],cwd=str(cwd) if cwd else None,
                     text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if p.returncode!=0:
        raise AssertionError({"args":[str(x) for x in args],"rc":p.returncode,
                              "stdout":p.stdout,"stderr":p.stderr})
    return p

with tempfile.TemporaryDirectory(prefix="v641-build-loop-") as td:
    td=Path(td)
    repo=td/"repo"
    shutil.copytree(ROOT/"dev-hub",repo/"dev-hub")
    work=td/"work"
    runtime=td/"runtime"
    request=td/"request.json"

    req={
      "schema":"chacha.dev/capability-build-request/v1",
      "project_id":"v641-e2e-project",
      "capability":"v641-generated-read",
      "provider_id":"v641-generated-read-provider",
      "adapter_id":"v641-generated-read-adapter",
      "profile":"structured-read-v1",
      "execution":"vps",
      "supports":["read"],
      "network_access":False,
      "credentials_required":False,
      "production_capable":False,
      "automatic_external_spend_eur":0,
      "technology_watch":{"consulted":True,"candidate_source":"v641-test"},
      "architecture_council":{"decision":"APPROVED","decision_id":"v641-test-council"}
    }
    save(request,req)

    plan=run([
      "python3",repo/"dev-hub/bin/capability-build-loop.py",
      "--policy",repo/"dev-hub/config/capability-build-loop.v1.json",
      "--request",request,
      "--repo-root",repo,
      "--base-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--workspace",work,
      "plan"
    ])
    p=json.loads(plan.stdout)
    assert p["status"]=="READY",p
    assert p["eligible"] is True,p
    assert p["automatic_external_spend_eur"]==0,p

    output=td/"result.json"
    overlay=td/"overlay.json"
    built=run([
      "python3",repo/"dev-hub/bin/capability-build-loop.py",
      "--policy",repo/"dev-hub/config/capability-build-loop.v1.json",
      "--request",request,
      "--repo-root",repo,
      "--base-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--workspace",work,
      "build-pilot",
      "--runtime-root",runtime,
      "--output",output,
      "--overlay",overlay,
      "--apply"
    ])
    result=load(output)
    assert result["status"]=="PASS",result
    assert result["adapter_status"]=="ENABLED",result
    assert result["same_project_resume_allowed"] is True,result
    assert result["durable_adoption"]=="PENDING_PROJECT_SUCCESS",result
    assert result["network_access"] is False,result
    assert result["credentials_required"] is False,result
    assert result["production_capable"] is False,result
    assert result["automatic_external_spend_eur"]==0,result

    generated=Path(result["generated_source"])
    source=generated.read_text(encoding="utf-8")
    for forbidden in ["subprocess","socket","urllib","requests","os.system","eval(","exec("]:
        assert forbidden not in source,(forbidden,source)

    registry=load(Path(result["artifacts"]["registry"]))
    adapter=registry["adapters"]["v641-generated-read-adapter"]
    provider=registry["providers"]["v641-generated-read-provider"]
    assert adapter["status"]=="ENABLED",adapter
    assert adapter["supports"]==["read"],adapter
    assert provider["execution"]=="vps",provider
    assert provider["adapter"]=="v641-generated-read-adapter",provider

    ov=load(overlay)["capabilities"]["v641-generated-read"]
    assert ov["providers"][0]["status"]=="PILOT",ov
    assert ov["selected_adapter"]=="v641-generated-read-adapter",ov

    assert "CHACHA_DEV_V641_SAFE_ADAPTER_BUILD=PASS" in built.stdout
    assert "CHACHA_DEV_V641_CONTRACT_OK=PASS" in built.stdout
    assert "CHACHA_DEV_V641_SANDBOX_PILOT=PASS" in built.stdout
    assert "CHACHA_DEV_V641_REPEATABLE_RUNS=3" in built.stdout
    assert "CHACHA_DEV_V641_SANDBOX_ENABLED=PASS" in built.stdout

# Explicit-apply guard.
with tempfile.TemporaryDirectory(prefix="v641-noapply-") as td:
    td=Path(td); repo=td/"repo"; shutil.copytree(ROOT/"dev-hub",repo/"dev-hub")
    req={
      "schema":"chacha.dev/capability-build-request/v1",
      "project_id":"v641-noapply",
      "capability":"v641-noapply-read",
      "provider_id":"v641-noapply-provider",
      "adapter_id":"v641-noapply-adapter",
      "profile":"structured-read-v1","execution":"vps","supports":["read"],
      "network_access":False,"credentials_required":False,"production_capable":False,
      "automatic_external_spend_eur":0,
      "technology_watch":{"consulted":True},
      "architecture_council":{"decision":"APPROVED","decision_id":"v641-noapply-council"}
    }
    request=td/"request.json";save(request,req)
    p=subprocess.run([
      "python3",repo/"dev-hub/bin/capability-build-loop.py",
      "--policy",repo/"dev-hub/config/capability-build-loop.v1.json",
      "--request",request,"--repo-root",repo,
      "--base-registry",repo/"dev-hub/config/provider-adapters.v1.json",
      "--workspace",td/"work","build-pilot",
      "--runtime-root",td/"runtime","--output",td/"out.json","--overlay",td/"ov.json"
    ],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert p.returncode==2,p
    assert "EXPLICIT_APPLY_FLAG_REQUIRED" in p.stdout,p.stdout

# Unsafe build classes fail closed.
unsafe_cases=[
 ("network",{"network_access":True},"NETWORK_ACCESS_FORBIDDEN"),
 ("credentials",{"credentials_required":True},"CREDENTIALS_FORBIDDEN"),
 ("production",{"production_capable":True},"PRODUCTION_CAPABILITY_FORBIDDEN"),
 ("spend",{"automatic_external_spend_eur":1},"NONZERO_EXTERNAL_SPEND"),
 ("supports",{"supports":["workspace-write"]},"SUPPORTS_OUTSIDE_PROFILE"),
 ("council",{"architecture_council":{"decision":"REVISE","decision_id":"x"}},"ARCHITECTURE_COUNCIL_APPROVAL_REQUIRED"),
 ("techwatch",{"technology_watch":{"consulted":False}},"TECHNOLOGY_WATCH_REQUIRED"),
]
for name,patch,blocker in unsafe_cases:
    with tempfile.TemporaryDirectory(prefix="v641-unsafe-") as td:
        td=Path(td); req={
          "schema":"chacha.dev/capability-build-request/v1",
          "project_id":"v641-unsafe-"+name,
          "capability":"v641-unsafe-"+name,
          "provider_id":"v641-provider-"+name,
          "adapter_id":"v641-adapter-"+name,
          "profile":"structured-read-v1","execution":"vps","supports":["read"],
          "network_access":False,"credentials_required":False,"production_capable":False,
          "automatic_external_spend_eur":0,
          "technology_watch":{"consulted":True},
          "architecture_council":{"decision":"APPROVED","decision_id":"v641-"+name}
        }
        req.update(patch); request=td/"request.json";save(request,req)
        p=subprocess.run([
          "python3",BIN/"capability-build-loop.py",
          "--policy",CFG/"capability-build-loop.v1.json",
          "--request",request,"--repo-root",ROOT,
          "--base-registry",CFG/"provider-adapters.v1.json",
          "--workspace",td/"work","plan"
        ],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert p.returncode==2,(name,p.stdout,p.stderr)
        plan=json.loads(p.stdout)
        assert plan["status"]=="BUILD_SPECIALIST_REQUIRED",(name,plan)
        assert blocker in plan["blockers"],(name,plan)


# Governed compiler: only an explicit safe build profile may cross BUILD_REQUIRED.
with tempfile.TemporaryDirectory(prefix="v641-compiler-") as td:
    td=Path(td)
    closure={
      "schema":"chacha.dev/capability-foundry-closure-plan/v1",
      "project_id":"v641-compiler-project",
      "plans":[
        {"capability":"v641-compiler-safe","state":"BUILD_REQUIRED","evaluated_candidates":[
          {"candidate":{
            "provider_id":"v641-compiler-provider",
            "adapter_id":"v641-compiler-adapter",
            "build_profile":"structured-read-v1","execution":"vps","supports":["read"],
            "network_access":False,"credentials_required":False,"production_capable":False,
            "external_spend_eur":0
          }}
        ]},
        {"capability":"v641-compiler-unsafe","state":"BUILD_REQUIRED","evaluated_candidates":[
          {"candidate":{
            "provider_id":"v641-unsafe-provider",
            "execution":"vps","supports":["read"],
            "network_access":False,"credentials_required":False,"production_capable":False,
            "external_spend_eur":0
          }}
        ]}
      ]
    }
    foundry={
      "schema":"chacha.dev/capability-foundry-plan/v1",
      "project_id":"v641-compiler-project",
      "plans":[
        {"capability":"v641-compiler-safe","technology_watch":{"consulted":True,"snapshot_freshness":"FRESH","source_snapshot_digest":"sha256:test"}},
        {"capability":"v641-compiler-unsafe","technology_watch":{"consulted":True,"snapshot_freshness":"FRESH","source_snapshot_digest":"sha256:test"}}
      ]
    }
    council={"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True,"decisions":[]}
    save(td/"closure.json",closure); save(td/"foundry.json",foundry); save(td/"council.json",council)
    run([
      "python3",BIN/"capability-build-request-compiler.py",
      "--closure",td/"closure.json","--foundry-plan",td/"foundry.json",
      "--architecture-council",td/"council.json","--output",td/"batch.json"
    ])
    batch=load(td/"batch.json")
    assert batch["buildable_count"]==1,batch
    assert batch["unresolved_count"]==1,batch
    req=batch["requests"][0]
    assert req["capability"]=="v641-compiler-safe",req
    assert req["profile"]=="structured-read-v1",req
    assert req["architecture_council"]["decision"]=="APPROVED",req
    assert batch["unresolved"][0]["reason"]=="BUILD_SPECIALIST_REQUIRED",batch


# Capability Foundry may carry an explicit contract build hint, but must never
# infer the build profile/provider from a capability name.
foundry_src=(BIN/"capability-foundry.py").read_text(encoding="utf-8")
assert 'build_profile=str(gap.get("build_profile") or "").strip()' in foundry_src
assert 'build_provider=str(gap.get("provider_id") or "").strip()' in foundry_src
assert 'if build_profile and build_provider:' in foundry_src
assert '"evidence":"functional-contract-build-hint-reviewed-by-technology-watch"' in foundry_src
assert '"technology_candidates":technology_candidates' in foundry_src
assert 'build_profile=slug(' not in foundry_src
assert 'build_provider=slug(' not in foundry_src

# Central orchestrator integration invariants.
orch=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"capability-build-request-compiler.py"' in orch
assert '"capability-build-loop.py"' in orch
assert 'if capability_build_required_count:' in orch
assert 'shutil.copytree(root/"dev-hub",build_repo/"dev-hub")' in orch
assert '"--architecture-council",architecture_council' in orch
assert '"--repo-root",build_repo' in orch
assert '"build-pilot"' in orch and '"--apply"' in orch
assert 'active_provider_adapters=current_provider_registry' in orch
assert 'active_capabilities=current_capability_registry' in orch
assert 'capability_build_required_count=capability_build_specialist_required_count' in orch
assert '"capability_build_durable_adoption_before_project_success":False' in orch
assert any(v in orch for v in ['"version":"6.41.0"','"version":"6.42.0"'])
assert orch.index('architecture_council_v=load(architecture_council)') < orch.index('capability_build_batch=out/"capability-build-request-batch.json"')
assert orch.index('capability_build_batch=out/"capability-build-request-batch.json"') < orch.index('effective_branch_topology=out/"branch-topology-effective.json"')

print("CHACHA_DEV_V641_BUILD_REQUIRED_TO_SAFE_ADAPTER=PASS")
print("CHACHA_DEV_V641_OFFICIAL_PROVISIONING_CHAIN=PASS")
print("CHACHA_DEV_V641_OFFICIAL_PROMOTION_CHAIN=PASS")
print("CHACHA_DEV_V641_THREE_RUN_ENABLEMENT=PASS")
print("CHACHA_DEV_V641_SAME_PROJECT_RESUME_READY=PASS")
print("CHACHA_DEV_V641_DURABLE_ADOPTION_BEFORE_PROJECT_SUCCESS=NO")
print("CHACHA_DEV_V641_UNSAFE_BUILD_CLASSES_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V641_GOVERNED_BUILD_REQUEST_COMPILER=PASS")
print("CHACHA_DEV_V641_ORCHESTRATOR_POST_COUNCIL_BUILD=PASS")
print("CHACHA_DEV_V641_PROJECT_LOCAL_BUILD_REPO=PASS")
print("CHACHA_DEV_V641_ACTIVE_PROVIDER_REGISTRY_PROPAGATED=PASS")
print("CHACHA_DEV_V641_UNDECLARED_BUILD_PROFILE_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V641_EXPLICIT_BUILD_HINT_PROPAGATION=PASS")
print("CHACHA_DEV_V641_BUILD_PROFILE_INFERENCE=NO")
print("CHACHA_DEV_V641_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
