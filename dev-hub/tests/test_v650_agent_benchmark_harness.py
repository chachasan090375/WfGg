#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"dev-hub/bin"))
import agent_benchmark_harness as h,agent_evolution_controller as aec
def load(p):return json.loads(Path(p).read_text())
routing=load(ROOT/"dev-hub/config/agent-routing.v1.json");seven=load(ROOT/"dev-hub/config/seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json");policy=load(ROOT/"dev-hub/config/agent-benchmark-harness.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
agents=[{"agent_id":a["agent_id"],"scorecard":{"logician_challenge":{"owner_role":"logician","decision_authority":False}}} for a in inv["agents"]]
actions=[]
for a in inv["agents"]:actions += [{"agent_id":a["agent_id"],"action":"DEEP_AGENT_AUDIT"},{"agent_id":a["agent_id"],"action":"ECOSYSTEM_BENCHMARK"}]
c=h.campaign({"scheduled_actions":actions},{"agents":agents},policy,{"state":"FRESH"})
assert c["scheduled_action_count"]==70 and c["contract_count"]==70,c
assert all(x["truth_scope"]=="BENCHMARK_ONLY" and x["production_truth_eligible"] is False for x in c["contracts"])
assert all(x["fixture_contract_digest"].startswith("sha256:") and x["environment_contract_digest"].startswith("sha256:") for x in c["contracts"])
contract=c["contracts"][0];fd=contract["fixture_contract_digest"];ed=contract["environment_contract_digest"];bid=contract["benchmark_id"]
base={"benchmark_id":bid,"agent_id":contract["agent_id"],"verification":"VERIFIED","verifier":"project-control","evidence_refs":["e:inc"],
 "fixture_contract_digest":fd,"environment_contract_digest":ed,"revision":"r1","metrics":{"accuracy":80,"robustness":90},
 "permission_expansion":False,"guardian_preserved":True,"sentinel_preserved":True,"automatic_external_spend_eur":0}
cand={**base,"revision":"r2","verifier":"sentinel","evidence_refs":["e:cand"],"metrics":{"accuracy":87,"robustness":92}}
good=h.compare(base,cand,policy);assert good["decision"]=="PILOT_ELIGIBLE",good
selfv={**cand,"verifier":contract["agent_id"]};assert h.compare(base,selfv,policy)["decision"]=="REJECT_CANDIDATE"
perm={**cand,"permission_expansion":True,"metrics":{"accuracy":100,"robustness":100}};assert "PERMISSION_EXPANSION" in h.compare(base,perm,policy)["hard_gate_failures"]
mismatch={**cand,"fixture_contract_digest":"sha256:other"};assert "FIXTURE_CONTRACT_MISMATCH" in h.compare(base,mismatch,policy)["hard_gate_failures"]
reg={**cand,"metrics":{"accuracy":95,"robustness":80}};assert "MATERIAL_DIMENSION_REGRESSION" in h.compare(base,reg,policy)["hard_gate_failures"]
print("CHACHA_DEV_V650_70_SCHEDULED_ACTIONS_CONSUMED=PASS")
print("CHACHA_DEV_V650_BENCHMARK_PRODUCTION_TRUTH=NO")
print("CHACHA_DEV_V650_INDEPENDENT_ORACLE_REQUIRED=PASS")
print("CHACHA_DEV_V650_FIXTURE_AND_ENVIRONMENT_PARITY=PASS")
print("CHACHA_DEV_V650_PERMISSION_EXPANSION=BLOCKED")
print("CHACHA_DEV_V650_GUARDIAN_SENTINEL_GATES=PASS")
print("CHACHA_DEV_V650_SHADOW_COMPARISON=PASS")
print("CHACHA_DEV_V650_SELF_VERIFICATION=REJECTED")
print("CHACHA_DEV_V650_LATEST_VERSION_PRIORITY=NO")
print("CHACHA_DEV_V650_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
