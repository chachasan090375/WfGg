#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
AGENT=ROOT/"dev-hub/bin/professional-localization-agent.py"
POLICY=ROOT/"dev-hub/config/professional-localization-policy.v1.json"
SEM=ROOT/"dev-hub/config/capability-semantics.v1.json"

spec=importlib.util.spec_from_file_location("v813_localization",AGENT)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
policy=json.loads(POLICY.read_text(encoding="utf-8"))
assert policy["agent_id"]=="translation-specialist"
assert set([
 "translation","terminology-management","translation-quality-review",
 "register-adaptation","locale-localization","ui-length-aware-translation",
 "structured-content-preservation","project-translation-memory"
])<=set(policy["capabilities"])

req={
 "schema":"chacha.dev/localization-request/v1",
 "project_id":"test-project","source_locale":"fr-FR","target_locale":"en-US",
 "register":"application-ui","content_kind":"ui",
 "segments":[{"id":"welcome","path":"home.welcome","text":"Bonjour {name}","max_chars":20}]
}
memory={
 "schema":"chacha.dev/project-translation-memory/v1","project_id":"test-project","updated_at":None,
 "entries":[{
   "source_locale":"fr-FR","target_locale":"en-US","register":"application-ui",
   "source_text":"Bonjour {name}","target_text":"Hello {name}",
   "approved":True,"approved_by":"documentation-adr-agent"
 }]
}
out=mod.translate(req,policy,memory,60)
assert out["status"]=="TRANSLATED",out
seg=out["segments"][0]
assert seg["translation"]=="Hello {name}"
assert seg["source"]=="PROJECT_MEMORY"
assert seg["placeholder_status"]=="PASS"
assert seg["length_status"]=="OK"
assert out["independent_review_required"] is True
assert out["memory_candidates_committed"] is False

req2=json.loads(json.dumps(req))
req2["segments"][0]["max_chars"]=5
out2=mod.translate(req2,policy,memory,60)
assert out2["status"]=="REVIEW_REQUIRED",out2
assert "UI_LENGTH_EXCEEDED:welcome" in out2["quality_issues"]

with tempfile.TemporaryDirectory(prefix="v813-memory-") as td:
    td=Path(td);mem=td/"memory.json"
    result={
      "schema":"chacha.dev/professional-localization-result/v1","project_id":"test-project",
      "memory_candidates":[{
        "source_locale":"fr-FR","target_locale":"en-US","register":"application-ui",
        "source_text":"Quitter","target_text":"Exit","path":"menu.exit"
      }]
    }
    bad={"schema":"chacha.dev/localization-review/v1","status":"PASS","independent":False,"reviewer_role":"documentation-adr-agent"}
    try:
        mod.commit_memory(result,bad,mem,True)
        raise AssertionError("independent review should be required")
    except ValueError as exc:
        assert "INDEPENDENT_REVIEW_REQUIRED" in str(exc)
    review={"schema":"chacha.dev/localization-review/v1","status":"PASS","independent":True,"reviewer_role":"documentation-adr-agent"}
    dry=mod.commit_memory(result,review,mem,False)
    assert dry["status"]=="READY" and not mem.exists()
    committed=mod.commit_memory(result,review,mem,True)
    assert committed["status"]=="COMMITTED" and committed["added"]==1
    saved=json.loads(mem.read_text(encoding="utf-8"))
    assert saved["entries"][0]["approved"] is True
    assert saved["entries"][0]["approved_by"]=="documentation-adr-agent"

sem=json.loads(SEM.read_text(encoding="utf-8"))
features=sem["domain_features"]
assert len(features)==27
assert all(v.get("implementation_state")=="REUSABLE" for v in features.values())
for cap in ["register-adaptation","locale-localization","ui-length-aware-translation","structured-content-preservation","project-translation-memory"]:
    assert "dev-hub/bin/professional-localization-agent.py" in features[cap]["evidence"]

print("CHACHA_DEV_V813_MEMORY_REUSE=PASS")
print("CHACHA_DEV_V813_PLACEHOLDER_PRESERVATION=PASS")
print("CHACHA_DEV_V813_UI_LENGTH_GATE=PASS")
print("CHACHA_DEV_V813_INDEPENDENT_MEMORY_REVIEW=PASS")
print("CHACHA_DEV_V813_ALL_27_DOMAIN_FEATURES_REUSABLE=PASS")
print("CHACHA_DEV_V813_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
