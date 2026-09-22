#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def run(script,args):
    p=subprocess.run([sys.executable,str(script),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     text=True,check=False,timeout=120)
    if p.returncode!=0:
        raise RuntimeError(f"{script.name}: {p.stderr.strip()} {p.stdout.strip()}")
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

def run_parallel_foundries(bin_dir,cfg_dir,preplan,project_id,routing,agent_out,branch_out):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        af=ex.submit(run,bin_dir/"agent-foundry-planner.py",[
            "--preplan",preplan,"--config",cfg_dir/"agent-foundry.v1.json",
            "--routing",routing,"--project-id",project_id,"--output",agent_out
        ])
        bf=ex.submit(run,bin_dir/"branch-foundry-planner.py",[
            "--preplan",preplan,"--config",cfg_dir/"branch-foundry.v1.json",
            "--project-id",project_id,"--output",branch_out
        ])
        af.result();bf.result()

def refine_branch_with_agents(bin_dir,cfg_dir,preplan,project_id,agent_topology,branch_out):
    run(bin_dir/"branch-foundry-planner.py",[
        "--preplan",preplan,"--config",cfg_dir/"branch-foundry.v1.json",
        "--project-id",project_id,"--agent-topology",agent_topology,"--output",branch_out
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

    # First preflight pass: Agent Foundry and Branch Foundry truly run in parallel.
    initial_agent=out/"agent-topology-initial.json"
    initial_branch=out/"branch-topology-initial.json"
    run_parallel_foundries(bin_dir,cfg,pre,pid,cfg/"agent-routing.v1.json",initial_agent,initial_branch)

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

    # Final foundry pass on the stable branch/capability set.
    agent_topology=out/"agent-topology.json"
    branch_parallel=out/"branch-topology-parallel.json"
    run_parallel_foundries(bin_dir,cfg,active_pre,pid,active_routing,agent_topology,branch_parallel)

    # Cheap cross-optimization: Branch Foundry recalculates only its blueprints with Agent Foundry topology.
    branch_topology=out/"branch-topology.json"
    refine_branch_with_agents(bin_dir,cfg,active_pre,pid,agent_topology,branch_topology)

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
        "--output",architecture_council
    ])
    architecture_council_v=load(architecture_council)

    # The Council is not advisory-only: its selected/revalidated architecture becomes
    # the effective topology consumed by planning and runtime scheduling.
    effective_branch_topology=out/"branch-topology-effective.json"
    apply_architecture_council(branch_topology,architecture_council,effective_branch_topology)

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
    else:
        next_stage="REPLAN_REQUIRED"

    state={
      "schema":"chacha.dev/autonomous-project-bootstrap/v1",
      "version":"6.13.0",
      "project_id":pid,
      "functional_contract":str(contract),
      "project":str(project),
      "preplan":str(active_pre),
      "agent_topology":str(agent_topology),
      "branch_topology":str(effective_branch_topology),
      "branch_topology_foundry":str(branch_topology),
      "runtime_wave_plan":str(wave_plan),
      "runtime_wave_count":int(wave_v.get("wave_count") or 0),
      "runtime_schedulable":bool(wave_v.get("schedulable")),
      "capability_foundry":str(foundry_plan),
      "final_plan":str(final),
      "architecture_decision_council":str(architecture_council),
      "architecture_decision_allowed":bool(architecture_council_v.get("dispatch_allowed")),
      "architecture_mandatory_advisors":architecture_council_v.get("mandatory_advisors") or [],
      "capability_foundry_created_domains":foundry_v.get("created_domain_count",0),
      "capability_foundry_created_capabilities":foundry_v.get("created_capability_count",0),
      "domain_dispatch_allowed":bool(final_v.get("dispatch_allowed")),
      "fast_path":fast_path,
      "runtime_materialized_branches":int((branch_v.get("summary") or {}).get("materialized") or 0),
      "runtime_memory_hard_limit_mb":int((branch_v.get("summary") or {}).get("runtime_memory_hard_limit_mb") or 0),
      "runtime_disk_soft_limit_mb":int((branch_v.get("summary") or {}).get("runtime_disk_soft_limit_mb") or 0),
      "external_spend_eur":float((branch_v.get("summary") or {}).get("external_spend_eur") or 0),
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
