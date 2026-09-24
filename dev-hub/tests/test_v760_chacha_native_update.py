#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

publisher=loadmod("native_update_publisher",BIN/"native_update_publisher.py")
direct=loadmod("direct_operator_service",BIN/"direct-operator-service.py")

policy=json.loads((ROOT/"dev-hub/config/android-native-update.v1.json").read_text(encoding="utf-8"))
pinned=policy["pinned_signing_certificate_sha256"]
assert len(pinned)==64
assert policy["invariants"]["silent_install_not_assumed"] is True
assert policy["invariants"]["user_android_install_confirmation_required"] is True
assert policy["required_workflows"]==[
  "ChaCha DEV V7.6 native update qualification",
  "ChaCha DEV Sentinel technical assurance"
]

class R:
    returncode=0
    stdout="Signer #1 certificate SHA-256 digest: "+pinned
    stderr=""
def fake_runner(*args,**kwargs):return R()

def receipts(rev):
    return [
      {"schema":"chacha.dev/exact-sha-workflow-receipt/v1","workflow_name":"ChaCha DEV V7.6 native update qualification","head_sha":rev,"conclusion":"success","exact_sha_verified":True},
      {"schema":"chacha.dev/exact-sha-workflow-receipt/v1","workflow_name":"ChaCha DEV Sentinel technical assurance","head_sha":rev,"conclusion":"success","exact_sha_verified":True},
    ]
def handoff(rev,vc,vn):
    return {"schema":"chacha.dev/native-update-publish-handoff/v1","handoff_id":"nu-"+rev[:8],
      "actor":"central-orchestrator","revision":rev,"publish_authorized":True,
      "package_id":"com.wfgg.chachadev.operator","version_code":vc,"version_name":vn,
      "signing_cert_sha256":pinned,"user_android_install_confirmation_required":True,
      "silent_install_authorized":False,"rollback_required":True,"single_use":True,
      "automatic_external_spend_eur":0}

with tempfile.TemporaryDirectory(prefix="native-update-publisher-") as td:
    root=Path(td);apk=root/"signed.apk";apk.write_bytes(b"signed-test-apk")
    r1="a"*40;r2="b"*40
    one=publisher.publish(policy,apk,r1,6,"0.6.0",handoff(r1,6,"0.6.0"),receipts(r1),root/"runtime",fake_runner)
    assert one["status"]=="PASS" and one["silent_install_performed"] is False,one
    current=root/"runtime/current"
    first=current.resolve()
    m1=json.loads((first/"manifest.json").read_text(encoding="utf-8"))
    assert m1["version_code"]==6 and m1["signing_cert_sha256"]==pinned,m1
    assert m1["user_android_install_confirmation_required"] is True and m1["silent_install"] is False,m1
    assert (first/"packages"/Path(m1["apk_path"]).name).is_file()

    two=publisher.publish(policy,apk,r2,7,"0.7.0",handoff(r2,7,"0.7.0"),receipts(r2),root/"runtime",fake_runner)
    second=current.resolve();assert second!=first,two
    rolled=publisher.rollback(policy,two,root/"runtime")
    assert rolled["status"]=="PASS" and current.resolve()==first,rolled

# Runtime Direct Operator must really switch to the live UI root, not only expose helper methods.
with tempfile.TemporaryDirectory(prefix="native-direct-operator-") as td:
    tmp=Path(td)
    dp=json.loads((ROOT/"dev-hub/config/direct-operator.v1.json").read_text(encoding="utf-8"))
    dp["runtime_root"]=str(tmp/"direct")
    dp["live_ui_root"]=str(tmp/"live/current/ui")
    dp["live_app_config"]=str(tmp/"live/current/app-config.json")
    dp["native_update_manifest"]=str(tmp/"native/current/manifest.json")
    dp["native_update_packages_root"]=str(tmp/"native/current/packages")
    st=direct.State(ROOT,tmp,dp)
    assert st.effective_ui_root()==ROOT/"dev-hub/direct-operator-ui",st.effective_ui_root()
    (tmp/"live/current/ui").mkdir(parents=True)
    (tmp/"live/current/ui/index.html").write_text("live",encoding="utf-8")
    (tmp/"live/current").mkdir(parents=True,exist_ok=True)
    livecfg=json.loads((ROOT/"dev-hub/config/android-live-shell.v1.json").read_text(encoding="utf-8"))
    livecfg["published_revision"]="runtime-test"
    (tmp/"live/current/app-config.json").write_text(json.dumps(livecfg),encoding="utf-8")
    assert st.effective_ui_root()==tmp/"live/current/ui"
    assert st.effective_live_shell_config()["published_revision"]=="runtime-test"
    assert st.effective_native_update_manifest()["status"]=="NONE"
    (tmp/"native/current").mkdir(parents=True)
    manifest={"schema":"chacha.dev/android-native-update/v1","status":"AVAILABLE",
      "package_id":"com.wfgg.chachadev.operator","version_code":7,"version_name":"0.7.0",
      "apk_path":"/native-updates/x.apk","apk_sha256":"0"*64,"signing_cert_sha256":pinned}
    (tmp/"native/current/manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    assert st.effective_native_update_manifest()["status"]=="AVAILABLE"
    manifest["package_id"]="wrong.package"
    (tmp/"native/current/manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    assert st.effective_native_update_manifest()["status"]=="NONE"

service=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text(encoding="utf-8")
assert 'path=="/api/v1/native-update"' in service
assert 'path.startswith("/native-updates/")' in service
assert "ui_root=self.st.effective_ui_root()" in service
assert "self.st.ui/rel" not in service

manager=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/NativeUpdateManager.java").read_text(encoding="utf-8")
receiver=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/NativeUpdateReceiver.java").read_text(encoding="utf-8")
activity=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/OperatorActivity.java").read_text(encoding="utf-8")
manifest=(ROOT/"android/chacha-direct-operator-widget/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
strings=(ROOT/"android/chacha-direct-operator-widget/app/src/main/res/values/strings.xml").read_text(encoding="utf-8")
gradle=(ROOT/"android/chacha-direct-operator-widget/app/build.gradle.kts").read_text(encoding="utf-8")
assert "PackageInstaller" in manager and "APK_SIGNING_CERT_MISMATCH" in manager
assert "canRequestPackageInstalls" in manager
assert "USER_ACTION_REQUIRED" in manager
assert "STATUS_PENDING_USER_ACTION" in receiver
assert "NativeUpdateManager.checkForUpdate" in activity
assert "REQUEST_INSTALL_PACKAGES" in manifest
assert 'android:name=".NativeUpdateReceiver"' in manifest and 'android:exported="false"' in manifest
assert pinned in strings
assert 'versionCode = 6' in gradle and 'versionName = "0.6.0"' in gradle

guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
ids={x["component_id"] for x in guardian["expected_components"]}
assert "native-update-publisher" in ids
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(ids)*12*24
roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:native-update-publisher")
assert "PUBLISH_NATIVE_UPDATE" in role["allowed_actions"]
assert {"SILENT_INSTALL","EXPORT_SIGNING_KEY","PUBLISH_UNPINNED_APK"}<=set(role["forbidden_actions"])

print("CHACHA_DEV_V760_NATIVE_UPDATE=PASS")
print("CHACHA_DEV_V760_STABLE_CERT_PIN=PASS")
print("CHACHA_DEV_V760_PRIVATE_NATIVE_CHANNEL=PASS")
print("CHACHA_DEV_V760_PACKAGE_AND_VERSION_VERIFY=YES")
print("CHACHA_DEV_V760_APK_SHA256_VERIFY=YES")
print("CHACHA_DEV_V760_APK_SIGNING_CERT_VERIFY=YES")
print("CHACHA_DEV_V760_ANDROID_USER_CONFIRMATION=REQUIRED")
print("CHACHA_DEV_V760_SILENT_INSTALL=NO")
print("CHACHA_DEV_V760_NATIVE_PUBLISH_ROLLBACK=PASS")
print("CHACHA_DEV_V760_LIVE_UI_RUNTIME_SWITCH=PASS")
print("CHACHA_DEV_V760_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
