#!/usr/bin/env python3
from __future__ import annotations
import hashlib,importlib.util,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BINDER=ROOT/"dev-hub/bin/task-contract-binder.py"
ROLES=ROOT/"dev-hub/config/guardian-role-contracts.v1.json"
PILOT=ROOT/"dev-hub/bin/run-collector-knowledge-v1-pilot-via-chacha-dev.sh"

spec=importlib.util.spec_from_file_location("v826_binder",BINDER)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

graph={
 "schema":"chacha.dev/task-graph/v1",
 "project":"wfgg-radar",
 "transition":"OPERATE->OPERATE",
 "tasks":[
  {"id":"install","owner_role":"collector-runtime-agent","permission":"workspace-write",
   "capabilities":["collector-knowledge-control"],"depends_on":[]},
  {"id":"probe","owner_role":"sre-observability-agent","permission":"read",
   "capabilities":["collector-knowledge-control"],"depends_on":["install"]},
  {"id":"query","owner_role":"collector-intelligence-agent","permission":"read",
   "capabilities":["collector-knowledge-inspect"],"depends_on":[]}
 ]
}
roles=json.loads(ROLES.read_text(encoding="utf-8"))
bound=mod.bind_graph(graph,{"contracts":[]},{"contracts":[]},roles)
assert bound["dispatch_allowed"] is True,bound
gbatch=bound["guardian_binding"]
assert gbatch["all_tasks_bound"] is True,gbatch
assert gbatch["blocked_task_count"]==0,gbatch

for task in bound["tasks"]:
    gb=task["guardian_binding"]
    assert gb["mode"]=="STATIC_ROLE",(task["id"],gb)
    assert gb["policy_contract_ref"]=="role:__agent__",(task["id"],gb)
    assert gb["subject_role"].endswith("-agent"),(task["id"],gb)
    base={k:v for k,v in gb.items() if k!="binding_digest"}
    raw=json.dumps(base,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    assert gb["binding_digest"]=="sha256:"+hashlib.sha256(raw).hexdigest(),(task["id"],gb)

agent_role=next(x for x in roles["contracts"] if x.get("contract_id")=="role:__agent__")
assert "workspace-write" in agent_role["allowed_permissions"],agent_role
assert "DISPATCH_TASK" in agent_role["allowed_actions"],agent_role
assert "production-deploy" not in agent_role["allowed_permissions"],agent_role

script=PILOT.read_text(encoding="utf-8")
for marker in [
 "collector-runtime-agent",
 "sre-observability-agent",
 "collector-intelligence-agent",
 "task-contract-binder.py",
 "COLLECTOR_KNOWLEDGE_BOOTSTRAP_GUARDIAN_BINDING=PASS",
 "COLLECTOR_KNOWLEDGE_QUERY_GUARDIAN_BINDING=PASS",
 "PRODUCTION_DEPLOYMENT=NO",
 "LASTWAR_GAME_CONNECTION=NONE",
 "COLLECTOR_KNOWLEDGE_RADAR_PRODUCTION_MUTATION=NO",
 "COLLECTOR_KNOWLEDGE_LASTWAR_MUTATION=NO",
]:
    assert marker in script,marker

print("CHACHA_DEV_V826_COLLECTOR_AGENT_ROLE_BINDING=PASS")
print("CHACHA_DEV_V826_GUARDIAN_BINDING_DIGEST=PASS")
print("CHACHA_DEV_V826_WORKSPACE_WRITE_WITHIN_AGENT_ROLE=PASS")
print("CHACHA_DEV_V826_PRODUCTION_PERMISSION_NOT_GRANTED=PASS")
print("CHACHA_DEV_V826_QUERY_AND_PROBE_BOUND=PASS")
print("CHACHA_DEV_V826_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
