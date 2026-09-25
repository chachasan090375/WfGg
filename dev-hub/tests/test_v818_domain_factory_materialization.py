#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RUNNER=ROOT/"dev-hub/bin/domain-factory-runner.py"

def write(p:Path,x):
    p.write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

def good_constraints():
    return {
      "branch_ready":True,"agent_ready":True,"capability_gaps_resolved":True,
      "zero_spend_rule_respected":True,"security_boundary_reduction":False
    }

with tempfile.TemporaryDirectory(prefix="v818-domain-factory-") as td:
    td=Path(td)
    plan=td/"final-plan.json"; council=td/"council.json"; wave=td/"waves.json"; policy=td/"policy.json"; out=td/"out"
    write(plan,{
      "schema":"chacha.dev/domain-plan/v1","project_id":"p1",
      "packages":[
        {"id":"domain:threat-intelligence","domain":"threat-intelligence","kind":"primary",
         "capabilities":["isolated-network-collection","semantic-source-analysis"],
         "agent_topology_status":"RESOLVED","branch_topology_status":"RESOLVED",
         "agent_id":"dark-intelligence-agent","branch_id":"p1:threat-intelligence:primary",
         "runtime_required":True,"runtime_architecture":"EPHEMERAL_CAPSULE",
         "materialization_profile":"STANDARD","resource_budget":{"memory_hard_limit_mb":192}},
        {"id":"review:documentation","domain":"documentation","kind":"review",
         "capabilities":["documentation"],
         "agent_topology_status":"RESOLVED","branch_topology_status":"RESOLVED",
         "agent_id":"documentation-review-agent","branch_id":"p1:documentation:review",
         "runtime_required":False,"runtime_architecture":"VIRTUAL_SHARED",
         "materialization_profile":"VIRTUAL","resource_budget":{}}
      ]})
    write(council,{
      "schema":"chacha.dev/architecture-decision-council/v1","project_id":"p1","dispatch_allowed":True,
      "decisions":[
        {"package_id":"domain:threat-intelligence","blocked_by":[],"constraint_policy":good_constraints()},
        {"package_id":"review:documentation","blocked_by":[],"constraint_policy":good_constraints()}
      ]})
    write(wave,{
      "schema":"chacha.dev/runtime-wave-plan/v1","schedulable":True,"unschedulable":[],
      "waves":[{"wave":1,"branches":["p1:threat-intelligence:primary"],
                "memory_mb":192,"disk_mb":256,"cpu_weight":35,"processes":1}]})
    write(policy,{
      "schema":"chacha.dev/domain-factories/v1","factory_cycle":["SPECIFY","SEARCH_REUSE","DESIGN","BUILD","VERIFY","BENCHMARK","QUALIFY","CATALOG","DELIVER","LEARN"],
      "required_outputs":["component-manifest","component-contract","verification-evidence","compatibility-metadata","version","provenance"]})
    cmd=[sys.executable,str(RUNNER),"--repo-root",str(ROOT),"--final-plan",str(plan),"--council",str(council),
         "--wave-plan",str(wave),"--factory-policy",str(policy),"--output-dir",str(out)]
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    result=json.loads((out/"domain-factory-result.json").read_text())
    assert result["status"]=="PASS" and result["next_stage"]=="DOMAIN_EXECUTION",result
    assert result["component_count"]==2 and result["materialized_count"]==2
    reg=json.loads((out/"component-registry.json").read_text())
    assert reg["scope"]=="PROJECT_LOCAL" and reg["durable_promotion"] is False
    assert all(x["state"]=="QUALIFIED" for x in reg["components"])
    ex=json.loads((out/"domain-execution-manifest.json").read_text())
    assert ex["status"]=="READY" and ex["wave_count"]==1 and ex["component_count"]==2
    assert len(ex["waves"][0]["components"])==1 and len(ex["virtual_components"])==1
    for row in reg["components"]:
        m=json.loads(Path(row["manifest"]).read_text())
        assert m["qualification_scope"]=="FACTORY_PACKAGE_ONLY"
        assert m["business_delivery_verified"] is False
        assert m["production_authority"] is False
        assert m["task_execution_required"] is True
        c=json.loads(Path(row["contract"]).read_text())
        assert c["authority"]["production"] is False
        e=json.loads(Path(row["evidence"]).read_text())
        assert e["status"]=="PASS" and e["business_delivery_verified"] is False

    # Reuse a qualified compatible project-local domain capsule.
    reuse=td/"reuse.json"
    existing=dict(reg["components"][0]);existing["quality"]=0.95;existing["reuse_score"]=0.9
    write(reuse,{"schema":"chacha.dev/component-registry/v1","components":[existing]})
    out2=td/"out2"
    p2=subprocess.run(cmd[:-2]+["--registry",str(reuse),"--output-dir",str(out2)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p2.returncode==0,(p2.stdout,p2.stderr)
    r2=json.loads((out2/"domain-factory-result.json").read_text())
    assert r2["reused_count"]==1 and r2["materialized_count"]==1,r2

    # A package with an unresolved council constraint must fail closed.
    bad=json.loads(council.read_text())
    bad["decisions"][0]["constraint_policy"]["branch_ready"]=False
    write(council,bad)
    out3=td/"out3"
    p3=subprocess.run(cmd[:-2]+["--output-dir",str(out3)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p3.returncode==2
    r3=json.loads((out3/"domain-factory-result.json").read_text())
    assert r3["status"]=="BLOCKED"
    assert "branch_ready" in r3["blocked"][0]["failed_checks"]

print("CHACHA_DEV_V818_DOMAIN_FACTORY_MATERIALIZATION=PASS")
print("CHACHA_DEV_V818_PROJECT_LOCAL_REGISTRY=PASS")
print("CHACHA_DEV_V818_RUNTIME_WAVE_BINDING=PASS")
print("CHACHA_DEV_V818_VIRTUAL_COMPONENT_HANDLING=PASS")
print("CHACHA_DEV_V818_QUALIFICATION_NOT_BUSINESS_DELIVERY=PASS")
print("CHACHA_DEV_V818_PRODUCTION_AUTHORITY=NO")
print("CHACHA_DEV_V818_COUNCIL_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V818_REUSE_QUALIFIED_FIRST=PASS")
print("CHACHA_DEV_V818_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
