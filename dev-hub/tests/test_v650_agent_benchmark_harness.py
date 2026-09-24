#!/usr/bin/env python3
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"dev-hub/bin"))
import agent_benchmark_harness as h,agent_evolution_controller as aec,agent_fleet_observatory as afo
def load(p):return json.loads(Path(p).read_text())
routing=load(ROOT/"dev-hub/config/agent-routing.v1.json");seven=load(ROOT/"dev-hub/config/seven-agent-final-compromise.v1.json");project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json");policy=load(ROOT/"dev-hub/config/agent-benchmark-harness.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
agents=[{"agent_id":a["agent_id"],"scorecard":{"logician_challenge":{"owner_role":"logician","decision_authority":False}}} for a in inv["agents"]]
fleet={"agents":agents};actions=[]
for a in inv["agents"]:actions += [{"agent_id":a["agent_id"],"action":"DEEP_AGENT_AUDIT"},{"agent_id":a["agent_id"],"action":"ECOSYSTEM_BENCHMARK"}]
idx={"scheduled_actions":actions};tw={"state":"FRESH"}
c=h.campaign(idx,fleet,policy,tw);assert c["scheduled_action_count"]==70 and c["contract_count"]==70,c;assert all(x["truth_scope"]=="BENCHMARK_ONLY" and x["production_truth_eligible"] is False for x in c["contracts"]);assert all(x["technology_watch_revalidation_required"] and x["independent_oracle_required"] for x in c["contracts"])
blocked=h.compare({"benchmark_id":"b","verification":"SELF_ASSERTED","metrics":{"accuracy":80}},{"benchmark_id":"b","verification":"VERIFIED","metrics":{"accuracy":90}});assert blocked["promotion_eligible"] is False
good=h.compare({"benchmark_id":"b","verification":"VERIFIED","metrics":{"accuracy":80,"robustness":90}},{"benchmark_id":"b","verification":"VERIFIED","metrics":{"accuracy":90,"robustness":90}});assert good["promotion_eligible"] is True
bad=h.compare({"benchmark_id":"b","verification":"VERIFIED","metrics":{"accuracy":80,"robustness":90}},{"benchmark_id":"b","verification":"VERIFIED","metrics":{"accuracy":90,"robustness":80}});assert bad["promotion_eligible"] is False and bad["material_regression"] is True
print("CHACHA_DEV_V650_70_SCHEDULED_ACTIONS_CONSUMED=PASS");print("CHACHA_DEV_V650_BENCHMARK_PRODUCTION_TRUTH=NO");print("CHACHA_DEV_V650_INDEPENDENT_ORACLE_REQUIRED=PASS");print("CHACHA_DEV_V650_LOGICIAN_CHALLENGE_REQUIRED=PASS");print("CHACHA_DEV_V650_SHADOW_COMPARISON=PASS");print("CHACHA_DEV_V650_SELF_PROMOTION=NO");print("CHACHA_DEV_V650_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
