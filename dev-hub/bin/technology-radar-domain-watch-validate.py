#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
domain=json.loads((ROOT/"dev-hub/config/domain-orchestration.v1.json").read_text())
econ=json.loads((ROOT/"dev-hub/config/provider-economics.v1.json").read_text())
radar=json.loads((ROOT/"dev-hub/config/technology-radar-domain-watch.v2.json").read_text())
routing=json.loads((ROOT/"dev-hub/config/agent-routing.v1.json").read_text())
caps=json.loads((ROOT/"dev-hub/config/capability-registry.v1.json").read_text())
foundry=json.loads((ROOT/"dev-hub/config/agent-foundry.v1.json").read_text())
factory=json.loads((ROOT/"dev-hub/config/project-factory.v1.json").read_text())
fabric=json.loads((ROOT/"dev-hub/config/knowledge-fabric.v1.json").read_text())
evolution=json.loads((ROOT/"dev-hub/config/self-evolution.v1.json").read_text())

assert domain["schema"]=="chacha.dev/domain-orchestration/v1"
assert econ["schema"]=="chacha.dev/provider-economics/v1"
assert radar["schema"]=="chacha.dev/technology-radar-domain-watch/v2"
assert econ["budget_policy"]["automatic_external_spend_eur"]==0
assert econ["budget_policy"]["paid_provider_requires_human_approval"] is True
assert foundry["schema"]=="chacha.dev/agent-foundry/v1"
assert foundry["mandatory_preflight"] is True
assert foundry["returns_to"]=="chacha-core-orchestrator"
assert factory["application_agnostic"] is True
assert factory["agent_preflight"]["required"] is True
assert fabric["schema"]=="chacha.dev/knowledge-fabric/v1"
assert evolution["schema"]=="chacha.dev/self-evolution/v1"
assert evolution["auto_promotion"]["enabled"] is True
assert domain["preflight"]["first_executable_branch"]=="agent-foundry"
assert domain["preflight"]["domain_dispatch_before_foundry"] is False
assert radar["mode"]=="ALL_PLATFORM_DOMAINS_AND_CORE"
assert radar["governance"]["auto_paid_provider_allowed"] is False
assert radar["governance"]["production_change_allowed"] is True
assert radar["governance"]["production_change_scope"]=="reversible-policy-qualified-self-upgrade-only"

required={"development","documentation","ui-layout","graphics","animation","cybersecurity","qa","platform-release","knowledge-research","translation","publication","assembly"}
assert required <= set(domain["domains"]), sorted(required-set(domain["domains"]))
assert set(domain["domains"]) == set(radar["watches"]["domains"])

roles=routing["roles"]
for role in ("graphics-specialist","animation-specialist","ui-layout-specialist","technology-watch-agent","translation-specialist","publication-specialist","integration-architect","agent-foundry-architect"):
    assert role in roles,role

for capability in ("graphics-pipeline","animation-pipeline","asset-analysis","ui-layout-review","prose-lint","translation","publication-writing","architecture-optimization","project-factory","agent-needs-analysis","agent-blueprint","agent-evaluation","agent-lifecycle","agent-composition"):
    assert capability in caps["capabilities"],capability

for d,spec in domain["domains"].items():
    assert spec.get("orchestrator"),d
    assert spec.get("capabilities"),d
    for role in spec.get("roles") or []:
        assert role in roles,(d,role)

print("CHACHA_DEV_V6_DOMAIN_ORCHESTRATION=PASS")
print("CHACHA_DEV_V6_DOMAIN_COUNT="+str(len(domain["domains"])))
print("CHACHA_DEV_V6_ZERO_INCREMENTAL_COST_DEFAULT=YES")
print("CHACHA_DEV_V6_TECH_RADAR_ALL_DOMAINS=YES")
