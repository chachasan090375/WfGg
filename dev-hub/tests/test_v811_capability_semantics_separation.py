#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

spec=importlib.util.spec_from_file_location("v811_orch",ROOT/"dev-hub/bin/autonomous-project-orchestrator.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

sem_path=ROOT/"dev-hub/config/capability-semantics.v1.json"
sem=json.loads(sem_path.read_text(encoding="utf-8"))
features=sem["domain_features"]
assert len(features)==27,len(features)

with tempfile.TemporaryDirectory(prefix="v811-cap-semantics-") as td:
    td=Path(td)
    pre=td/"pre.json";contract=td/"contract.json";caps=td/"caps.json";out=td/"gaps.json"
    pre.write_text(json.dumps({
      "packages":[
        {"domain":"conversation-interface","capabilities":["human-conversation-rendering"]},
        {"domain":"translation","capabilities":["locale-localization"]},
        {"domain":"knowledge-research","capabilities":["web-research","missing-runtime-tool"]}
      ]
    }),encoding="utf-8")
    contract.write_text(json.dumps({"capability_hints":[]}),encoding="utf-8")
    caps.write_text(json.dumps({
      "schema":"chacha.dev/capability-registry/v1",
      "capabilities":{"web-research":{"providers":[{"id":"technology-radar","status":"ADOPT"}]}}
    }),encoding="utf-8")
    mod.capability_gaps(pre,contract,caps,sem_path,"test-project",out)
    x=json.loads(out.read_text(encoding="utf-8"))
    assert x["schema"]=="chacha.dev/capability-gap-classification/v1"
    assert [r["id"] for r in x["missing_capabilities"]]==["missing-runtime-tool"],x
    fm={r["id"]:r for r in x["domain_feature_requirements"]}
    assert fm["human-conversation-rendering"]["classification"]=="REUSABLE",fm
    assert fm["human-conversation-rendering"]["evidence_complete"] is True,fm
    assert fm["locale-localization"]["classification"]=="BUILD_REQUIRED",fm
    assert fm["locale-localization"]["provider_registration_required"] is False,fm
    assert x["summary"]["runtime_provider_gap_count"]==1
    assert x["domain_features_do_not_grant_provider_authority"] is True

    # An explicit runtime build hint remains fail-closed as a provider gap.
    contract.write_text(json.dumps({"capability_hints":[{
      "id":"locale-localization","domain":"translation",
      "build_profile":"structured-read-v1","provider_id":"explicit-provider",
      "adapter_id":"explicit-adapter","execution":"vps","supports":["read"],
      "network_access":False,"credentials_required":False,"production_capable":False,
      "automatic_external_spend_eur":0
    }]}),encoding="utf-8")
    pre.write_text(json.dumps({"packages":[]}),encoding="utf-8")
    mod.capability_gaps(pre,contract,caps,sem_path,"test-project",out)
    y=json.loads(out.read_text(encoding="utf-8"))
    assert len(y["missing_capabilities"])==1,y
    assert y["missing_capabilities"][0]["id"]=="locale-localization"
    assert y["missing_capabilities"][0]["kind"]=="runtime_provider"
    assert not y["domain_feature_requirements"]

src=(ROOT/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert 'cfg/"capability-semantics.v1.json"' in src
assert '"domain_feature_requirements"' in src
assert '"runtime_provider_gap_count"' in src

print("CHACHA_DEV_V811_DOMAIN_FEATURE_NOT_PROVIDER_GAP=PASS")
print("CHACHA_DEV_V811_RUNTIME_PROVIDER_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V811_REUSABLE_FEATURE_EVIDENCE=PASS")
print("CHACHA_DEV_V811_TRANSLATION_FEATURE_BUILD_REQUIRED=PASS")
print("CHACHA_DEV_V811_EXPLICIT_RUNTIME_HINT_PRESERVED=PASS")
print("CHACHA_DEV_V811_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
