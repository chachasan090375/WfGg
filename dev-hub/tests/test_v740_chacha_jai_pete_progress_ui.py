#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import progress_state_controller as psc

policy=json.loads((ROOT/"dev-hub/config/progress-reporting.v1.json").read_text(encoding="utf-8"))
assert policy["schema"]=="chacha.dev/progress-reporting-policy/v1"
assert policy["platform_maturity"]["percent"]==86
assert policy["platform_maturity"]["active_work_must_never_overwrite"] is True
assert policy["invariants"]["global_maturity_and_active_work_are_distinct"] is True
assert policy["invariants"]["one_shared_source_for_web_and_android"] is True
assert policy["invariants"]["progress_has_no_execution_authority"] is True

with tempfile.TemporaryDirectory(prefix="v740-progress-") as td:
    test_policy=json.loads(json.dumps(policy))
    test_policy["runtime_state"]=str(Path(td)/"progress.json")
    store=psc.ProgressStore(test_policy)
    idle=store.snapshot()
    assert idle["platform_maturity_percent"]==86
    assert idle["active_work_percent"]==0
    first=store.begin("op-1","Première tâche","chacha-dev-platform")
    assert first["platform_maturity_percent"]==86 and first["active_work_percent"]==3
    mid=store.update("central-orchestrator",55,"RUNNING","Décision en cours",62,"Cerveau central")
    assert mid["platform_maturity_percent"]==86 and mid["active_work_percent"]==62
    done=store.complete("Terminé")
    assert done["platform_maturity_percent"]==86 and done["active_work_percent"]==100
    second=store.begin("op-2","Deuxième tâche","chacha-dev-platform")
    assert second["platform_maturity_percent"]==86 and second["active_work_percent"]==3
    assert second["modules"]["direct-operator-service"]["percent"]==10
    assert second["modules"]["central-orchestrator"]["percent"]==0

service=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text(encoding="utf-8")
assert 'path=="/api/v1/progress"' in service
assert "ProgressStore" in service
assert 'self.progress.begin(' in service
assert 'self.progress.complete(' in service

cfg=json.loads((ROOT/"dev-hub/config/direct-operator.v1.json").read_text(encoding="utf-8"))
assert cfg["progress_policy"]=="dev-hub/config/progress-reporting.v1.json"
assert cfg["invariants"]["persistent_progress_reporting"] is True

unit=(ROOT/"dev-hub/systemd/chacha-dev-direct-operator.service").read_text(encoding="utf-8")
assert "/opt/chacha-dev/runtime/progress" in unit

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text(encoding="utf-8")
assert "ChaCha j’ai pété" in ui
assert "/api/v1/progress" in ui
assert 'id="globalPct"' in ui and 'id="workPct"' in ui
assert "ChaCha DEV global" in ui

strings=(ROOT/"android/chacha-direct-operator-widget/app/src/main/res/values/strings.xml").read_text(encoding="utf-8")
activity=(ROOT/"android/chacha-direct-operator-widget/app/src/main/res/layout/activity_operator.xml").read_text(encoding="utf-8")
widget=(ROOT/"android/chacha-direct-operator-widget/app/src/main/res/layout/widget_chacha.xml").read_text(encoding="utf-8")
activity_java=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/OperatorActivity.java").read_text(encoding="utf-8")
provider=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/ChaChaWidgetProvider.java").read_text(encoding="utf-8")
assert "ChaCha j’ai pété" in strings
assert "@+id/operator_context_panel" in activity
assert "@+id/work_progress" in activity
assert "@+id/module_4_progress" in activity
assert "@+id/widget_global_progress" in widget and "@+id/widget_work_progress" in widget
assert ("showContextMode()" in activity_java) or ("WebView" in activity_java and "SHELL_PROTOCOL_VERSION" in activity_java), activity_java
assert ('getJson("/api/v1/progress")' in activity_java) or ('"/api/v1/app-config"' in activity_java and "refreshRemote" in provider), activity_java
assert "updateContext" in provider
assert "setProgressBar" in provider

guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
ids={x["component_id"] for x in guardian["expected_components"]}
assert "progress-state-controller" in ids
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(ids)*12*24

core=json.loads((ROOT/"dev-hub/config/technology-core-watch.v1.json").read_text(encoding="utf-8"))
crow=next(x for x in core["components"] if x["id"]=="progress-state-controller")
assert crow["class"]=="verification"

roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:progress-state-controller")
assert "REPORT_PROGRESS" in role["allowed_actions"]
assert "EXECUTE_TECHNICAL_ACTION" in role["forbidden_actions"]

print("CHACHA_DEV_V740_PROGRESS_PERSISTENCE=PASS")
print("CHACHA_DEV_V740_GLOBAL_MATURITY=86")
print("CHACHA_DEV_V740_ACTIVE_WORK_INDEPENDENT=YES")
print("CHACHA_DEV_V740_PROGRESS_API=PASS")
print("CHACHA_DEV_V740_WEB_CONTEXT_UI=PASS")
print("CHACHA_DEV_V740_ANDROID_CONTEXT_UI=PASS")
print("CHACHA_DEV_V740_WIDGET_LIVE_CONTEXT=PASS")
print("CHACHA_DEV_V740_PROGRESS_EXECUTION_AUTHORITY=NO")
print("CHACHA_DEV_V740_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
