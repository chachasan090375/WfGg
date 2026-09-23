#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

recall=mod("cmr",BIN/"central-memory-recall.py")

memory={
 "schema":"chacha.dev/central-memory-assimilation/v1",
 "snapshot_digest":"mem-123",
 "items":[
  {"item_key":"p1","scope":"PROJECT","project_id":"p-current","subject_kind":"experience","subject_id":"graphics-agent",
   "signal_key":"intent:image-generation","state":"TRUSTED","generalizable":False,"confidence":0.92,"latest_observed_at":"2026-09-23T01:00:00Z"},
  {"item_key":"g1","scope":"GLOBAL_CANDIDATE","project_id":None,"subject_kind":"experience","subject_id":"branch-foundry",
   "signal_key":"intent:image-generation","state":"TRUSTED","generalizable":True,"confidence":0.91,"latest_observed_at":"2026-09-23T01:01:00Z"},
  {"item_key":"g2","scope":"GLOBAL_CANDIDATE","project_id":None,"subject_kind":"agent","subject_id":"other-agent",
   "signal_key":"intent:image-generation","state":"PROVISIONAL","generalizable":False,"confidence":0.3,"latest_observed_at":"2026-09-23T01:02:00Z"},
  {"item_key":"g3","scope":"GLOBAL_CANDIDATE","project_id":None,"subject_kind":"embedded-application-agent","subject_id":"graphics-runtime",
   "signal_key":"anomaly:image-generation-regression","state":"CONTRADICTED","generalizable":False,"confidence":0.4,"latest_observed_at":"2026-09-23T01:03:00Z"}
 ],
 "reuse_catalog":{
   "branches":[
    {"branch_id":"generic:graphics:primary","version":"v3","domain":"graphics","functional_signature":"image-generation","version_status":"CURRENT_BEST","quality_score":99,"success_count":12},
    {"branch_id":"generic:graphics:primary","version":"v2","domain":"graphics","functional_signature":"image-generation","version_status":"SUPERSEDED","quality_score":97,"success_count":8}
   ],
   "architectures":[
    {"architecture_id":"graphics-stack","version":"v5","functional_signature":"image-generation","version_status":"CURRENT_BEST","quality_score":98,"success_count":6}
   ]
 }
}
intent={"goal":"generate an image","domains":["graphics"],"capabilities":["image-generation"]}
pre={"schema":"chacha.dev/domain-plan/v1","intent":"generate image","dispatch_allowed":False,
     "packages":[{"id":"graphics-main","domain":"graphics","kind":"primary","capabilities":["image-generation"],
                  "roles":["graphics-agent"],"toolchain":[]}]}
policy=json.load(open(CFG/"central-memory-recall.v1.json",encoding="utf-8"))
out=recall.recall(memory,intent,pre,"p-current",policy)
assert out["memory_authority"]=="ADVISORY",out
assert out["technology_revalidation_required"] is True,out
assert out["previous_solution_is_default"] is False,out
assert out["single_observation_is_actionable"] is False,out
assert {x["item_key"] for x in out["trusted_memory"]}=={"p1","g1"},out["trusted_memory"]
assert "g2" not in {x["item_key"] for x in out["trusted_memory"]},out
assert "g3" in {x["item_key"] for x in out["cautions"]},out["cautions"]
reuse={(x["kind"],x.get("version")) for x in out["current_best_reuse_candidates"]}
assert ("branch","v3") in reuse and ("branch","v2") not in reuse,reuse
assert ("architecture","v5") in reuse,reuse

# Agent Foundry consumes the brief but may not treat it as final authority.
agent=mod("agent_foundry_v623",BIN/"agent-foundry-planner.py")
agent.tw.consult=lambda *a,**k:{
  "snapshot_freshness":"FRESH","targeted_refresh_performed":False,"source_snapshot_digest":"tw-1",
  "zero_spend_candidate_available":True,"selection_rule":"TEST","eligible_provider_candidates":[],
  "automatic_external_spend_eur":0
}
agent_cfg=json.load(open(CFG/"agent-foundry.v1.json",encoding="utf-8"))
routing={"roles":{"graphics-agent":{"capabilities":["image-generation"]}}}
aout=agent.build(pre,agent_cfg,routing,"p-current",out)
assert aout["central_memory_recall_consumed"] is True,aout
ad=aout["decisions"][0]
assert ad["central_memory_recall"]["consumed"] is True,ad
assert ad["central_memory_recall"]["technology_revalidation_required"] is True,ad
assert ad["central_memory_recall"]["memory_authority"]=="ADVISORY",ad

branch_src=(BIN/"branch-foundry-planner.py").read_text(encoding="utf-8")
for m in ["--memory-brief","central_memory_recall_consumed","previous_solution_is_default","technology_revalidation_required"]:
    assert m in branch_src,m

council=(BIN/"architecture-decision-council.py").read_text(encoding="utf-8")
assert '"central-memory-recall"' in council
assert '--memory-brief' in council
assert '"version":"6.23.0"' in council
assert "recall_branch_rank" in council and "recall_arch_rank" in council

orch=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert orch.count('"central-memory-recall.py"')>=3,orch.count('"central-memory-recall.py"')
assert orch.count('"--memory-brief"')>=5,orch.count('"--memory-brief"')
assert '"version":"6.23.0"' in orch
assert '"central_memory_brief"' in orch

guardian=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
assert '"central_memory_assimilation","central_memory_recall"' in guardian
assert "central_memory_assimilation_evidence_required:true" in guardian
assert "contextual_memory_recall_evidence_required:true" in guardian
assert "coverage_remediation_auto_resolution:true" in guardian
assert "remediation_cascade_suppression:true" in guardian
assert "storeEvent(env,event,evaluation,Boolean(hold))" in guardian
assert "resolveCoverageRemediations" in guardian

contracts=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
cc=next(x for x in contracts["contracts"] if x["contract_id"]=="role:architecture-decision-council")
assert "central_memory_assimilation" in cc["required_evidence"]
assert "central_memory_recall" in cc["required_evidence"]

print("CHACHA_DEV_V623_CONTEXTUAL_MEMORY_RECALL=PASS")
print("CHACHA_DEV_V623_PROJECT_MEMORY_PRIORITY=PASS")
print("CHACHA_DEV_V623_TRUSTED_GLOBAL_GENERALIZATION=PASS")
print("CHACHA_DEV_V623_PROVISIONAL_NOT_ACTIONABLE=PASS")
print("CHACHA_DEV_V623_NEGATIVE_MEMORY_CAUTION=PASS")
print("CHACHA_DEV_V623_CURRENT_BEST_REUSE_ONLY=PASS")
print("CHACHA_DEV_V623_FOUNDRIES_CONSUME_MEMORY_BRIEF=PASS")
print("CHACHA_DEV_V623_COUNCIL_CONTEXTUAL_MEMORY_ADVISOR=PASS")
installer=(BIN/"install-v623-contextual-memory-recall.sh").read_text(encoding="utf-8")
assert "guardian-coverage-bootstrap" in installer
assert installer.index("guardian-coverage-bootstrap") < installer.index("guardian-central-memory-recall-contract")
print("CHACHA_DEV_V623_GUARDIAN_MEMORY_EVIDENCE_GATE=PASS")
print("CHACHA_DEV_V623_GUARDIAN_COVERAGE_BOOTSTRAP_ORDER=PASS")
print("CHACHA_DEV_V623_REMEDIATION_CASCADE_SUPPRESSION=PASS")
print("CHACHA_DEV_V623_TECHNOLOGY_REVALIDATION_REMAINS_REQUIRED=PASS")
print("CHACHA_DEV_V623_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
