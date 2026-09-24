#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

objf=load_module("object_factory",ROOT/"dev-hub/bin/object-factory.py")
planner=load_module("project_planner",ROOT/"dev-hub/bin/project-planner.py")

intent={
 "schema":"chacha.dev/project-intent/v1",
 "identity":{"name":"Roster","slug":"roster"},
 "goal":"Manage players and teams",
 "users":{"audiences":["staff"]},
 "channels":["web","api"],
 "criticality":"medium",
 "data":{"stores_data":True,"relational_required":True,"sensitivity":"internal"},
 "constraints":{"production_change_requires_approval":True},
 "non_functional":{"rpo_hours":24,"rto_hours":4},
 "domain_objects":[
   {"id":"player","name":"Player","purpose":"A game player","persistence":"relational",
    "api_exposed":True,"ui_visible":True,
    "fields":[
      {"name":"id","type":"uuid","required":True,"unique":True},
      {"name":"name","type":"string","required":True},
      {"name":"email","type":"string","required":False,"sensitive":True}
    ],
    "relationships":[{"target":"team","type":"many-to-one","required":False}],
    "events":["player.created","player.updated"]
   }
 ]
}
empty={"schema":"chacha.dev/object-registry/v1","objects":[]}
idx=objf.plans_from_intent(intent,empty)
assert idx["object_count"]==1,idx
p=idx["plans"][0]
assert p["action"]=="BUILD",p
assert p["component_factory_handoff_required"] is True,p
assert p["capability_foundry_only_if_gap"] is True,p
assert p["technology_provider_selection_authorized"] is False,p
assert p["production_change_authorized"] is False,p
assert p["contract"]["fields"][2]["sensitive"] is True,p
assert p["outputs_required"]["api_contract"] is True,p
assert p["outputs_required"]["storage_mapping"] is True,p
assert p["outputs_required"]["relationship_contract"] is True,p

qualified={"schema":"chacha.dev/object-registry/v1","objects":[{
 "object_id":"player","state":"QUALIFIED","contract_fingerprint":p["contract_fingerprint"],
 "quality":0.99,"reuse_score":1.0
}]}
reuse=objf.plans_from_intent(intent,qualified)["plans"][0]
assert reuse["action"]=="REUSE",reuse
assert reuse["component_factory_handoff_required"] is False,reuse
assert reuse["selected_existing"]["object_id"]=="player",reuse

registry=json.loads((ROOT/"dev-hub/config/capability-registry.v1.json").read_text(encoding="utf-8"))
paths=json.loads((ROOT/"dev-hub/config/golden-paths.v1.json").read_text(encoding="utf-8"))
plan=planner.make_plan(intent,registry,paths)
assert plan["object_factory"]["required"] is True,plan
assert len(plan["object_factory"]["handoffs"])==1,plan
h=plan["object_factory"]["handoffs"][0]
assert h["owner"]=="component-factory",h
assert h["architecture_owner"]=="chacha-dev-architect",h
assert h["capability_gap_owner"]=="capability-foundry",h
assert h["must_complete_before_code_generation"] is True,h
assert any(x["id"]=="object-factory" for x in plan["capabilities"]),plan

missing=json.loads(json.dumps(intent))
missing.pop("domain_objects")
blocked=planner.make_plan(missing,registry,paths)
decision=next(x for x in blocked["decisions"] if x["id"]=="OBJECT_MODEL")
assert decision["status"]=="NEEDS_INPUT",decision
assert blocked["readiness"]["code_generation_allowed"] is False,blocked
assert "decision:OBJECT_MODEL" in blocked["readiness"]["blocking_reasons"],blocked

schema=json.loads((ROOT/"dev-hub/schemas/project-intent-v1.schema.json").read_text(encoding="utf-8"))
assert "domain_objects" in schema["properties"],schema

guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
assert any(x["component_id"]=="object-factory" for x in guardian["expected_components"]),guardian
roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:object-factory")
assert "DIRECT_DATABASE_MUTATION" in role["forbidden_actions"],role
assert "SELECT_PRODUCTION_PROVIDER" in role["forbidden_actions"],role

print("CHACHA_DEV_V770_OBJECT_FACTORY=PASS")
print("OBJECT_FACTORY_BUILD=PASS")
print("OBJECT_FACTORY_REUSE=PASS")
print("OBJECT_FACTORY_PLANNER_INTEGRATION=PASS")
print("OBJECT_MODEL_MISSING_BLOCKS_CODE_GENERATION=YES")
print("OBJECT_FACTORY_COMPONENT_OWNER=component-factory")
print("OBJECT_FACTORY_ARCHITECTURE_OWNER=chacha-dev-architect")
print("OBJECT_FACTORY_CAPABILITY_GAP_OWNER=capability-foundry")
print("OBJECT_FACTORY_PRODUCTION_CHANGE_AUTHORITY=NO")
print("OBJECT_FACTORY_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
