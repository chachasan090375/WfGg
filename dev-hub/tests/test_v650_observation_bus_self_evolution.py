#!/usr/bin/env python3
import copy,json,sqlite3,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"dev-hub/bin"))
import agent_observation_bus as bus,agent_observation_bus_health as health
def load(p):return json.loads(Path(p).read_text())
p=load(ROOT/"dev-hub/config/agent-observation-bus.v1.json");core=load(ROOT/"dev-hub/config/technology-core-watch.v1.json");logic=load(ROOT/"dev-hub/config/technology-watch-logician.v1.json")
assert "agent-observation-bus" in {x["id"] for x in core["components"]}
assert "OBSERVATION_BUS_CHAIN_TAMPER_PROBE" in {x["id"] for x in logic["verification_routes"]}
with tempfile.TemporaryDirectory() as td:
 rt=Path(td);s=rt/"s.json";r=rt/"r.json";x=health.assess(ROOT,rt,p,s,r,True);assert x["status"]=="PASS",x;assert x["candidate_owner"]=="capability-foundry";assert x["direct_self_mutation"] is False and x["self_promotion"] is False
 orig=health.inventory
 def changed(_):
  inv=copy.deepcopy(orig(ROOT))
  for a in inv["agents"]:
   if a.get("agent_id")=="backend-api-architect" and a.get("scope")=="PLATFORM":a["capabilities"]=list(a.get("capabilities") or [])+["v650-change"];break
  return inv
 health.inventory=changed;y=health.assess(ROOT,rt,p,s,r,False);assert y["status"]=="REASSESS_REQUIRED",y;req=load(Path(y["reassessment"]["path"]));assert req["candidate_owner"]=="capability-foundry";assert req["shadow_required"] and req["pilot_required"]
 health.inventory=orig
 rt2=rt/"tamper";s2=rt2/"s.json";r2=rt2/"r.json";health.assess(ROOT,rt2,p,s2,r2,False);bus.publish({"event_id":"t","event_type":"T","source_id":"run-controller","source_surface":"x","project_id":"p","revision":"r","subject_role":"backend-api-architect","outcome":"OK","verification":"OBSERVED","capabilities":[],"evidence_refs":["e"]},p,rt2);db=bus.db_path(rt2,p);con=sqlite3.connect(db);con.execute("update observations set payload_json='{}'");con.commit();con.close();z=health.assess(ROOT,rt2,p,s2,r2,False);assert z["integrity"]["hash_chain"]["status"]=="FAIL",z
print("CHACHA_DEV_V650_BUS_SELF_HEALTH=PASS");print("CHACHA_DEV_V650_AGENT_CHANGE_REASSESSMENT=PASS");print("CHACHA_DEV_V650_BUS_HASH_TAMPER_DETECTED=PASS");print("CHACHA_DEV_V650_BUS_SELF_MUTATION=NO");print("CHACHA_DEV_V650_BUS_SELF_PROMOTION=NO");print("CHACHA_DEV_V650_BUS_CANDIDATE_OWNER=CAPABILITY_FOUNDRY")
