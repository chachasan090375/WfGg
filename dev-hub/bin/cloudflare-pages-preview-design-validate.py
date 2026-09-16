#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "dev-hub/config/cloudflare-pages-preview-contract.v1.json"
ADAPTERS = ROOT / "dev-hub/config/provider-adapters.v1.json"
CAPS = ROOT / "dev-hub/config/capability-registry.v1.json"
EVIDENCE = ROOT / "dev-hub/evidence/cloudflare-pages-preview-design-2026-09-16.json"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


c = load(CONTRACT)
a = load(ADAPTERS)
r = load(CAPS)
e = load(EVIDENCE)

assert c["schema"] == "chacha.dev/cloudflare-pages-preview-contract/v1"
assert c["provider_id"] == "cloudflare-pages"
assert c["adapter_id"] == "cloudflare-pages-adapter"
assert c["runtime_status"] == "DESIGNED"
assert c["decision"] == "ADOPT"
assert c["delivery_model"]["preferred_mode"] == "git-integration"
assert c["delivery_model"]["qualified_modes"] == []
assert c["delivery_model"]["git_integration"]["unique_preview_url_required"] is True
assert c["delivery_model"]["git_integration"]["branch_alias_is_authoritative"] is False
assert c["delivery_model"]["wrangler_direct"]["runtime_enabled"] is False
assert c["intent_contract"]["future_manifest_capability"] == "cloud-preview-static"
assert c["intent_contract"]["permission"] == "preview-deploy"
assert c["intent_contract"]["manifest_declares_provider"] is False
assert c["intent_contract"]["task_can_choose_account_id"] is False
assert c["intent_contract"]["task_can_choose_api_token"] is False
assert c["intent_contract"]["task_can_choose_project_name"] is False
assert c["output_contract"]["provider_result_trust"] == "UNVERIFIED"
assert c["output_contract"]["verification_broker_required"] is True
assert c["security"]["preview_only"] is True
for denied in (
    "production_deploy", "production_branch", "dns_mutation", "custom_domain_mutation",
    "project_create_delete", "project_settings_mutation", "environment_secret_mutation",
    "workers_mutation", "d1_mutation", "r2_mutation", "deployment_delete", "cross_account"
):
    assert c["security"][denied] is False, denied
assert c["downstream_verification"]["browser_source_provider"] == "chrome-devtools-mcp"
assert c["downstream_verification"]["browser_independent_provider"] == "playwright-mcp"
assert c["downstream_verification"]["target_must_equal_immutable_preview_url"] is True
assert c["admission"]["automatic_promotion"] is False
assert c["admission"]["next_transition"] == "DESIGNED->CONTRACT_OK"

p = a["providers"]["cloudflare-pages"]
assert p["adapter"] == "cloudflare-pages-adapter"
assert p["execution"] == "external"
ad = a["adapters"]["cloudflare-pages-adapter"]
assert ad["status"] == "DESIGNED"
assert ad["executable"] is None
assert "preview-deploy" in ad["supports"]

cap = r["capabilities"]["cloud-deploy-static"]
assert any(x.get("id") == "cloudflare-pages" for x in cap["providers"])

assert e["schema"] == "chacha.dev/cloudflare-pages-preview-design-evidence/v1"
assert e["runtime_executed"] is False
assert e["cloudflare_account_touched"] is False
assert e["pages_project_touched"] is False
assert e["production_touched"] is False
assert e["automatic_promotion"] is False
assert "NARROW_PREVIEW_ONLY_ADAPTER_SURFACE" in e["blockers_to_contract_ok"]

print("CLOUDFLARE_PAGES_PREVIEW_DESIGN_VALID state=DESIGNED runtime=false production=false")
