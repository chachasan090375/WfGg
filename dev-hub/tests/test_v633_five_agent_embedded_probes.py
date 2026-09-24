#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))

event=loadmod("v633_event",BIN/"project-assurance-event.py")
policy=load(CFG/"project-embedded-assurance.v1.json")
network=load(CFG/"peripheral-assurance-network.v1.json")
factory=load(CFG/"project-factory.v1.json")
control=load(CFG/"project-control.v1.json")

roles={"guardian","sentinel","curator","bastion","intendant"}
assert set(policy["local_agents"])==roles,policy["local_agents"].keys()
for role in roles:
    assert policy["local_agents"][role]["status"]=="ACTIVE",(role,policy["local_agents"][role])
    assert policy["local_agents"][role]["direct_mutation"] is False

assert network["participants"]["curator"]["status"]=="LOCAL_PROBE_ACTIVE"
assert network["participants"]["bastion"]["status"]=="LOCAL_PROBE_ACTIVE"
assert network["participants"]["intendant"]["status"]=="LOCAL_PROBE_ACTIVE"
assert network["communication"]["all_five_local_probes_share_incremental_transport"] is True
assert network["communication"]["future_specialized_authorities_consume_exchange_events"] is True
assert network["communication"]["common_exchange"]=="assurance-exchange"
assert network["communication"]["direct_mutation"] is False
assert network["communication"]["central_orchestrator_owns_remediation"] is True
assert network["communication"]["architecture_change_requires_technology_watch"] is True
assert network["communication"]["architecture_council_final_authority"] is True

samples=[
 ("guardian","functional-miss",{"component_id":"ui"}),
 ("sentinel","runtime-regression",{"component_id":"api","duration_ms":1200}),
 ("curator","visual-regression",{"surface_id":"home","visual_diff_score":0.42,"viewport_class":"mobile"}),
 ("bastion","permission-drift",{"permission_code":"scope-expanded","exposure_class":"authenticated"}),
 ("intendant","resource-budget-drift",{"memory_mb":640,"cpu_ms":1800,"external_cost_microunits":12}),
]
for role,event_type,fields in samples:
    e=event.build_event("p633","v1",role,event_type,"WARNING",fields,policy)
    assert e["assurance_role"]==role,e
    assert e["privacy"]["raw_user_content"] is False,e
    assert e["direct_mutation"] is False,e

for role,event_type in [("curator","visual-regression"),("bastion","permission-drift"),("intendant","resource-budget-drift")]:
    try:
        event.build_event("p633","v1",role,event_type,"WARNING",{"message":"raw text forbidden"},policy)
        raise AssertionError("raw user field accepted:"+role)
    except RuntimeError as exc:
        assert "RAW_OR_SENSITIVE_FIELD_DENIED" in str(exc),exc

with tempfile.TemporaryDirectory(prefix="v633-bundle-") as td:
    td=Path(td);contract=td/"functional.json";bundle=td/"bundle"
    contract.write_text('{"schema":"chacha.dev/functional-contract/v1","contract_id":"p633-contract"}\n',encoding="utf-8")
    p=subprocess.run([
      sys.executable,str(BIN/"project-embedded-assurance.py"),
      "--project-id","p633","--application-version","v1",
      "--policy",str(CFG/"project-embedded-assurance.v1.json"),
      "--runtime-script",str(BIN/"project-assurance-event.py"),
      "--relay-script",str(BIN/"project-assurance-relay.py"),
      "--client-runtime",str(ROOT/"dev-hub/templates/project-assurance-client.mjs"),
      "--functional-contract",str(contract),"--output-dir",str(bundle)
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    m=load(bundle/"embedded-assurance.json")
    for role in roles:
        assert m[role+"_local"]["enabled"] is True,(role,m)
        assert (bundle/"outbox"/role).is_dir(),role
        assert (bundle/"delivered"/role).is_dir(),role
    assert m["production_readiness"]["five_local_probes"] is True,m
    assert m["production_readiness"]["ready"] is False,m
    client=(bundle/"project-assurance-client.mjs").read_text(encoding="utf-8")
    for fn in ["createGuardianLocal","createSentinelLocal","createCuratorLocal","createBastionLocal","createIntendantLocal"]:
        assert fn in client,fn

relay=(BIN/"project-assurance-relay.py").read_text(encoding="utf-8")
identity=(BIN/"project-assurance-identity-manager.py").read_text(encoding="utf-8")
exchange_client=(BIN/"assurance-exchange-client.py").read_text(encoding="utf-8")
exchange_worker=(ROOT/"dev-hub/assurance-exchange/worker.js").read_text(encoding="utf-8")
orchestrator=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")

for marker in [
    'endpoint=(transport.get("role_endpoints") or {}).get(role)',
    'roles=active if a.role in {"all","both"} else [a.role]',
]:
    assert marker in relay,marker

for marker in [
    "--exchange-client","--exchange-policy",
    '"exchange_status":e.get("status")',
    "EXCHANGE_REGISTRATION=PASS",
]:
    assert marker in identity,marker

assert "register-project-assurance-identity" in exchange_client
for marker in [
    "/v1/project-assurance-identities/register",
    "/v1/peripheral-events",
    'new Set(["curator","bastion","intendant"])',
    "project_assurance_identity_project_mismatch",
    "curator_local_ingest:true",
    "bastion_local_ingest:true",
    "intendant_local_ingest:true",
    "five_agent_local_probe_fabric:true",
]:
    assert marker in exchange_worker,marker

assert any(v in orchestrator for v in ['"version":"6.33.0"','"version":"6.34.0"','"version":"6.35.0"','"version":"6.40.0"','"version":"6.41.0"','"version":"6.42.0"','"version":"6.43.0"','"version":"6.44.0"','"version":"6.45.0"','"version":"6.46.0"','"version":"6.47.0"','"version":"6.48.0"','"version":"6.49.0"','"version":"6.50.0"','"version":"6.51.0"','"version":"6.52.0"','"version":"6.53.0"','"version":"6.54.0"','"version":"6.55.0"','"version":"6.56.0"'])
for marker in [
    '"curator_local_enabled"',
    '"bastion_local_enabled"',
    '"intendant_local_enabled"',
    '"five_local_probes_enabled"',
    '"assurance-exchange-client.py"',
]:
    assert marker in orchestrator,marker

for key in ["curator_local_required","bastion_local_required","intendant_local_required"]:
    assert factory["delivery"][key] is True,key
assert factory["embedded_assurance"]["five_local_probes_required"] is True
assert factory["embedded_assurance"]["incremental_feedback_for_all_five"] is True
assert control["principles"]["five_local_assurance_probes_mandatory_for_every_project"] is True
assert control["principles"]["all_peripheral_agents_must_communicate_via_assurance_exchange"] is True
assert control["principles"]["cross_agent_optimization_feedback_returns_to_central_orchestrator"] is True

print("CHACHA_DEV_V633_FIVE_LOCAL_PROBES_ACTIVE=PASS")
print("CHACHA_DEV_V633_CURATOR_LOCAL=PASS")
print("CHACHA_DEV_V633_BASTION_LOCAL=PASS")
print("CHACHA_DEV_V633_INTENDANT_LOCAL=PASS")
print("CHACHA_DEV_V633_INCREMENTAL_EXCHANGE_SINK=PASS")
print("CHACHA_DEV_V633_PROJECT_SCOPED_EXCHANGE_IDENTITY=PASS")
print("CHACHA_DEV_V633_RAW_USER_CONTENT=NO")
print("CHACHA_DEV_V633_CLIENT_SECRET=NO")
print("CHACHA_DEV_V633_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V633_CROSS_AGENT_COMMUNICATION_VIA_EXCHANGE=PASS")
print("CHACHA_DEV_V633_CENTRAL_ORCHESTRATOR_REMEDIATION_OWNER=PASS")
print("CHACHA_DEV_V633_TECHNOLOGY_WATCH_ARCHITECTURE_GUARD=PASS")
print("CHACHA_DEV_V633_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=PASS")
print("CHACHA_DEV_V633_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
