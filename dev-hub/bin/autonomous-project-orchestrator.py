#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys,tempfile
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def run(script,args):
    p=subprocess.run([sys.executable,str(script),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
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

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",default=".",type=Path)
    ap.add_argument("--intent",required=True,type=Path)
    ap.add_argument("--output-dir",required=True,type=Path)
    a=ap.parse_args();root=a.repo_root.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    cfg=root/"dev-hub/config";bin=root/"dev-hub/bin"

    contract=out/"functional-contract.json"
    run(bin/"specification-compiler.py",["--intent",a.intent,"--output",contract])

    pre=out/"preplan.json"
    run(bin/"functional-intent-orchestrator.py",["--config",cfg/"domain-orchestration.v1.json","--intent",a.intent,"--output",pre])
    pre_v=load(pre)
    assert pre_v.get("dispatch_allowed") is False

    project=out/"project.json"
    run(bin/"project-factory.py",["--intent",a.intent,"--domain-plan",pre,
        "--config",cfg/"project-factory.v1.json","--knowledge-fabric",cfg/"knowledge-fabric.v1.json","--output",project])
    project_v=load(project);pid=project_v["project_id"]

    topology=out/"agent-topology.json"
    run(bin/"agent-foundry-planner.py",["--preplan",pre,"--config",cfg/"agent-foundry.v1.json",
        "--routing",cfg/"agent-routing.v1.json","--project-id",pid,"--output",topology])

    capreg=load(cfg/"capability-registry.v1.json");known=set((capreg.get("capabilities") or {}).keys())
    contract_v=load(contract)
    gaps=[]
    for pkg in pre_v.get("packages") or []:
        for cap in pkg.get("capabilities") or []:
            if cap not in known:gaps.append({"id":cap,"domain":pkg.get("domain")})
    for hint in contract_v.get("capability_hints") or []:
        if isinstance(hint,str) and hint not in known:gaps.append({"id":hint})
        elif isinstance(hint,dict) and hint.get("id") not in known:gaps.append(hint)
    uniq={str(x.get("id")):x for x in gaps if x.get("id")}
    gapreq=out/"capability-gaps.json";save(gapreq,{"project_id":pid,"missing_capabilities":list(uniq.values())})

    foundry_plan=out/"capability-foundry.json"
    dom_overlay=out/"domain-overlay.json";cap_overlay=out/"capability-overlay.json";routing_overlay=out/"routing-overlay.json"
    run(bin/"capability-foundry.py",["--request",gapreq,"--policy",cfg/"capability-foundry.v1.json",
       "--domains",cfg/"domain-orchestration.v1.json","--capabilities",cfg/"capability-registry.v1.json",
       "--output",foundry_plan,"--domain-overlay",dom_overlay,"--capability-overlay",cap_overlay,"--routing-overlay",routing_overlay])
    foundry_v=load(foundry_plan)

    final=out/"final-plan.json"
    if foundry_v.get("created_domain_count") or foundry_v.get("created_capability_count"):
        merged_domain=out/"runtime-domain-orchestration.json";merged_caps=out/"runtime-capabilities.json";merged_routing=out/"runtime-routing.json"
        merge_domain(cfg/"domain-orchestration.v1.json",dom_overlay,merged_domain)
        merge_caps(cfg/"capability-registry.v1.json",cap_overlay,merged_caps)
        merge_routing(cfg/"agent-routing.v1.json",routing_overlay,merged_routing)
        # New branch/capability exists project-locally; Foundry must rerun on the revised platform view.
        revised_pre=out/"revised-preplan.json"
        run(bin/"functional-intent-orchestrator.py",["--config",merged_domain,"--intent",a.intent,"--output",revised_pre])
        revised_topology=out/"revised-agent-topology.json"
        run(bin/"agent-foundry-planner.py",["--preplan",revised_pre,"--config",cfg/"agent-foundry.v1.json",
            "--routing",merged_routing,"--project-id",pid,"--output",revised_topology])
        run(bin/"functional-intent-orchestrator.py",["--config",merged_domain,"--intent",a.intent,
            "--agent-topology",revised_topology,"--output",final])
        used_topology=revised_topology
    else:
        run(bin/"functional-intent-orchestrator.py",["--config",cfg/"domain-orchestration.v1.json","--intent",a.intent,
            "--agent-topology",topology,"--output",final])
        used_topology=topology

    final_v=load(final)
    state={
      "schema":"chacha.dev/autonomous-project-bootstrap/v1","project_id":pid,
      "functional_contract":str(contract),"project":str(project),
      "preplan":str(pre),"agent_topology":str(used_topology),
      "capability_foundry":str(foundry_plan),"final_plan":str(final),
      "capability_foundry_created_domains":foundry_v.get("created_domain_count",0),
      "capability_foundry_created_capabilities":foundry_v.get("created_capability_count",0),
      "domain_dispatch_allowed":bool(final_v.get("dispatch_allowed")),
      "next_stage":"DOMAIN_FACTORIES" if final_v.get("dispatch_allowed") else "REPLAN_REQUIRED"
    }
    save(out/"bootstrap-result.json",state)
    print("CHACHA_AUTONOMOUS_PROJECT_BOOTSTRAP=PASS")
    print("PROJECT_ID="+pid)
    print("NEXT_STAGE="+state["next_stage"])
if __name__=="__main__":main()
