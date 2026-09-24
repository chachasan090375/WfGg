#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"

def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))

common=load(CFG/"specialist-authority-common.v1.json")
curator=load(CFG/"curator-authority.v1.json")
bastion=load(CFG/"bastion-authority.v1.json")
intendant=load(CFG/"intendant-authority.v1.json")
embedded=load(CFG/"project-embedded-assurance.v1.json")
roles=load(CFG/"guardian-role-contracts.v1.json")
coverage=load(CFG/"guardian-coverage-manifest.v1.json")
control=load(CFG/"project-control.v1.json")
release=load(CFG/"compromise-release-gate.v1.json")

assert common["review_contract"]["exact_project_required"] is True
assert common["review_contract"]["exact_revision_required"] is True
assert common["review_contract"]["exact_compromise_digest_required"] is True
assert common["governance"]["direct_application_mutation"] is False
assert common["governance"]["direct_architecture_mutation"] is False
assert common["governance"]["reviews_publish_to_assurance_exchange"] is True

assert curator["role"]=="curator" and curator["scope"]=="VISUAL_UX"
assert bastion["role"]=="bastion" and bastion["scope"]=="SECURITY_DATA"
assert intendant["role"]=="intendant" and intendant["scope"]=="COST_RESOURCES"
assert curator["direct_mutation"] is False
assert bastion["direct_mutation"] is False
assert intendant["direct_mutation"] is False

ir=bastion["incident_response"]
assert ir["actions"]==["OBSERVE","CONTAIN","QUARANTINE","REVOKE","SURVIVAL","E_STOP"]
assert ir["local_project_attack_max_without_corroboration"]=="QUARANTINE"
assert ir["e_stop_requires"]["minimum_independent_corroborations"]==2
assert set(ir["e_stop_requires"]["allowed_scopes"])=={"PLATFORM","CORE"}
assert ir["e_stop_requires"]["out_of_band_controller"] is True
assert ir["failover"]["status"]=="RESERVED_INACTIVE"
assert ir["failover"]["future_architecture"]=="ACTIVE_PASSIVE_HA"
assert ir["failover"]["compromised_state_replication_forbidden"] is True

for role in ["curator","bastion","intendant"]:
    ep=embedded["transport"]["role_endpoints"][role]
    assert ep["base_key"]==role+"_url",ep
    assert ep["path"]=="/v1/project-events",ep
    assert embedded["central_authority"][role+"_status"]=="ACTIVE"
    assert embedded["central_authority"][role+"_url"].startswith("https://chacha-dev-"+role+"."),embedded["central_authority"][role+"_url"]

assert "visual-health" in embedded["local_agents"]["curator"]["allowed_event_types"]
assert "security-health" in embedded["local_agents"]["bastion"]["allowed_event_types"]
assert "resource-health" in embedded["local_agents"]["intendant"]["allowed_event_types"]
assert embedded["communication"]["specialist_authorities_publish_reviews_to_exchange"] is True
assert embedded["communication"]["local_specialist_probes_report_to_specialist_authorities"] is True

core=(ROOT/"dev-hub/specialists/core.js").read_text(encoding="utf-8")
exchange=(ROOT/"dev-hub/assurance-exchange/worker.js").read_text(encoding="utf-8")
identity=(BIN/"project-assurance-identity-manager.py").read_text(encoding="utf-8")
client=(BIN/"specialist-authority-client.py").read_text(encoding="utf-8")
orch=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
bastion_controller=(BIN/"bastion-incident-response-controller.py").read_text(encoding="utf-8")
bastion_timer=(ROOT/"dev-hub/systemd/chacha-dev-bastion-incident-response.timer").read_text(encoding="utf-8")

for marker in [
  "/v1/project-assurance-identities/register","/v1/project-events","/v1/review","/v1/reviews/",
  "implementation_verified","compromise_digest","ASSURANCE_EXCHANGE_SERVICE",
  "bastionAction","/v1/incidents/escalate","/v1/incidents/directives",
  'failover_status:"RESERVED_INACTIVE"'
]:
    assert marker in core,marker

for marker in [
  "CURATOR_SERVICE","BASTION_SERVICE","INTENDANT_SERVICE",
  "/v1/specialist-reviews","source_reverified:true",
  "specialist_review_source_reverification:true"
]:
    assert marker in exchange,marker

for marker in [
  "--specialist-client","--curator-policy","--bastion-policy","--intendant-policy",
  "CURATOR_REGISTRATION=PASS","BASTION_REGISTRATION=PASS","INTENDANT_REGISTRATION=PASS",
  "specialist_authority_identities_active"
]:
    assert marker in identity,marker

for marker in [
  "register-project-assurance-identity","review","directives","escalate"
]:
    assert marker in client,marker

assert any(v in orch for v in ['"version":"6.35.0"','"version":"6.40.0"','"version":"6.41.0"','"version":"6.42.0"','"version":"6.43.0"','"version":"6.44.0"','"version":"6.45.0"','"version":"6.46.0"','"version":"6.47.0"','"version":"6.48.0"','"version":"6.49.0"','"version":"6.50.0"','"version":"6.51.0"','"version":"6.52.0"','"version":"6.53.0"','"version":"6.54.0"','"version":"6.55.0"','"version":"6.56.0"','"version":"6.57.0"','"version":"6.58.0"','"version":"6.59.0"','"version":"6.60.0"','"version":"6.61.0"','"version":"6.62.0"','"version":"6.63.0"','"version":"6.64.0"'])
for marker in [
  '"--specialist-client",bin_dir/"specialist-authority-client.py"',
  '"--curator-policy",cfg/"curator-runtime-policy.v1.json"',
  '"--bastion-policy",cfg/"bastion-runtime-policy.v1.json"',
  '"--intendant-policy",cfg/"intendant-runtime-policy.v1.json"',
  '"specialist_authority_identities_active"'
]:
    assert marker in orch,marker

contract_ids={x["contract_id"] for x in roles["contracts"]}
assert {"role:curator","role:bastion","role:intendant"}.issubset(contract_ids),contract_ids
brole=next(x for x in roles["contracts"] if x["contract_id"]=="role:bastion")
assert "ISSUE_CONTAINMENT" in brole["allowed_actions"]
assert "ISSUE_QUARANTINE" in brole["allowed_actions"]
assert "ISSUE_REVOCATION" in brole["allowed_actions"]
assert "REQUEST_EMERGENCY_CONTROL" in brole["allowed_actions"]
assert "FINAL_ARCHITECTURE_DECISION" in brole["forbidden_actions"]

components={x["component_id"] for x in coverage["expected_components"]}
assert {"curator-central-authority","bastion-central-authority","intendant-central-authority"}.issubset(components),components

assert control["principles"]["curator_central_authority_external"] is True
assert control["principles"]["bastion_central_authority_external"] is True
assert control["principles"]["intendant_central_authority_external"] is True
assert control["principles"]["specialist_reviews_are_source_reverified_by_assurance_exchange"] is True
assert control["principles"]["bastion_failover_reserved_until_active_passive_ha_exists"] is True
assert control["principles"]["compromised_state_must_never_be_blindly_replicated_to_future_passive"] is True

assert len(release["required_agents"])==7
assert {x["id"] for x in release["required_agents"]}.issuperset({"curator","bastion","intendant"})

for marker in ["CONTAIN","QUARANTINE","REVOKE","SURVIVAL","E_STOP","FAILOVER_RESERVED_INACTIVE"]:
    assert marker in bastion_controller,marker
assert "OnUnitActiveSec=10s" in bastion_timer
assert "CHACHA_DEV_BASTION_SURVIVAL_MODE_ACTIVE" in orch
assert "CHACHA_DEV_BASTION_PROJECT_BLOCKED" in orch
assert '"bastion_failover_status":"RESERVED_INACTIVE"' in orch

print("CHACHA_DEV_V635_CURATOR_CENTRAL_AUTHORITY=PASS")
print("CHACHA_DEV_V635_BASTION_CENTRAL_AUTHORITY=PASS")
print("CHACHA_DEV_V635_INTENDANT_CENTRAL_AUTHORITY=PASS")
print("CHACHA_DEV_V635_SPECIALIST_PROJECT_IDENTITIES=PASS")
print("CHACHA_DEV_V635_SPECIALIST_REVIEWS_EXCHANGE_REVERIFY=PASS")
print("CHACHA_DEV_V635_BASTION_CONTAINMENT_CORE=PASS")
print("CHACHA_DEV_V635_BASTION_RESPONSE_CONTROLLER=PASS")
print("CHACHA_DEV_V635_BASTION_SURVIVAL_GUARD=PASS")
print("CHACHA_DEV_V635_BASTION_EMERGENCY_CORROBORATION_GUARD=PASS")
print("CHACHA_DEV_V635_FAILOVER_RESERVED_INACTIVE=PASS")
print("CHACHA_DEV_V635_COMPROMISED_STATE_REPLICATION=FORBIDDEN")
print("CHACHA_DEV_V635_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V635_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
