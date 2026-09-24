#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")


spec=importlib.util.spec_from_file_location("v640_closure",BIN/"capability-foundry-closure.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

policy=load(CFG/"capability-foundry-closure.v1.json")
caps=load(CFG/"capability-registry.v1.json")
providers=load(CFG/"provider-adapters.v1.json")


def foundry(capability,candidates):
    return {
      "schema":"chacha.dev/capability-foundry-plan/v1",
      "project_id":"v640-test-project",
      "plans":[{
        "capability":capability,
        "already_registered":False,
        "owner_domain":"domain-v640-test",
        "technology_candidates":candidates,
        "technology_watch":{"consulted":True,"automatic_external_spend_eur":0},
        "state":"PROJECT_LOCAL_PILOT"
      }],
      "promotion_requires_qualification":True
    }


# Existing ENABLED read-only provider: safe project-local auto-closure.
safe=foundry("v640-browser-proof",[
  {"provider_id":"playwright-mcp","external_spend_eur":0}
])
safe_plan=mod.build_plan(safe,caps,providers,policy)
row=safe_plan["plans"][0]
assert row["state"]=="PROJECT_LOCAL_READY",row
assert row["selected_provider"]=="playwright-mcp",row
assert row["selected_adapter"]=="playwright-mcp-adapter",row
assert row["selected_adapter_status"]=="ENABLED",row
assert row["production_capable"] is False,row
assert row["same_project_resume_allowed"] is True,row
assert row["durable_adoption_requires_human_approval"] is False,row
assert safe_plan["summary"]["build_required_count"]==0,safe_plan
assert safe_plan["automatic_external_spend_eur"]==0,safe_plan
overlay=safe_plan["capability_overlay"]["capabilities"]["v640-browser-proof"]
assert overlay["providers"][0]["id"]=="playwright-mcp",overlay
assert overlay["providers"][0]["status"]=="PILOT",overlay

# Non-zero spend must never auto-close.
paid=foundry("v640-paid-proof",[
  {"provider_id":"playwright-mcp","external_spend_eur":1.0}
])
paid_row=mod.build_plan(paid,caps,providers,policy)["plans"][0]
assert paid_row["state"]=="BUILD_REQUIRED",paid_row
assert "NONZERO_EXTERNAL_SPEND" in paid_row["evaluated_candidates"][0]["reason_codes"],paid_row

# New credential/identity boundary must never auto-close.
credential=foundry("v640-credential-proof",[
  {"provider_id":"playwright-mcp","external_spend_eur":0,"new_credentials_required":True}
])
credential_row=mod.build_plan(credential,caps,providers,policy)["plans"][0]
assert credential_row["state"]=="BUILD_REQUIRED",credential_row
assert "NEW_CREDENTIAL_BOUNDARY" in credential_row["evaluated_candidates"][0]["reason_codes"],credential_row

# Known provider whose adapter is not ENABLED must stay build/qualification required.
not_enabled=foundry("v640-antigravity-proof",[
  {"provider_id":"antigravity","external_spend_eur":0}
])
ne_row=mod.build_plan(not_enabled,caps,providers,policy)["plans"][0]
assert ne_row["state"]=="BUILD_REQUIRED",ne_row
assert "ADAPTER_NOT_ENABLED" in ne_row["evaluated_candidates"][0]["reason_codes"],ne_row

# Unknown provider cannot be invented by the Foundry.
unknown=foundry("v640-unknown-proof",[
  {"provider_id":"made-up-provider","external_spend_eur":0}
])
un_row=mod.build_plan(unknown,caps,providers,policy)["plans"][0]
assert un_row["state"]=="BUILD_REQUIRED",un_row
assert "PROVIDER_NOT_REGISTERED" in un_row["evaluated_candidates"][0]["reason_codes"],un_row

# Durable adoption of a non-production capability requires verified project success
# but no human approval.
with tempfile.TemporaryDirectory(prefix="v640-adopt-") as td:
    td=Path(td)
    registry=td/"capabilities.json"
    receipt=td/"receipt.json"
    save(registry,caps)
    verification={
      "schema":"chacha.dev/capability-adoption-evidence/v1",
      "status":"PASS",
      "project_id":"v640-test-project",
      "capability":"v640-browser-proof",
      "provider":"playwright-mcp",
      "project_success":True,
      "approvals":[]
    }
    rec=mod.apply_adoption(
      registry,safe_plan,"v640-browser-proof",verification,policy,
      actor="central-orchestrator",approval_id=None,receipt_path=receipt
    )
    assert rec["status"]=="COMMITTED",rec
    assert rec["applied"] is True,rec
    durable=load(registry)["capabilities"]["v640-browser-proof"]
    assert durable["providers"][0]["status"]=="ADOPT",durable
    assert durable["providers"][0]["id"]=="playwright-mcp",durable

# Production-capable existing provider may be project-local, but durable ADOPT
# requires a separate human capability-production-adopt approval.
prod=foundry("v640-production-proof",[
  {"provider_id":"cloudflare-pages-production","external_spend_eur":0}
])
prod_plan=mod.build_plan(prod,caps,providers,policy)
prod_row=prod_plan["plans"][0]
assert prod_row["state"]=="PROJECT_LOCAL_READY",prod_row
assert prod_row["production_capable"] is True,prod_row
assert prod_row["durable_adoption_requires_human_approval"] is True,prod_row

with tempfile.TemporaryDirectory(prefix="v640-prod-") as td:
    td=Path(td)
    registry=td/"capabilities.json";receipt=td/"receipt.json"
    save(registry,caps)
    verification={
      "schema":"chacha.dev/capability-adoption-evidence/v1",
      "status":"PASS","project_id":"v640-test-project",
      "capability":"v640-production-proof",
      "provider":"cloudflare-pages-production",
      "project_success":True,"approvals":[]
    }
    blocked=False
    try:
        mod.apply_adoption(
          registry,prod_plan,"v640-production-proof",verification,policy,
          actor="central-orchestrator",approval_id=None,receipt_path=receipt
        )
    except SystemExit as exc:
        blocked=str(exc)=="CAPABILITY_ADOPTION_HUMAN_APPROVAL_REQUIRED"
    assert blocked

    verification["approvals"]=[{
      "id":"v640-human-adopt",
      "type":"capability-production-adopt",
      "capability":"v640-production-proof",
      "target_status":"ADOPT",
      "actor":"cedric"
    }]
    rec=mod.apply_adoption(
      registry,prod_plan,"v640-production-proof",verification,policy,
      actor="cedric",approval_id="v640-human-adopt",receipt_path=receipt
    )
    assert rec["status"]=="COMMITTED",rec
    assert rec["approval_id"]=="v640-human-adopt",rec

print("CHACHA_DEV_V640_EXISTING_ENABLED_PROVIDER_AUTO_CLOSURE=PASS")
print("CHACHA_DEV_V640_NONZERO_SPEND_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V640_CREDENTIAL_BOUNDARY_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V640_ADAPTER_NOT_ENABLED_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V640_UNKNOWN_PROVIDER_INVENTION=NO")
print("CHACHA_DEV_V640_VERIFIED_PROJECT_SUCCESS_BEFORE_ADOPT=PASS")
print("CHACHA_DEV_V640_PRODUCTION_CAPABILITY_HUMAN_ADOPTION_BOUNDARY=PASS")
print("CHACHA_DEV_V640_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
