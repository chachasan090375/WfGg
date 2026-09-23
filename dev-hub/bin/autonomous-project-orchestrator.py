#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import uuid
from pathlib import Path

import guardian_remediation_runtime as grr
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
    "agent-foundry-planner.py":"agent-foundry",
    "agent-role-contract-manager.py":"agent-contract-registry",
    "component-role-contract-manager.py":"component-contract-registry",
    "branch-foundry-planner.py":"branch-foundry",
    "capability-foundry.py":"capability-foundry",
    "central-memory-recall.py":"central-memory-recall",
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
      "central_memory_recall":all_pass("central-memory-recall"),
      "reuse_memory":all_pass("reuse-memory"),
      "architecture_memory":all_pass("architecture-memory"),
      "architecture_portfolio":all_pass("architecture-portfolio"),
      "branch_foundry":all_pass("branch-foundry"),
      "agent_foundry":all_pass("agent-foundry"),
      "capability_foundry":all_pass("capability-foundry"),
      "constraint_policy":all_pass("constraint-policy"),
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

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",default=".",type=Path)
    ap.add_argument("--intent",required=True,type=Path)
    ap.add_argument("--output-dir",required=True,type=Path)
    a=ap.parse_args()
    if emergency_stop_active():
        raise SystemExit("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
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

    # Capability gaps may create project-local branches/capabilities.
    gapreq=out/"capability-gaps.json"
    capability_gaps(pre,contract,cfg/"capability-registry.v1.json",pid,gapreq)
    foundry_plan=out/"capability-foundry.json"
    dom_overlay=out/"domain-overlay.json";cap_overlay=out/"capability-overlay.json";routing_overlay=out/"routing-overlay.json"
    run(bin_dir/"capability-foundry.py",[
       "--request",gapreq,"--policy",cfg/"capability-foundry.v1.json",
       "--domains",cfg/"domain-orchestration.v1.json",
       "--capabilities",cfg/"capability-registry.v1.json",
       "--output",foundry_plan,
       "--domain-overlay",dom_overlay,
       "--capability-overlay",cap_overlay,
       "--routing-overlay",routing_overlay
    ])
    foundry_v=load(foundry_plan)

    active_pre=pre
    active_intent=a.intent
    active_domain=cfg/"domain-orchestration.v1.json"
    active_routing=cfg/"agent-routing.v1.json"

    if foundry_v.get("created_domain_count") or foundry_v.get("created_capability_count"):
        merged_domain=out/"runtime-domain-orchestration.json"
        merged_caps=out/"runtime-capabilities.json"
        merged_routing=out/"runtime-routing.json"
        merge_domain(cfg/"domain-orchestration.v1.json",dom_overlay,merged_domain)
        merge_caps(cfg/"capability-registry.v1.json",cap_overlay,merged_caps)
        merge_routing(cfg/"agent-routing.v1.json",routing_overlay,merged_routing)

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

    # Final foundry pass on the stable branch/capability set.
    agent_topology=out/"agent-topology.json"
    branch_parallel=out/"branch-topology-parallel.json"
    run_parallel_foundries(bin_dir,cfg,active_pre,pid,active_routing,memory_brief,agent_topology,branch_parallel)

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
                "--comparative-pilot-result",comparative_pilot,
                "--output",architecture_council
            ])
            architecture_council_v=load(architecture_council)

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
    final_v["dispatch_allowed"]=bool(final_v.get("dispatch_allowed")) and bool(architecture_council_v.get("dispatch_allowed"))
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
    if fast_path:
        next_stage="KNOWLEDGE_FAST_PATH"
    elif final_v.get("dispatch_allowed"):
        next_stage="DOMAIN_FACTORIES"
    elif bool((architecture_council_v.get("architecture_portfolio") or {}).get("comparative_pilot_required")):
        next_stage="ARCHITECTURE_COMPARATIVE_PILOT_REQUIRED"
    else:
        next_stage="REPLAN_REQUIRED"

    state={
      "schema":"chacha.dev/autonomous-project-bootstrap/v1",
      "version":"6.23.0",
      "project_id":pid,
      "functional_contract":str(contract),
      "project":str(project),
      "preplan":str(active_pre),
      "central_memory_brief":str(memory_brief),
      "central_memory_brief_digest":load(memory_brief).get("brief_digest"),
      "central_memory_source_snapshot_digest":load(memory_brief).get("source_memory_snapshot_digest"),
      "central_memory_trusted_count":int(load(memory_brief).get("trusted_memory_count") or 0),
      "central_memory_caution_count":int(load(memory_brief).get("caution_count") or 0),
      "central_memory_current_best_reuse_count":int(load(memory_brief).get("reuse_candidate_count") or 0),
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
    print("EXTERNAL_SPEND_EUR="+str(state["external_spend_eur"]))

if __name__=="__main__":main()
