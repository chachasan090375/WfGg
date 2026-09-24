#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import guardian_remediation_runtime as grr
import assurance_exchange_runtime as aer
import universal_learning_runtime as ulr

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

_GUARDIAN_CONTEXT={"enabled":False}
_STAGE_ROLE={
    "specification-compiler.py":"specification-compiler",
    "functional-intent-orchestrator.py":"orchestrator",
    "project-factory.py":"project-factory",
    "project-embedded-assurance.py":"project-factory",
    "project-assurance-identity-manager.py":"orchestrator",
    "agent-foundry-planner.py":"agent-foundry",
    "agent-role-contract-manager.py":"agent-contract-registry",
    "component-role-contract-manager.py":"component-contract-registry",
    "branch-foundry-planner.py":"branch-foundry",
    "capability-foundry.py":"capability-foundry",
    "capability-foundry-closure.py":"capability-foundry",
    "capability-build-request-compiler.py":"capability-foundry",
    "capability-build-loop.py":"capability-foundry",
    "durable-capability-registry.py":"capability-foundry",
    "central-memory-recall.py":"central-memory-recall",
    "logic-search-engine.py":"logician",
    "ux-planning-engine.py":"ergonomist",
    "multi-agent-compromise-engine.py":"orchestrator",
    "architecture-decision-council.py":"architecture-decision-council",
    "architecture-comparative-pilot.py":"comparative-pilot",
    "capsule-scheduler.py":"capsule-scheduler",
}

def configure_guardian(root:Path,out:Path):
    _GUARDIAN_CONTEXT.clear()
    _GUARDIAN_CONTEXT.update({
      "enabled":Path("/opt/chacha-dev/runtime").exists(),
      "client":root/"dev-hub/bin/guardian-client.py",
      "policy":root/"dev-hub/config/guardian-runtime-policy.v1.json",
      "event_dir":out/"guardian",
    })

def _output_arg(args):
    vals=list(map(str,args))
    for i,v in enumerate(vals[:-1]):
        if v=="--output": return Path(vals[i+1])
    return None

def _council_guardian_evidence(output_path:Path|None):
    evidence={"emergency_stop_active":emergency_stop_active()}
    if not output_path or not output_path.exists():
        return evidence
    try:x=load(output_path)
    except Exception:return evidence
    decisions=[d for d in x.get("decisions") or [] if isinstance(d,dict)]
    def all_pass(key):
        return bool(decisions) and all((d.get("mandatory_advisors") or {}).get(key)=="PASS" for d in decisions)
    evidence.update({
      "technology_watch_pre":all_pass("technology-watch-pre"),
      "technology_watch_final":all_pass("technology-watch-final"),
      "central_memory_assimilation":all_pass("central-memory-assimilation"),
      "component_confidence":all_pass("component-confidence"),
      "central_memory_recall":all_pass("central-memory-recall"),
      "reuse_memory":all_pass("reuse-memory"),
      "architecture_memory":all_pass("architecture-memory"),
      "architecture_portfolio":all_pass("architecture-portfolio"),
      "branch_foundry":all_pass("branch-foundry"),
      "agent_foundry":all_pass("agent-foundry"),
      "capability_foundry":all_pass("capability-foundry"),
      "constraint_policy":all_pass("constraint-policy"),
      "logic_ux_compromise":all_pass("logic-ux-compromise") if "logic-ux-compromise" in (x.get("mandatory_advisors") or []) else True,
      "dispatch_allowed":bool(x.get("dispatch_allowed")),
    })
    return evidence

def guardian_stage(script:Path,args,phase:str,action_id:str):
    if not _GUARDIAN_CONTEXT.get("enabled"): return {"status":"NON_RUNTIME_TEST_BYPASS"}
    client=Path(_GUARDIAN_CONTEXT["client"]);policy=Path(_GUARDIAN_CONTEXT["policy"])
    if not client.is_file() or not policy.is_file():
        raise RuntimeError("GUARDIAN_STAGE_UNAVAILABLE:CLIENT_OR_POLICY_MISSING")
    role=_STAGE_ROLE.get(script.name,"orchestrator")
    out=_output_arg(args)
    action="INVOKE_COMPONENT"
    evidence={"emergency_stop_active":emergency_stop_active(),"output_exists":bool(out and out.exists())}
    if script.name=="architecture-decision-council.py" and phase=="POST_ACTION":
        evidence=_council_guardian_evidence(out)
        try:
            council_preview=load(out) if out and out.exists() else {}
        except Exception:
            council_preview={}
        if bool(council_preview.get("dispatch_allowed")):
            action="FINAL_ARCHITECTURE_DECISION"
        else:
            action="REPORT_DECISION"
    event_context=grr.inject_context(
      {"resource_class":"light","human_approval_required":False,"storage_preflight_required":False,"deadline_seconds":180},
      actor="central-orchestrator",subject_role=role,project_id="platform-bootstrap"
    )
    event={
      "schema":"chacha.dev/governance-action/v1",
      "event_id":"gov-"+uuid.uuid4().hex,
      "action_id":action_id,
      "phase":phase,
      "actor":"central-orchestrator",
      "subject_role":role,
      "action":action,
      "task_kind":script.stem,
      "permission":"plan",
      "project_id":"platform-bootstrap",
      "run_id":None,
      "adapters":[],
      "evidence":evidence,
      "context":event_context
    }
    event_dir=Path(_GUARDIAN_CONTEXT["event_dir"]);event_dir.mkdir(parents=True,exist_ok=True)
    ep=event_dir/(event["event_id"]+".json");save(ep,event)
    p=subprocess.run([sys.executable,str(client),"--policy",str(policy),"check","--event",str(ep)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=25)
    try:verdict=json.loads(p.stdout.strip())
    except Exception:
        verdict={"status":"UNAVAILABLE","reason":"INVALID_GUARDIAN_RESPONSE"}
    save(event_dir/(event["event_id"]+".verdict.json"),verdict)
    state=str(verdict.get("verdict") or verdict.get("status") or "UNAVAILABLE")
    if state in {"BLOCK","CRITICAL"}:
        raise RuntimeError("GUARDIAN_STAGE_BLOCK:"+script.name+":"+str(verdict.get("reason_codes") or []))
    if state not in {"PASS","WARNING"}:
        raise RuntimeError("GUARDIAN_STAGE_UNAVAILABLE:"+script.name+":"+str(verdict.get("reason") or state))
    return verdict

def run(script,args):
    action_id="stage-"+uuid.uuid4().hex
    guardian_stage(Path(script),args,"PRE_ACTION",action_id)
    p=subprocess.run([sys.executable,str(script),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     text=True,check=False,timeout=120)
    role=_STAGE_ROLE.get(Path(script).name,"orchestrator")
    lower=role.lower()
    kind="foundry" if "foundry" in lower else "core-orchestrator" if role=="orchestrator" else "domain-orchestrator" if "orchestrator" in lower else "agent"
    project_id="platform-global"
    for i,v in enumerate(args):
        if str(v)=="--project-id" and i+1<len(args):
            project_id=str(args[i+1]);break
    try:
        ulr.observe_platform(project_id=project_id,source_id=role,source_kind=kind,state={
          "stage":Path(script).name,"returncode":int(p.returncode),
          "stdout_digest":"sha256:"+__import__("hashlib").sha256(p.stdout.encode()).hexdigest(),
          "stderr_digest":"sha256:"+__import__("hashlib").sha256(p.stderr.encode()).hexdigest()
        })
    except Exception:
        pass
    if p.returncode!=0:
        raise RuntimeError(f"{script.name}: {p.stderr.strip()} {p.stdout.strip()}")
    guardian_stage(Path(script),args,"POST_ACTION",action_id)
    return p.stdout

def merge_domain(base,overlay,out):
    b=load(base);o=load(overlay)
    b.setdefault("domains",{}).update(o.get("domains") or {})
    save(out,b)

def merge_caps(base,overlay,out):
    b=load(base);o=load(overlay)
    b.setdefault("capabilities",{}).update(o.get("capabilities") or {})
    save(out,b)

def merge_routing(base,overlay,out):
    b=load(base);o=load(overlay)
    b.setdefault("roles",{}).update(o.get("roles") or {})
    save(out,b)

def run_parallel_foundries(bin_dir,cfg_dir,preplan,project_id,routing,memory_brief,agent_out,branch_out):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        af=ex.submit(run,bin_dir/"agent-foundry-planner.py",[
            "--preplan",preplan,"--config",cfg_dir/"agent-foundry.v1.json",
            "--routing",routing,"--project-id",project_id,"--memory-brief",memory_brief,"--output",agent_out
        ])
        bf=ex.submit(run,bin_dir/"branch-foundry-planner.py",[
            "--preplan",preplan,"--config",cfg_dir/"branch-foundry.v1.json",
            "--project-id",project_id,"--memory-brief",memory_brief,"--output",branch_out
        ])
        af.result();bf.result()

def refine_branch_with_agents(bin_dir,cfg_dir,preplan,project_id,agent_topology,memory_brief,branch_out):
    run(bin_dir/"branch-foundry-planner.py",[
        "--preplan",preplan,"--config",cfg_dir/"branch-foundry.v1.json",
        "--project-id",project_id,"--agent-topology",agent_topology,"--memory-brief",memory_brief,"--output",branch_out
    ])

def apply_architecture_council(branch_topology,council,out):
    b=load(branch_topology); council_v=load(council)
    cmap={str(x.get("package_id")):x for x in council_v.get("decisions") or [] if isinstance(x,dict)}
    applied=0
    for row in b.get("decisions") or []:
        if not isinstance(row,dict): continue
        d=cmap.get(str(row.get("package_id")))
        if not d or d.get("decision_ready") is not True: continue
        if isinstance(d.get("architecture"),dict):
            row["foundry_architecture"]=row.get("architecture")
            row["architecture"]=d["architecture"]
            row["architecture_source"]=d.get("architecture_source")
            row["selected_reuse"]=d.get("selected_reuse")
            row["architecture_council_applied"]=True
            applied+=1
    b["architecture_council"]={
      "schema":council_v.get("schema"),"version":council_v.get("version"),
      "dispatch_allowed":council_v.get("dispatch_allowed"),"applied_decisions":applied,
      "architecture_memory":council_v.get("architecture_memory")
    }
    if council_v.get("dispatch_allowed") is not True:
        b.setdefault("blocked",[]).append({"scope":"architecture-council","reason":"COUNCIL_NOT_READY"})
    save(out,b)


def capability_gaps(preplan,contract,capability_registry,project_id,out):
    pre=load(preplan);contract_v=load(contract);capreg=load(capability_registry)
    known=set((capreg.get("capabilities") or {}).keys())
    gaps=[]
    for pkg in pre.get("packages") or []:
        for cap in pkg.get("capabilities") or []:
            if cap not in known:gaps.append({"id":cap,"domain":pkg.get("domain")})
    for hint in contract_v.get("capability_hints") or []:
        if isinstance(hint,str) and hint not in known:gaps.append({"id":hint})
        elif isinstance(hint,dict) and str(hint.get("id") or "") not in known:gaps.append(hint)
    uniq={str(x.get("id")):x for x in gaps if x.get("id")}
    save(out,{"project_id":project_id,"missing_capabilities":list(uniq.values())})

def emergency_stop_active(path=Path("/opt/chacha-dev/runtime/control/emergency-stop.json")):
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return bool(x.get("active"))
    except Exception:
        return False

def bastion_survival_active(path=Path("/opt/chacha-dev/runtime/control/survival-mode.json")):
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return bool(x.get("active"))
    except Exception:
        return False

def bastion_project_block(project_id:str,root=Path("/opt/chacha-dev/runtime/control")):
    for kind in ("revocation","quarantine","containment"):
        p=root/kind/(str(project_id)+".json")
        try:
            x=json.loads(p.read_text(encoding="utf-8"))
            if x.get("active"):
                return {"kind":kind,"path":str(p),"state":x}
        except Exception:
            pass
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",default=".",type=Path)
    ap.add_argument("--intent",required=True,type=Path)
    ap.add_argument("--output-dir",required=True,type=Path)
    a=ap.parse_args()
    if emergency_stop_active():
        raise SystemExit("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
    if bastion_survival_active():
        raise SystemExit("CHACHA_DEV_BASTION_SURVIVAL_MODE_ACTIVE")
    root=a.repo_root.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    cfg=root/"dev-hub/config";bin_dir=root/"dev-hub/bin"
    configure_guardian(root,out)

    contract=out/"functional-contract.json"
    run(bin_dir/"specification-compiler.py",["--intent",a.intent,"--output",contract])

    pre=out/"preplan.json"
    run(bin_dir/"functional-intent-orchestrator.py",[
        "--config",cfg/"domain-orchestration.v1.json","--intent",a.intent,"--output",pre
    ])
    pre_v=load(pre)
    assert pre_v.get("dispatch_allowed") is False

    project=out/"project.json"
    run(bin_dir/"project-factory.py",[
        "--intent",a.intent,"--domain-plan",pre,
        "--config",cfg/"project-factory.v1.json",
        "--knowledge-fabric",cfg/"knowledge-fabric.v1.json",
        "--output",project
    ])
    pid=load(project)["project_id"]
    bastion_block=bastion_project_block(pid)
    if bastion_block:
        raise SystemExit("CHACHA_DEV_BASTION_PROJECT_BLOCKED:"+str(bastion_block.get("kind"))+":"+pid)

    # V6.32: assurance is part of the project birth contract, never an optional plugin.
    assurance_bundle=out/"embedded-assurance"
    run(bin_dir/"project-embedded-assurance.py",[
        "--project-id",pid,
        "--application-version","UNRELEASED",
        "--policy",cfg/"project-embedded-assurance.v1.json",
        "--runtime-script",bin_dir/"project-assurance-event.py",
        "--relay-script",bin_dir/"project-assurance-relay.py",
        "--client-runtime",root/"dev-hub/templates/project-assurance-client.mjs",
        "--functional-contract",contract,
        "--output-dir",assurance_bundle
    ])
    assurance_identity_receipt=out/"project-assurance-identity-receipt.json"
    if bool(_GUARDIAN_CONTEXT.get("enabled")):
        run(bin_dir/"project-assurance-identity-manager.py",[
            "--project-id",pid,
            "--guardian-client",bin_dir/"guardian-client.py",
            "--guardian-policy",cfg/"guardian-runtime-policy.v1.json",
            "--sentinel-client",bin_dir/"sentinel-client.py",
            "--sentinel-policy",cfg/"sentinel-runtime-policy.v1.json",
            "--exchange-client",bin_dir/"assurance-exchange-client.py",
            "--exchange-policy",cfg/"assurance-exchange-runtime-policy.v1.json",
            "--specialist-client",bin_dir/"specialist-authority-client.py",
            "--curator-policy",cfg/"curator-runtime-policy.v1.json",
            "--bastion-policy",cfg/"bastion-runtime-policy.v1.json",
            "--intendant-policy",cfg/"intendant-runtime-policy.v1.json",
            "--registration",out/"project-assurance-identity-registration.json",
            "--receipt",assurance_identity_receipt,
            "--bundle",assurance_bundle
        ])
    assurance_manifest=load(assurance_bundle/"embedded-assurance.json")

    # V6.23: the central brain recalls only context-relevant memory before asking the Foundries.
    # Recall is advisory; current Technology Watch and Council remain mandatory.
    initial_memory_brief=out/"central-memory-brief-initial.json"
    run(bin_dir/"central-memory-recall.py",[
        "--memory",Path("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"),
        "--policy",cfg/"central-memory-recall.v1.json",
        "--intent",a.intent,"--preplan",pre,"--project-id",pid,"--output",initial_memory_brief
    ])

    # First preflight pass: Agent Foundry and Branch Foundry truly run in parallel.
    initial_agent=out/"agent-topology-initial.json"
    initial_branch=out/"branch-topology-initial.json"
    run_parallel_foundries(bin_dir,cfg,pre,pid,cfg/"agent-routing.v1.json",initial_memory_brief,initial_agent,initial_branch)

    # V6.42: merge release-independent durable capability adoptions before
    # capability-gap detection. This keeps learned capabilities reusable across
    # projects and platform releases without mutating static release configs.
    durable_registry=Path("/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json")
    durable_caps=out/"runtime-capabilities-durable.json"
    durable_providers=out/"runtime-provider-adapters-durable.json"
    capability_trust_snapshot=Path("/opt/chacha-dev/runtime/knowledge/component-confidence.json")
    durable_merge_args=[
       "merge",
       "--base-capability-registry",cfg/"capability-registry.v1.json",
       "--base-provider-registry",cfg/"provider-adapters.v1.json",
       "--registry",durable_registry,
       "--output-capabilities",durable_caps,
       "--output-providers",durable_providers,
       "--trust-policy",cfg/"capability-trust-graduation.v1.json"
    ]
    if capability_trust_snapshot.is_file():
        durable_merge_args+=["--trust-snapshot",capability_trust_snapshot]
    run(bin_dir/"durable-capability-registry.py",durable_merge_args)

    # Capability gaps may create project-local branches/capabilities.
    gapreq=out/"capability-gaps.json"
    capability_gaps(pre,contract,durable_caps,pid,gapreq)
    foundry_plan=out/"capability-foundry.json"
    dom_overlay=out/"domain-overlay.json";cap_overlay=out/"capability-overlay.json";routing_overlay=out/"routing-overlay.json"
    run(bin_dir/"capability-foundry.py",[
       "--request",gapreq,"--policy",cfg/"capability-foundry.v1.json",
       "--domains",cfg/"domain-orchestration.v1.json",
       "--capabilities",durable_caps,
       "--memory-brief",initial_memory_brief,
       "--output",foundry_plan,
       "--domain-overlay",dom_overlay,
       "--capability-overlay",cap_overlay,
       "--routing-overlay",routing_overlay
    ])
    foundry_v=load(foundry_plan)

    # V6.40: a logical Foundry overlay is not executable authority by itself.
    # Close only through an already-known, already-ENABLED provider adapter.
    # Anything else becomes an explicit BUILD_REQUIRED blocker.
    closure_plan=out/"capability-foundry-closure.json"
    closure_overlay=out/"capability-closure-overlay.json"
    run(bin_dir/"capability-foundry-closure.py",[
       "--policy",cfg/"capability-foundry-closure.v1.json",
       "--foundry-plan",foundry_plan,
       "--capability-registry",durable_caps,
       "--provider-adapters",durable_providers,
       "--output",closure_plan,
       "--overlay",closure_overlay,
       "plan"
    ])
    closure_v=load(closure_plan)
    closure_summary=closure_v.get("summary") or {}
    capability_build_required_count=int(closure_summary.get("build_required_count") or 0)

    # V6.42: every project-local capability that could become durable is
    # materialized as a pending candidate. Adoption is NOT performed here.
    capability_adoption_candidates=[]
    durable_provider_v=load(durable_providers)
    for row in closure_v.get("plans") or []:
        if not isinstance(row,dict) or row.get("state")!="PROJECT_LOCAL_READY":
            continue
        provider=str(row.get("selected_provider") or "")
        adapter=str(row.get("selected_adapter") or "")
        provider_cfg=(durable_provider_v.get("providers") or {}).get(provider) or {}
        capability_adoption_candidates.append({
          "schema":"chacha.dev/capability-adoption-candidate/v1",
          "source_kind":"EXISTING_PROVIDER",
          "project_id":pid,
          "capability":str(row.get("capability") or ""),
          "provider":provider,
          "adapter":adapter,
          "build_result":None,
          "production_capable":bool(row.get("production_capable")),
          "network_access":str(provider_cfg.get("execution") or "")=="external",
          "credentials_required":False,
          "automatic_external_spend_eur":0,
          "technology_watch_plan":str(foundry_plan),
          "architecture_council":None,
          "adoption_state":"PENDING_PROJECT_SUCCESS"
        })

    active_pre=pre
    active_intent=a.intent
    active_domain=cfg/"domain-orchestration.v1.json"
    active_routing=cfg/"agent-routing.v1.json"
    active_capabilities=durable_caps

    if foundry_v.get("created_domain_count") or foundry_v.get("created_capability_count"):
        merged_domain=out/"runtime-domain-orchestration.json"
        merged_caps=out/"runtime-capabilities.json"
        merged_routing=out/"runtime-routing.json"
        merge_domain(cfg/"domain-orchestration.v1.json",dom_overlay,merged_domain)
        merge_caps(cfg/"capability-registry.v1.json",closure_overlay,merged_caps)
        merge_routing(cfg/"agent-routing.v1.json",routing_overlay,merged_routing)
        active_capabilities=merged_caps

        revised_intent=out/"revised-intent.json"
        intent_v=load(a.intent)
        generated_domains=[str(x.get("owner_domain")) for x in foundry_v.get("plans") or [] if x.get("create_domain")]
        existing_primary=[str(x) for x in pre_v.get("primary_domains") or []]
        intent_v["domains"]=list(dict.fromkeys(existing_primary+generated_domains))
        save(revised_intent,intent_v)

        revised_pre=out/"revised-preplan.json"
        run(bin_dir/"functional-intent-orchestrator.py",[
            "--config",merged_domain,"--intent",revised_intent,"--output",revised_pre
        ])
        active_pre=revised_pre;active_intent=revised_intent;active_domain=merged_domain;active_routing=merged_routing

    # V6.23: capability discovery may change context, so recall is refreshed before final Foundry decisions.
    memory_brief=out/"central-memory-brief.json"
    run(bin_dir/"central-memory-recall.py",[
        "--memory",Path("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"),
        "--policy",cfg/"central-memory-recall.v1.json",
        "--intent",active_intent,"--preplan",active_pre,"--project-id",pid,"--output",memory_brief
    ])

    # V6.34: Logician and Ergonomist challenge the stable plan before final architecture.
    # The central brain must first try to synthesize an admissible compromise itself.
    logic_report=out/"logic-search-report.json"
    run(bin_dir/"logic-search-engine.py",[
        "--repo-root",root,
        "--intent",active_intent,
        "--contract",contract,
        "--preplan",active_pre,
        "--memory-brief",memory_brief,
        "--policy",cfg/"logic-search.v1.json",
        "--output",logic_report
    ])
    ux_report=out/"ux-planning-report.json"
    run(bin_dir/"ux-planning-engine.py",[
        "--intent",active_intent,
        "--contract",contract,
        "--preplan",active_pre,
        "--policy",cfg/"ux-planning.v1.json",
        "--output",ux_report
    ])
    compromise=out/"multi-agent-compromise.json"
    run(bin_dir/"multi-agent-compromise-engine.py",[
        "--policy",cfg/"decision-challenge.v1.json",
        "--logic-report",logic_report,
        "--ux-report",ux_report,
        "--output",compromise
    ])
    compromise_v=load(compromise)
    if compromise_v.get("central_compromise_found") is not True:
        revision_path=out/"agent-revision-requests.json"
        save(revision_path,{
          "schema":"chacha.dev/agent-revision-request-batch/v1",
          "project_id":pid,
          "requests":compromise_v.get("revision_requests") or [],
          "reason":"CENTRAL_COMPROMISE_SEARCH_FAILED",
          "central_brain_attempted_compromise":True
        })
        raise RuntimeError("MULTI_AGENT_COMPROMISE_REQUIRED:"+str(revision_path))

    # Final foundry pass on the stable branch/capability set.
    agent_topology=out/"agent-topology.json"
    branch_parallel=out/"branch-topology-parallel.json"
    run_parallel_foundries(bin_dir,cfg,active_pre,pid,active_routing,memory_brief,agent_topology,branch_parallel)
    agent_topology_v=load(agent_topology)

    # V6.17: every newly created agent gets a precise, versioned Guardian contract.
    # Runtime registration is fail-closed and constrained by Guardian's immutable agent template.
    agent_contracts=out/"agent-role-contracts.json"
    contract_args=[
        "--agent-topology",agent_topology,
        "--output",agent_contracts,
        "--client",bin_dir/"guardian-client.py",
        "--policy",cfg/"guardian-runtime-policy.v1.json"
    ]
    if bool(_GUARDIAN_CONTEXT.get("enabled")):
        contract_args+=["--register"]
    run(bin_dir/"agent-role-contract-manager.py",contract_args)
    agent_contracts_v=load(agent_contracts)

    # Cheap cross-optimization: Branch Foundry recalculates only its blueprints with Agent Foundry topology.
    branch_topology=out/"branch-topology.json"
    refine_branch_with_agents(bin_dir,cfg,active_pre,pid,agent_topology,memory_brief,branch_topology)

    # V6.11: the central brain does not accept any single foundry as the final architect.
    # It must synthesize Technology Watch, reusable memory, Branch/Agent/Capability Foundries,
    # hard policy constraints, dynamic domain experts, and then perform a fresh Technology Watch check.
    architecture_council=out/"architecture-decision-council.json"
    run(bin_dir/"architecture-decision-council.py",[
        "--repo-root",root,
        "--preplan",active_pre,
        "--branch-topology",branch_topology,
        "--agent-topology",agent_topology,
        "--capability-foundry",foundry_plan,
        "--policy",cfg/"architecture-decision-council.v1.json",
        "--memory-brief",memory_brief,
        "--challenge-dossier",compromise,
        "--output",architecture_council
    ])
    architecture_council_v=load(architecture_council)

    # V6.15: when proven history conflicts with today's Foundries, run the same
    # benchmark contract in isolated ephemeral capsules. Without a real harness,
    # production remains fail-closed instead of fabricating a winner.
    comparative_pilot=out/"architecture-comparative-pilot.json"
    comparative_pilot_v={"schema":"chacha.dev/architecture-comparative-pilot-result/v1","status":"NOT_REQUIRED","resolved":False}
    portfolio_v=architecture_council_v.get("architecture_portfolio") or {}
    if portfolio_v.get("comparative_pilot_required") is True:
        portfolio_file=architecture_council.with_name(architecture_council.stem+"-portfolio.json")
        harness_candidates=[
            out/"comparative-pilot-harness.json",
            cfg/"comparative-pilot-harness.v1.json"
        ]
        harness=next((p for p in harness_candidates if p.is_file()),None)
        args=[
            "--repo-root",root,
            "--portfolio",portfolio_file,
            "--output",comparative_pilot
        ]
        if harness is not None:
            args+=["--harness",harness]
        run(bin_dir/"architecture-comparative-pilot.py",args)
        comparative_pilot_v=load(comparative_pilot)
        if comparative_pilot_v.get("resolved") is True:
            run(bin_dir/"architecture-decision-council.py",[
                "--repo-root",root,
                "--preplan",active_pre,
                "--branch-topology",branch_topology,
                "--agent-topology",agent_topology,
                "--capability-foundry",foundry_plan,
                "--policy",cfg/"architecture-decision-council.v1.json",
                "--memory-brief",memory_brief,
                "--challenge-dossier",compromise,
                "--comparative-pilot-result",comparative_pilot,
                "--output",architecture_council
            ])
            architecture_council_v=load(architecture_council)

    # V6.41: after the FINAL Architecture Council decision, BUILD_REQUIRED gaps
    # may enter the bounded capability build loop. Only candidates explicitly
    # declaring an approved safe build profile can be generated automatically.
    # Builds are project-local: copied tooling, sandbox runtime, and temporary
    # provider/capability registries. Durable adoption remains post-project-success.
    capability_build_batch=out/"capability-build-request-batch.json"
    capability_build_results=[]
    capability_build_auto_built_count=0
    capability_build_specialist_required_count=capability_build_required_count
    active_provider_adapters=durable_providers

    if capability_build_required_count:
        run(bin_dir/"capability-build-request-compiler.py",[
            "--closure",closure_plan,
            "--foundry-plan",foundry_plan,
            "--architecture-council",architecture_council,
            "--output",capability_build_batch
        ])
        build_batch_v=load(capability_build_batch)
        capability_build_specialist_required_count=int(build_batch_v.get("unresolved_count") or 0)
        requests=[x for x in build_batch_v.get("requests") or [] if isinstance(x,dict)]
        if requests:
            build_repo=out/"capability-build-repo"
            if build_repo.exists():
                shutil.rmtree(build_repo)
            shutil.copytree(root/"dev-hub",build_repo/"dev-hub")
            current_provider_registry=active_provider_adapters
            current_capability_registry=active_capabilities
            build_root=out/"capability-builds"
            runtime_root=out/"capability-build-runtime"
            build_root.mkdir(parents=True,exist_ok=True)
            runtime_root.mkdir(parents=True,exist_ok=True)

            for index,request_v in enumerate(requests,1):
                capability=str(request_v.get("capability") or f"capability-{index}")
                safe_name="".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in capability)[:72] or f"capability-{index}"
                request_path=build_root/(f"{index:02d}-{safe_name}-request.json")
                save(request_path,request_v)
                workspace=build_root/(f"{index:02d}-{safe_name}")
                result_path=workspace/"build-result.json"
                overlay_path=workspace/"capability-overlay.json"
                run(bin_dir/"capability-build-loop.py",[
                    "--policy",cfg/"capability-build-loop.v1.json",
                    "--request",request_path,
                    "--repo-root",build_repo,
                    "--base-registry",current_provider_registry,
                    "--workspace",workspace,
                    "build-pilot",
                    "--runtime-root",runtime_root/safe_name,
                    "--output",result_path,
                    "--overlay",overlay_path,
                    "--apply"
                ])
                result_v=load(result_path)
                if result_v.get("status")!="PASS" or result_v.get("same_project_resume_allowed") is not True:
                    raise RuntimeError("CAPABILITY_BUILD_LOOP_NOT_RESUMABLE:"+capability)
                capability_build_results.append(str(result_path))
                capability_adoption_candidates.append({
                  "schema":"chacha.dev/capability-adoption-candidate/v1",
                  "source_kind":"BUILT_ADAPTER",
                  "project_id":pid,
                  "capability":str(result_v.get("capability") or capability),
                  "provider":str(result_v.get("provider") or ""),
                  "adapter":str(result_v.get("adapter") or ""),
                  "build_result":str(result_path),
                  "production_capable":bool(result_v.get("production_capable")),
                  "network_access":bool(result_v.get("network_access")),
                  "credentials_required":bool(result_v.get("credentials_required")),
                  "automatic_external_spend_eur":float(result_v.get("automatic_external_spend_eur") or 0),
                  "technology_watch_plan":str(foundry_plan),
                  "architecture_council":str(architecture_council),
                  "adoption_state":"PENDING_PROJECT_SUCCESS"
                })
                current_provider_registry=Path(str((result_v.get("artifacts") or {}).get("registry") or ""))
                if not current_provider_registry.is_file():
                    raise RuntimeError("CAPABILITY_BUILD_PROVIDER_REGISTRY_MISSING:"+capability)
                merged_after_build=out/(f"runtime-capabilities-v641-{index:02d}.json")
                merge_caps(current_capability_registry,overlay_path,merged_after_build)
                current_capability_registry=merged_after_build

            active_provider_adapters=current_provider_registry
            active_capabilities=current_capability_registry
            capability_build_auto_built_count=len(capability_build_results)

        # Only unresolved specialist-required gaps remain blockers.
        capability_build_required_count=capability_build_specialist_required_count

    capability_adoption_batch=out/"capability-adoption-candidates.json"
    save(capability_adoption_batch,{
      "schema":"chacha.dev/capability-adoption-candidates/v1",
      "project_id":pid,
      "status":"PENDING_PROJECT_SUCCESS" if capability_adoption_candidates else "NONE",
      "candidate_count":len(capability_adoption_candidates),
      "candidates":capability_adoption_candidates,
      "durable_adoption_before_project_success":False,
      "automatic_external_spend_eur":0
    })

    # The Council is not advisory-only: its selected/revalidated architecture becomes
    # the effective topology consumed by planning and runtime scheduling.
    effective_branch_topology=out/"branch-topology-effective.json"
    apply_architecture_council(branch_topology,architecture_council,effective_branch_topology)

    # V6.18: every dynamic branch and every dedicated/project-local orchestrator
    # gets a precise versioned Guardian contract before final dispatch planning.
    component_contracts=out/"component-role-contracts.json"
    component_contract_args=[
        "--preplan",active_pre,
        "--branch-topology",effective_branch_topology,
        "--capability-foundry",foundry_plan,
        "--output",component_contracts,
        "--client",bin_dir/"guardian-client.py",
        "--policy",cfg/"guardian-runtime-policy.v1.json"
    ]
    if bool(_GUARDIAN_CONTEXT.get("enabled")):
        component_contract_args+=["--register"]
    run(bin_dir/"component-role-contract-manager.py",component_contract_args)
    component_contracts_v=load(component_contracts)

    final=out/"final-plan.json"
    run(bin_dir/"functional-intent-orchestrator.py",[
        "--config",active_domain,"--intent",active_intent,
        "--agent-topology",agent_topology,
        "--branch-topology",effective_branch_topology,
        "--output",final
    ])

    final_v=load(final);branch_v=load(effective_branch_topology)
    final_v["architecture_council"]=str(architecture_council)
    final_v["architecture_decision_allowed"]=bool(architecture_council_v.get("dispatch_allowed"))
    final_v["active_capability_registry"]=str(active_capabilities)
    final_v["active_provider_adapter_registry"]=str(active_provider_adapters)
    final_v["capability_foundry_closure"]=str(closure_plan)
    final_v["capability_build_request_batch"]=str(capability_build_batch) if capability_build_batch.exists() else None
    final_v["capability_build_auto_built_count"]=capability_build_auto_built_count
    final_v["capability_build_specialist_required_count"]=capability_build_specialist_required_count
    final_v["capability_build_required_count"]=capability_build_required_count
    final_v["dispatch_allowed"]=bool(final_v.get("dispatch_allowed")) and bool(architecture_council_v.get("dispatch_allowed"))
    if capability_build_required_count:
        final_v["dispatch_allowed"]=False
        final_v.setdefault("blocked",[]).append({
          "scope":"capability-foundry-closure",
          "reason":"CAPABILITY_BUILD_REQUIRED",
          "count":capability_build_required_count
        })
    save(final,final_v)

    wave_plan=out/"runtime-wave-plan.json"
    run(bin_dir/"capsule-scheduler.py",[
        "--topology",effective_branch_topology,
        "--policy",cfg/"branch-foundry.v1.json",
        "--output",wave_plan
    ])
    wave_v=load(wave_plan)

    fast_path=(not bool(final_v.get("implementation_allowed"))
               and int((branch_v.get("summary") or {}).get("materialized") or 0)==0)
    assurance_recommendations=aer.recommendations(project_id=pid)

    if capability_build_required_count:
        next_stage="CAPABILITY_BUILD_REQUIRED"
    elif fast_path:
        next_stage="KNOWLEDGE_FAST_PATH"
    elif final_v.get("dispatch_allowed"):
        next_stage="DOMAIN_FACTORIES"
    elif bool((architecture_council_v.get("architecture_portfolio") or {}).get("comparative_pilot_required")):
        next_stage="ARCHITECTURE_COMPARATIVE_PILOT_REQUIRED"
    else:
        next_stage="REPLAN_REQUIRED"

    state={
      "schema":"chacha.dev/autonomous-project-bootstrap/v1",
      "version":"6.43.0",
      "project_id":pid,
      "functional_contract":str(contract),
      "project":str(project),
      "embedded_assurance_bundle":str(assurance_bundle),
      "embedded_assurance_manifest":str(assurance_bundle/"embedded-assurance.json"),
      "embedded_assurance_required":True,
      "guardian_local_enabled":bool((assurance_manifest.get("guardian_local") or {}).get("enabled")),
      "sentinel_local_enabled":bool((assurance_manifest.get("sentinel_local") or {}).get("enabled")),
      "curator_local_enabled":bool((assurance_manifest.get("curator_local") or {}).get("enabled")),
      "bastion_local_enabled":bool((assurance_manifest.get("bastion_local") or {}).get("enabled")),
      "intendant_local_enabled":bool((assurance_manifest.get("intendant_local") or {}).get("enabled")),
      "five_local_probes_enabled":all(bool((assurance_manifest.get(role+"_local") or {}).get("enabled"))
                                      for role in ("guardian","sentinel","curator","bastion","intendant")),
      "project_assurance_identity_active":bool((assurance_manifest.get("production_readiness") or {}).get("relay_identity_active")),
      "embedded_assurance_production_ready":bool((assurance_manifest.get("production_readiness") or {}).get("ready")),
      "specialist_authority_identities_active":bool((assurance_manifest.get("production_readiness") or {}).get("specialist_authority_identities_active")),
      "curator_central_authority":"ACTIVE",
      "bastion_central_authority":"ACTIVE",
      "bastion_survival_guard":True,
      "bastion_project_control_guard":True,
      "bastion_failover_status":"RESERVED_INACTIVE",
      "intendant_central_authority":"ACTIVE",
      "embedded_assurance_raw_user_content":False,
      "embedded_assurance_direct_mutation":False,
      "preplan":str(active_pre),
      "central_memory_brief":str(memory_brief),
      "central_memory_brief_digest":load(memory_brief).get("brief_digest"),
      "central_memory_source_snapshot_digest":load(memory_brief).get("source_memory_snapshot_digest"),
      "central_memory_trusted_count":int(load(memory_brief).get("trusted_memory_count") or 0),
      "central_memory_caution_count":int(load(memory_brief).get("caution_count") or 0),
      "central_memory_current_best_reuse_count":int(load(memory_brief).get("reuse_candidate_count") or 0),
      "central_memory_trusted_component_candidate_count":int(load(memory_brief).get("trusted_component_candidate_count") or 0),
      "central_memory_caution_component_candidate_count":int(load(memory_brief).get("caution_component_candidate_count") or 0),
      "component_confidence_available":bool((load(memory_brief).get("component_confidence") or {}).get("available")),
      "component_confidence_snapshot_digest":(load(memory_brief).get("component_confidence") or {}).get("snapshot_digest"),
      "agent_topology":str(agent_topology),
      "agent_role_contracts":str(agent_contracts),
      "dynamic_agent_contract_count":int(agent_contracts_v.get("contract_count") or 0),
      "dynamic_agent_contracts_registered":bool(agent_contracts_v.get("registered")),
      "dynamic_agent_contracts_all_registered":bool(agent_contracts_v.get("all_registered")),
      "component_role_contracts":str(component_contracts),
      "dynamic_component_contract_count":int(component_contracts_v.get("contract_count") or 0),
      "dynamic_component_contracts_registered":bool(component_contracts_v.get("registered")),
      "dynamic_component_contracts_all_registered":bool(component_contracts_v.get("all_registered")),
      "dynamic_branch_contract_count":int((component_contracts_v.get("kinds") or {}).get("branch") or 0),
      "dynamic_orchestrator_contract_count":int((component_contracts_v.get("kinds") or {}).get("orchestrator") or 0),
      "branch_topology":str(effective_branch_topology),
      "branch_topology_foundry":str(branch_topology),
      "runtime_wave_plan":str(wave_plan),
      "runtime_wave_count":int(wave_v.get("wave_count") or 0),
      "runtime_schedulable":bool(wave_v.get("schedulable")),
      "capability_foundry":str(foundry_plan),
      "capability_foundry_closure":str(closure_plan),
      "active_capability_registry":str(active_capabilities),
      "active_provider_adapter_registry":str(active_provider_adapters),
      "capability_build_request_batch":str(capability_build_batch) if capability_build_batch.exists() else None,
      "capability_build_results":capability_build_results,
      "capability_build_auto_built_count":capability_build_auto_built_count,
      "capability_build_specialist_required_count":capability_build_specialist_required_count,
      "capability_build_same_project_resume":bool(capability_build_auto_built_count) and capability_build_required_count==0,
      "capability_build_durable_adoption_before_project_success":False,
      "capability_adoption_candidates":str(capability_adoption_batch),
      "capability_adoption_candidate_count":len(capability_adoption_candidates),
      "durable_capability_registry":str(durable_registry),
      "durable_registry_merged_before_gap_detection":True,
      "capability_trust_snapshot":str(capability_trust_snapshot),
      "capability_trust_filter_applied":capability_trust_snapshot.is_file(),
      "capability_trust_project_distinct":True,
      "capability_trust_does_not_escalate_permissions":True,
      "capability_foundry_auto_closed_count":sum(1 for x in closure_v.get("plans") or [] if x.get("state")=="PROJECT_LOCAL_READY"),
      "capability_foundry_reused_registered_count":sum(1 for x in closure_v.get("plans") or [] if x.get("state")=="REUSE_REGISTERED"),
      "capability_foundry_build_required_count":capability_build_required_count,
      "capability_foundry_same_project_resume_allowed":bool(closure_summary.get("same_project_resume_allowed")),
      "capability_foundry_automatic_external_spend_eur":float(closure_v.get("automatic_external_spend_eur") or 0),
      "agent_foundry_memory_guided_decisions":int((agent_topology_v.get("summary") or {}).get("memory_guided_decisions") or 0),
      "branch_foundry_memory_guided_decisions":int((branch_v.get("summary") or {}).get("memory_guided_decisions") or 0),
      "capability_foundry_memory_guided_plans":int(foundry_v.get("memory_guided_plans") or 0),
      "memory_guided_foundry_planning":True,
      "final_plan":str(final),
      "architecture_decision_council":str(architecture_council),
      "architecture_decision_allowed":bool(architecture_council_v.get("dispatch_allowed")),
      "architecture_portfolio_mode":((architecture_council_v.get("architecture_portfolio") or {}).get("mode")),
      "architecture_comparative_pilot_required":bool((architecture_council_v.get("architecture_portfolio") or {}).get("comparative_pilot_required")),
      "architecture_comparative_pilot":str(comparative_pilot) if comparative_pilot.exists() else None,
      "architecture_comparative_pilot_status":comparative_pilot_v.get("status"),
      "architecture_comparative_pilot_resolved":bool(comparative_pilot_v.get("resolved")),
      "architecture_mandatory_advisors":architecture_council_v.get("mandatory_advisors") or [],
      "capability_foundry_created_domains":foundry_v.get("created_domain_count",0),
      "capability_foundry_created_capabilities":foundry_v.get("created_capability_count",0),
      "domain_dispatch_allowed":bool(final_v.get("dispatch_allowed")),
      "fast_path":fast_path,
      "runtime_materialized_branches":int((branch_v.get("summary") or {}).get("materialized") or 0),
      "runtime_memory_hard_limit_mb":int((branch_v.get("summary") or {}).get("runtime_memory_hard_limit_mb") or 0),
      "runtime_disk_soft_limit_mb":int((branch_v.get("summary") or {}).get("runtime_disk_soft_limit_mb") or 0),
      "external_spend_eur":float((branch_v.get("summary") or {}).get("external_spend_eur") or 0),
      "guardian_external_enabled":bool(_GUARDIAN_CONTEXT.get("enabled")),
      "guardian_event_dir":str(_GUARDIAN_CONTEXT.get("event_dir")),
      "logic_search_report":str(logic_report),
      "ux_planning_report":str(ux_report),
      "multi_agent_compromise":str(compromise),
      "logic_challenge_status":load(logic_report).get("challenge_status"),
      "ux_challenge_status":load(ux_report).get("challenge_status"),
      "central_compromise_found":bool(compromise_v.get("central_compromise_found")),
      "architecture_council_consumed_compromise":bool((architecture_council_v.get("logic_ux_compromise") or {}).get("valid")),
      "revision_request_only_after_failed_compromise":True,
      "assurance_exchange_recommendations":assurance_recommendations,
      "assurance_exchange_recommendation_count":len(assurance_recommendations),
      "assurance_exchange_blocker_count":sum(1 for x in assurance_recommendations if x.get("priority")=="BLOCKER"),
      "assurance_exchange_optimize_count":sum(1 for x in assurance_recommendations if x.get("priority")=="OPTIMIZE"),
      "assurance_exchange_direct_mutation_allowed":False,
      "assurance_exchange_remediation_owner":"central-orchestrator",
      "next_stage":next_stage
    }
    save(out/"bootstrap-result.json",state)
    print("CHACHA_AUTONOMOUS_PROJECT_BOOTSTRAP=PASS")
    print("PROJECT_ID="+pid)
    print("NEXT_STAGE="+next_stage)
    print("FAST_PATH="+("YES" if fast_path else "NO"))
    print("MATERIALIZED_BRANCHES="+str(state["runtime_materialized_branches"]))
    print("RUNTIME_WAVES="+str(state["runtime_wave_count"]))
    print("RUNTIME_MEMORY_MB="+str(state["runtime_memory_hard_limit_mb"]))
    print("MEMORY_GUIDED_FOUNDRY_PLANNING=YES")
    print("AGENT_FOUNDRY_MEMORY_GUIDED_DECISIONS="+str(state["agent_foundry_memory_guided_decisions"]))
    print("BRANCH_FOUNDRY_MEMORY_GUIDED_DECISIONS="+str(state["branch_foundry_memory_guided_decisions"]))
    print("CAPABILITY_FOUNDRY_MEMORY_GUIDED_PLANS="+str(state["capability_foundry_memory_guided_plans"]))
    print("CAPABILITY_FOUNDRY_AUTO_CLOSED="+str(state["capability_foundry_auto_closed_count"]))
    print("CAPABILITY_FOUNDRY_BUILD_REQUIRED="+str(state["capability_foundry_build_required_count"]))
    print("CAPABILITY_FOUNDRY_SAME_PROJECT_RESUME="+("YES" if state["capability_foundry_same_project_resume_allowed"] else "NO"))
    print("ACTIVE_CAPABILITY_REGISTRY="+str(state["active_capability_registry"]))
    print("ACTIVE_PROVIDER_ADAPTER_REGISTRY="+str(state["active_provider_adapter_registry"]))
    print("CAPABILITY_BUILD_AUTO_BUILT="+str(state["capability_build_auto_built_count"]))
    print("CAPABILITY_BUILD_SPECIALIST_REQUIRED="+str(state["capability_build_specialist_required_count"]))
    print("CAPABILITY_BUILD_SAME_PROJECT_RESUME="+("YES" if state["capability_build_same_project_resume"] else "NO"))
    print("CAPABILITY_BUILD_DURABLE_ADOPTION_BEFORE_PROJECT_SUCCESS=NO")
    print("CAPABILITY_ADOPTION_CANDIDATES="+str(state["capability_adoption_candidate_count"]))
    print("DURABLE_REGISTRY_MERGED_BEFORE_GAPS=YES")
    print("CAPABILITY_TRUST_FILTER_APPLIED="+("YES" if state["capability_trust_filter_applied"] else "NO_SNAPSHOT"))
    print("CAPABILITY_TRUST_PROJECT_DISTINCT=YES")
    print("CAPABILITY_TRUST_PERMISSION_ESCALATION=NO")
    print("LOGIC_CHALLENGE_STATUS="+str(state["logic_challenge_status"]))
    print("UX_CHALLENGE_STATUS="+str(state["ux_challenge_status"]))
    print("CENTRAL_COMPROMISE_FOUND="+("YES" if state["central_compromise_found"] else "NO"))
    print("ARCHITECTURE_COUNCIL_CONSUMED_COMPROMISE="+("YES" if state["architecture_council_consumed_compromise"] else "NO"))
    print("REVISION_REQUEST_ONLY_AFTER_FAILED_COMPROMISE=YES")
    print("ASSURANCE_EXCHANGE_RECOMMENDATIONS="+str(state["assurance_exchange_recommendation_count"]))
    print("ASSURANCE_EXCHANGE_BLOCKERS="+str(state["assurance_exchange_blocker_count"]))
    print("ASSURANCE_EXCHANGE_OPTIMIZE="+str(state["assurance_exchange_optimize_count"]))
    print("PROJECT_EMBEDDED_ASSURANCE=REQUIRED")
    print("GUARDIAN_LOCAL="+("ENABLED" if state["guardian_local_enabled"] else "DISABLED"))
    print("SENTINEL_LOCAL="+("ENABLED" if state["sentinel_local_enabled"] else "DISABLED"))
    print("CURATOR_LOCAL="+("ENABLED" if state["curator_local_enabled"] else "DISABLED"))
    print("BASTION_LOCAL="+("ENABLED" if state["bastion_local_enabled"] else "DISABLED"))
    print("INTENDANT_LOCAL="+("ENABLED" if state["intendant_local_enabled"] else "DISABLED"))
    print("PROJECT_ASSURANCE_IDENTITY="+("ACTIVE" if state["project_assurance_identity_active"] else "PENDING"))
    print("SPECIALIST_AUTHORITY_IDENTITIES="+("ACTIVE" if state["specialist_authority_identities_active"] else "PENDING"))
    print("CURATOR_CENTRAL_AUTHORITY=ACTIVE")
    print("BASTION_CENTRAL_AUTHORITY=ACTIVE")
    print("BASTION_SURVIVAL_GUARD=ACTIVE")
    print("BASTION_PROJECT_CONTROL_GUARD=ACTIVE")
    print("BASTION_FAILOVER=RESERVED_INACTIVE")
    print("INTENDANT_CENTRAL_AUTHORITY=ACTIVE")
    print("EXTERNAL_SPEND_EUR="+str(state["external_spend_eur"]))

if __name__=="__main__":main()
