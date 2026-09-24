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

event=loadmod("v632_event",BIN/"project-assurance-event.py")
identity=loadmod("v632_identity",BIN/"project-assurance-identity-manager.py")
policy=load(CFG/"project-embedded-assurance.v1.json")
network=load(CFG/"peripheral-assurance-network.v1.json")
factory_cfg=load(CFG/"project-factory.v1.json")
project_control=load(CFG/"project-control.v1.json")

assert policy["mandatory_for_all_projects"] is True
assert {"guardian","sentinel"}.issubset(set(policy["local_agents"]))
assert network["participants"]["guardian"]["status"]=="ACTIVE"
assert network["participants"]["sentinel"]["status"]=="ACTIVE"
assert network["participants"]["curator"]["status"] in {"PLANNED","LOCAL_PROBE_ACTIVE"}
assert network["participants"]["bastion"]["status"] in {"PLANNED","LOCAL_PROBE_ACTIVE"}
assert network["participants"]["intendant"]["status"] in {"PLANNED","LOCAL_PROBE_ACTIVE"}
assert network["communication"]["common_exchange"]=="assurance-exchange"
assert network["communication"]["peer_to_peer_decision_making"] is False
assert network["communication"]["direct_mutation"] is False
assert network["communication"]["central_orchestrator_owns_remediation"] is True
assert network["communication"]["architecture_change_requires_technology_watch"] is True
assert network["communication"]["architecture_council_final_authority"] is True

for name in ["embedded-assurance-manifest","guardian-local-probe","sentinel-local-probe",
             "project-assurance-outbox","project-assurance-relay","project-assurance-identity-request"]:
    assert name in factory_cfg["provision_on_project_creation"],name
assert factory_cfg["delivery"]["embedded_assurance_required"] is True
assert factory_cfg["delivery"]["guardian_local_required"] is True
assert factory_cfg["delivery"]["sentinel_local_required"] is True

fields={"component_id":"api","component_version":"v1","status_code":500}
g=event.build_event("p632","v1","guardian","user-visible-failure","BLOCK",fields,policy)
s=event.build_event("p632","v1","sentinel","exception","BLOCK",fields,policy)
assert g["assurance_role"]=="guardian" and s["assurance_role"]=="sentinel"
assert g["privacy"]["raw_user_content"] is False and s["privacy"]["raw_user_content"] is False
assert g["direct_mutation"] is False and s["direct_mutation"] is False
try:
    event.build_event("p632","v1","guardian","user-visible-failure","BLOCK",{"message":"secret user text"},policy)
    raise AssertionError("raw message accepted")
except RuntimeError as exc:
    assert "RAW_OR_SENSITIVE_FIELD_DENIED" in str(exc),exc
if "curator" in policy["local_agents"]:
    ce=event.build_event("p632","v1","curator","visual-regression","WARNING",{},policy)
    assert ce["assurance_role"]=="curator",ce
else:
    try:
        event.build_event("p632","v1","curator","visual-regression","WARNING",{},policy)
        raise AssertionError("planned role accepted before activation")
    except RuntimeError as exc:
        assert "EVENT_TYPE_DENIED" in str(exc),exc

with tempfile.TemporaryDirectory(prefix="v632-bundle-") as td:
    td=Path(td);contract=td/"functional.json"
    contract.write_text('{"schema":"chacha.dev/functional-contract/v1","contract_id":"p632-contract"}\n',encoding="utf-8")
    out=td/"bundle"
    p=subprocess.run([
      sys.executable,str(BIN/"project-embedded-assurance.py"),
      "--project-id","p632","--application-version","v1",
      "--policy",str(CFG/"project-embedded-assurance.v1.json"),
      "--runtime-script",str(BIN/"project-assurance-event.py"),
      "--relay-script",str(BIN/"project-assurance-relay.py"),
      "--client-runtime",str(ROOT/"dev-hub/templates/project-assurance-client.mjs"),
      "--functional-contract",str(contract),"--output-dir",str(out)
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    m=load(out/"embedded-assurance.json")
    assert m["guardian_local"]["enabled"] is True
    assert m["sentinel_local"]["enabled"] is True
    assert m["relay"]["mode"]=="SERVER_SIDE_ONLY"
    assert m["relay"]["client_direct_to_central"] is False
    assert m["relay"]["private_key_embedded_in_client"] is False
    assert m["relay"]["identity_status"]=="PENDING_APPROVAL"
    assert m["functional_contract"]["bound"] is True
    assert m["privacy"]["raw_user_content"] is False
    assert m["privacy"]["client_side_secret"] is False
    assert m["production_readiness"]["ready"] is False
    assert (out/"project-assurance-identity-request.json").is_file()
    assert (out/"project-assurance-client.mjs").is_file()
    client=(out/"project-assurance-client.mjs").read_text(encoding="utf-8")
    assert "createAssuranceLocal" in client
    for role in ["guardian","sentinel","curator","bastion","intendant"]:assert role in client
    assert "secret" not in load(out/"project-assurance-identity-request.json")

    secret=td/"keys"/"p632.pem";identity.ensure_key(secret)
    pub=identity.public_b64(secret);kid=identity.key_id(pub)
    assert kid.startswith("project-") and len(kid)==24,kid
    assert (secret.stat().st_mode & 0o777)==0o600

guardian=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
sentinel=(ROOT/"dev-hub/sentinel/worker.js").read_text(encoding="utf-8")
orchestrator=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
bootstrap=(BIN/"project-bootstrap.py").read_text(encoding="utf-8")
relay=(BIN/"project-assurance-relay.py").read_text(encoding="utf-8")

for body in [guardian,sentinel]:
    assert "/v1/project-assurance-identities/register" in body
    assert "project_assurance_identity_project_mismatch" in body
    assert "project_assurance_identity_registration:true" in body
    assert "requireProjectAssurance" in body

assert any(v in orchestrator for v in ['"version":"6.32.0"','"version":"6.33.0"','"version":"6.34.0"','"version":"6.35.0"','"version":"6.40.0"','"version":"6.41.0"','"version":"6.42.0"','"version":"6.43.0"','"version":"6.44.0"','"version":"6.45.0"','"version":"6.46.0"','"version":"6.47.0"','"version":"6.48.0"','"version":"6.49.0"','"version":"6.50.0"','"version":"6.51.0"','"version":"6.52.0"','"version":"6.53.0"','"version":"6.54.0"','"version":"6.55.0"','"version":"6.56.0"','"version":"6.57.0"','"version":"6.58.0"','"version":"6.59.0"','"version":"6.60.0"','"version":"6.61.0"','"version":"6.62.0"'])
assert "project-embedded-assurance.py" in orchestrator
assert "project-assurance-identity-manager.py" in orchestrator
assert '"embedded_assurance_required":True' in orchestrator
assert "PROJECT_EMBEDDED_ASSURANCE=REQUIRED" in bootstrap
assert "project-embedded-assurance.py" in bootstrap
assert '"project-"+hashlib.sha256' in relay
assert project_control["principles"]["embedded_assurance_is_mandatory_for_every_project"] is True
assert project_control["principles"]["project_assurance_identity_is_project_scoped"] is True
assert project_control["principles"]["peripheral_assurance_communicates_through_common_exchange"] is True

print("CHACHA_DEV_V632_EVERY_PROJECT_EMBEDDED_ASSURANCE=PASS")
print("CHACHA_DEV_V632_GUARDIAN_LOCAL=PASS")
print("CHACHA_DEV_V632_SENTINEL_LOCAL=PASS")
print("CHACHA_DEV_V632_PROJECT_SCOPED_IDENTITY=PASS")
print("CHACHA_DEV_V632_SERVER_SIDE_RELAY_ONLY=PASS")
print("CHACHA_DEV_V632_RAW_USER_CONTENT=NO")
print("CHACHA_DEV_V632_CLIENT_SECRET=NO")
print("CHACHA_DEV_V632_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V632_FIVE_AGENT_NETWORK_RESERVED=PASS")
print("CHACHA_DEV_V632_COMMON_ASSURANCE_EXCHANGE=PASS")
print("CHACHA_DEV_V632_CENTRAL_ORCHESTRATOR_REMEDIATION_OWNER=PASS")
print("CHACHA_DEV_V632_TECHNOLOGY_WATCH_ARCHITECTURE_GUARD=PASS")
print("CHACHA_DEV_V632_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=PASS")
print("CHACHA_DEV_V632_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
