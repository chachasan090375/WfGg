#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))

spec=importlib.util.spec_from_file_location("live_ui_publisher",BIN/"live_ui_publisher.py")
assert spec and spec.loader
pub=importlib.util.module_from_spec(spec);spec.loader.exec_module(pub)

policy=json.loads((ROOT/"dev-hub/config/live-ui-publisher.v1.json").read_text(encoding="utf-8"))
assert policy["scope"]=="CHACHA_LIVE_UI_ONLY"
assert policy["invariants"]["android_native_files_forbidden"] is True
assert policy["invariants"]["apk_install_authority"] is False
assert policy["invariants"]["systemd_mutation_authority"] is False

def receipts(rev):
    return [
      {"schema":"chacha.dev/exact-sha-workflow-receipt/v1","workflow_name":"ChaCha DEV V7.5 live update shell qualification","head_sha":rev,"conclusion":"success","exact_sha_verified":True},
      {"schema":"chacha.dev/exact-sha-workflow-receipt/v1","workflow_name":"ChaCha DEV Sentinel technical assurance","head_sha":rev,"conclusion":"success","exact_sha_verified":True},
    ]
def handoff(rev):
    return {"schema":"chacha.dev/live-ui-publish-handoff/v1","handoff_id":"live-"+rev[:8],
      "actor":"central-orchestrator","revision":rev,"publish_authorized":True,
      "scope":"CHACHA_LIVE_UI_ONLY","native_update_authorized":False,"apk_install_authorized":False,
      "systemd_mutation_authorized":False,"rollback_required":True,"single_use":True,
      "automatic_external_spend_eur":0}

with tempfile.TemporaryDirectory(prefix="live-ui-") as td:
    rt=Path(td)
    r1="1"*40;r2="2"*40
    one=pub.publish(ROOT,policy,r1,handoff(r1),receipts(r1),rt)
    current=rt/"current"
    assert current.is_symlink(),one
    first_target=current.resolve()
    assert (first_target/"ui/index.html").is_file()
    cfg=json.loads((first_target/"app-config.json").read_text(encoding="utf-8"))
    assert cfg["published_revision"]==r1,cfg
    assert one["native_update_performed"] is False and one["apk_installed"] is False,one

    two=pub.publish(ROOT,policy,r2,handoff(r2),receipts(r2),rt)
    second_target=current.resolve()
    assert second_target!=first_target,two
    assert two["previous_target"],two
    cfg2=json.loads((second_target/"app-config.json").read_text(encoding="utf-8"))
    assert cfg2["published_revision"]==r2,cfg2

    rolled=pub.rollback(policy,two,rt)
    assert rolled["status"]=="PASS",rolled
    assert current.resolve()==first_target,(current.resolve(),first_target)

shell=json.loads((ROOT/"dev-hub/config/android-live-shell.v1.json").read_text(encoding="utf-8"))
assert shell["app_id"]=="com.wfgg.chachadev.operator"
assert shell["invariants"]["allowed_origin_only"] is True
assert shell["invariants"]["remote_ui_has_no_native_install_authority"] is True

service=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text(encoding="utf-8")
assert 'path=="/api/v1/app-config"' in service
assert "effective_ui_root" in service and "effective_live_shell_config" in service

activity=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/OperatorActivity.java").read_text(encoding="utf-8")
assert "WebView" in activity
assert "MIXED_CONTENT_NEVER_ALLOW" in activity
assert "setAllowFileAccess(false)" in activity
assert "setAllowContentAccess(false)" in activity
assert "allowedOrigin" in activity
assert '"/api/v1/app-config"' in activity
assert "SHELL_PROTOCOL_VERSION" in activity
assert "addJavascriptInterface" not in activity

provider=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/ChaChaWidgetProvider.java").read_text(encoding="utf-8")
assert '"/api/v1/app-config"' in provider
assert '"/api/v1/progress"' in provider
assert "refreshRemote" in provider

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text(encoding="utf-8")
assert "window.chachaSetPrompt" in ui
assert "window.chachaSubmit" in ui

widget_info=(ROOT/"android/chacha-direct-operator-widget/app/src/main/res/xml/chacha_widget_info.xml").read_text(encoding="utf-8")
assert 'android:updatePeriodMillis="1800000"' in widget_info

guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
ids={x["component_id"] for x in guardian["expected_components"]}
assert "live-ui-publisher" in ids
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(ids)*12*24

roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:live-ui-publisher")
assert "PUBLISH_LIVE_UI" in role["allowed_actions"]
assert {"INSTALL_APK","NATIVE_APP_UPDATE","MUTATE_SYSTEMD","ARBITRARY_RUNTIME_MUTATION"}<=set(role["forbidden_actions"])

print("CHACHA_DEV_V750_LIVE_SHELL=PASS")
print("CHACHA_DEV_V750_REMOTE_UI=YES")
print("CHACHA_DEV_V750_REMOTE_WIDGET_CONFIG=YES")
print("CHACHA_DEV_V750_ALLOWED_ORIGIN_ONLY=YES")
print("CHACHA_DEV_V750_ATOMIC_PUBLISH=PASS")
print("CHACHA_DEV_V750_ROLLBACK=PASS")
print("CHACHA_DEV_V750_NATIVE_UPDATE_AUTHORITY=NO")
print("CHACHA_DEV_V750_APK_INSTALL_AUTHORITY=NO")
print("CHACHA_DEV_V750_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
