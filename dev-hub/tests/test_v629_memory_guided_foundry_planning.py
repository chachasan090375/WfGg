#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def save(path,obj):Path(path).write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")

recall=loadmod("v629_recall",BIN/"central-memory-recall.py")
agent=loadmod("v629_agent",BIN/"agent-foundry-planner.py")
branch=loadmod("v629_branch",BIN/"branch-foundry-planner.py")
capfoundry=loadmod("v629_capability",BIN/"capability-foundry.py")
import planning_memory_runtime as pmr

watch={
  "eligible_provider_candidates":[{"id":"zero-cost-current","external_spend_eur":0}],
  "branch_blueprints":[],
  "snapshot_freshness":"FRESH","targeted_refresh_performed":False,
  "source_snapshot_digest":"tw-v629","zero_spend_candidate_available":True,
  "selection_rule":"ZERO_SPEND_FIRST"
}
agent.tw.consult=lambda *a,**k:dict(watch)
branch.tw.consult=lambda *a,**k:dict(watch)
capfoundry.tw.consult=lambda *a,**k:dict(watch)

pre={
 "schema":"chacha.dev/domain-plan/v1","mode":"implementation","implementation_allowed":True,
 "intent":{"summary":"graphics generation"},
 "packages":[{
   "id":"domain:graphics","domain":"graphics","kind":"primary",
   "roles":["graphics-old-agent","graphics-agent"],
   "capabilities":["image-generation"],"toolchain":[]
 }]
}
intent={"schema":"test-intent","request":"generate a graphics image","domains":["graphics"]}
memory={
 "schema":"chacha.dev/central-memory-assimilation/v1","snapshot_digest":"memory-v629",
 "items":[],
 "reuse_catalog":{
   "branches":[{
     "branch_id":"graphics-reusable-branch","version":"v3","domain":"graphics",
     "functional_signature":"sig","state":"ADOPT","qualification_status":"PASS",
     "external_spend_eur":0,"quality_score":99,"success_count":8,"failure_count":0,
     "incident_count":0,"version_status":"CURRENT_BEST",
     "component_confidence":{"state":"TRUSTED","confidence":0.98}
   }],
   "architectures":[]
 },
 "component_confidence":{"available":True,"snapshot_digest":"confidence-v629",
                         "trusted_count":2,"negative_state_count":1}
}
confidence={
 "schema":"chacha.dev/component-confidence-snapshot/v1","snapshot_digest":"confidence-v629",
 "trusted_count":2,"negative_state_count":1,
 "items":[
   {"component_kind":"agent","component_id":"graphics-agent","version":"v7",
    "confidence":0.97,"state":"TRUSTED","verified_success_count":6,
    "reuse_advisory_eligible":True},
   {"component_kind":"agent","component_id":"graphics-old-agent","version":"v2",
    "confidence":0.31,"state":"DEGRADED","verified_success_count":3,
    "verified_failure_count":1,"reuse_advisory_eligible":False},
   {"component_kind":"agent","component_id":"unrelated-qa-agent","version":"v9",
    "confidence":0.99,"state":"TRUSTED","verified_success_count":20,
    "reuse_advisory_eligible":True}
 ]
}
policy=load(CFG/"central-memory-recall.v1.json")
brief=recall.recall(memory,intent,pre,"new-project",policy,confidence)
trusted={x["component_id"] for x in brief["trusted_component_candidates"]}
caution={x["component_id"] for x in brief["caution_component_candidates"]}
assert "graphics-agent" in trusted,brief
assert "unrelated-qa-agent" not in trusted,brief
assert "graphics-old-agent" in caution,brief
assert brief["reuse_candidate_count"]==1,brief
assert brief["foundry_planning_context_ready"] is True

advice=pmr.package_advice(brief,pre["packages"][0])
assert pmr.preferred_ids(advice,{"agent"})==["graphics-agent"],advice
assert "graphics-old-agent" in pmr.avoid_ids(advice,{"agent"}),advice
assert advice["reuse_candidates"],advice
assert advice["rules"]["architecture_council_final_authority"] is True

routing={"roles":{
  "graphics-agent":{"capabilities":["image-generation"]},
  "graphics-old-agent":{"capabilities":["image-generation"]}
}}
agent_cfg=load(CFG/"agent-foundry.v1.json")
top=agent.build(pre,agent_cfg,routing,"new-project",brief)
d=top["decisions"][0]
assert d["decision"]=="REUSE_EXISTING_AGENT",d
assert d["agent_id"]=="graphics-agent",d
assert d["memory_guided_decision"] is True,d
assert d["memory_excluded_roles"]==["graphics-old-agent"],d
assert top["summary"]["memory_guided_decisions"]==1,top

branch_cfg=load(CFG/"branch-foundry.v1.json")
bt=branch.build(pre,branch_cfg,"new-project",top,brief)
bd=bt["decisions"][0]
assert bd["memory_reuse_candidates_considered"]>=1,bd
assert bd["memory_guided_decision"] is True,bd
assert bt["summary"]["memory_guided_decisions"]>=1,bt
assert bd["technology_watch"]["consulted"] is True,bd

with tempfile.TemporaryDirectory(prefix="v629-capability-") as td:
    td=Path(td)
    req=td/"request.json";domains=td/"domains.json";caps=td/"caps.json";mem=td/"memory.json"
    out=td/"out.json";do=td/"domains-out.json";co=td/"caps-out.json";ro=td/"routing-out.json"
    save(req,{"project_id":"new-project","missing_capabilities":[{
      "id":"image-generation","domain":"graphics",
      "architecture_candidates":[{"id":"graphics-old-agent"},{"id":"fresh-design"}]
    }]})
    save(domains,{"domains":{"graphics":{"orchestrator":"graphics-orchestrator"}}})
    save(caps,{"capabilities":{}})
    save(mem,brief)
    oldargv=sys.argv
    try:
        sys.argv=[
          "capability-foundry.py","--request",str(req),"--policy",str(CFG/"capability-foundry.v1.json"),
          "--domains",str(domains),"--capabilities",str(caps),"--memory-brief",str(mem),
          "--output",str(out),"--domain-overlay",str(do),"--capability-overlay",str(co),"--routing-overlay",str(ro)
        ]
        capfoundry.main()
    finally:
        sys.argv=oldargv
    cv=load(out);p=cv["plans"][0]
    assert cv["central_memory_recall_consumed"] is True,cv
    assert p["memory_guided_candidate_count"]>=1,p
    assert all(x.get("id")!="graphics-old-agent" for x in p["architecture_candidates"]),p
    assert p["technology_watch"]["consulted"] is True,p

for path,key in [
 (CFG/"agent-foundry.v1.json","central_memory_guides_existing_agent_candidate_order"),
 (CFG/"branch-foundry.v1.json","central_memory_guides_hard_valid_blueprint_order"),
]:
    cfg=load(path);assert cfg["principles"][key] is True,cfg
ccfg=load(CFG/"capability-foundry.v1.json")
assert ccfg["rules"]["central_memory_seeds_capability_design_candidates"] is True
assert ccfg["rules"]["architecture_council_remains_final_authority"] is True
assert policy["behavior"]["memory_guides_candidate_generation_not_final_architecture"] is True

print("CHACHA_DEV_V629_CONTEXTUAL_COMPONENT_RANKING=PASS")
print("CHACHA_DEV_V629_NEGATIVE_COMPONENT_FAST_REUSE_EXCLUSION=PASS")
print("CHACHA_DEV_V629_AGENT_FOUNDRY_MEMORY_DECISION=PASS")
print("CHACHA_DEV_V629_BRANCH_FOUNDRY_MEMORY_CANDIDATES=PASS")
print("CHACHA_DEV_V629_CAPABILITY_FOUNDRY_MEMORY_CANDIDATES=PASS")
print("CHACHA_DEV_V629_TECHNOLOGY_WATCH_REMAINS_REQUIRED=PASS")
print("CHACHA_DEV_V629_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=PASS")
print("CHACHA_DEV_V629_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
