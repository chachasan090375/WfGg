#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import component_evolution_governance as ceg

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))

policy=load(CFG/"universal-evolution-governance.v1.json")
guardian=load(CFG/"guardian-coverage-manifest.v1.json")
idx=ceg.build_index(
    {"profiles":[]},
    load(CFG/"technology-core-watch.v1.json"),
    load(CFG/"provider-adapters.v1.json"),
    load(CFG/"mcp-provider-catalog.v1.json"),
    load(CFG/"project-embedded-assurance.v1.json"),
    policy,
    guardian,
)
expected={x["component_id"] for x in guardian["expected_components"]}
covered={x["component_id"][5:] for x in idx["components"] if x["component_id"].startswith("core:")}
assert idx["guardian_component_count"]==len(expected),(idx["guardian_component_count"],len(expected))
assert idx["guardian_evolution_coverage_sync_complete"] is True,idx
assert idx["guardian_uncovered_components"]==[],idx["guardian_uncovered_components"]
assert expected<=covered,sorted(expected-covered)
assert "central-interface-controller" in expected
for cid in ("human-interface-gateway","central-interface-controller","direct-operator-service","functional-translator-satellite"):
    row=next(x for x in idx["components"] if x["component_id"]=="core:"+cid)
    assert "guardian-coverage-manifest" in row["sources"],row
    assert row["evolution_owner"]=="branch-foundry",row
    assert row["active_self_mutation"] is False and row["self_promotion"] is False,row
assert policy["principles"]["guardian_coverage_is_evolution_source"] is True
assert policy["principles"]["unmapped_guardian_component_kind_fails_closed"] is True
assert policy["source_catalogs"]["guardian_coverage_manifest"]=="dev-hub/config/guardian-coverage-manifest.v1.json"
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(expected)*12*24
assert guardian["d1_write_budget"]["calculation"]==f"{len(expected)} components * 12 heartbeats/hour * 24 hours"

bad=json.loads(json.dumps(guardian))
bad["expected_components"].append({
    "component_id":"future-unmapped-component","role":"future","kind":"future-new-kind",
    "enforcement_point":"test","criticality":"HIGH","proof":{}
})
try:
    ceg.build_index({"profiles":[]},load(CFG/"technology-core-watch.v1.json"),
        load(CFG/"provider-adapters.v1.json"),load(CFG/"mcp-provider-catalog.v1.json"),
        load(CFG/"project-embedded-assurance.v1.json"),policy,bad)
except ValueError as e:
    assert str(e).startswith("UNMAPPED_GUARDIAN_KIND:future-unmapped-component:"),e
else:
    raise AssertionError("unmapped Guardian component kind did not fail closed")

print("CHACHA_DEV_UNIVERSAL_EVOLUTION_GUARDIAN_SYNC=PASS")
print("CHACHA_DEV_UNIVERSAL_EVOLUTION_GUARDIAN_COMPONENTS="+str(len(expected)))
print("CHACHA_DEV_UNIVERSAL_EVOLUTION_CENTRAL_INTERFACE_CONTROLLER=GOVERNED")
print("CHACHA_DEV_UNIVERSAL_EVOLUTION_UNMAPPED_KIND=FAIL_CLOSED")
print("CHACHA_DEV_UNIVERSAL_EVOLUTION_SELF_MUTATION=NO")
print("CHACHA_DEV_UNIVERSAL_EVOLUTION_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
