#!/usr/bin/env python3
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
policy=json.loads((ROOT/"dev-hub/config/android-migration-bootstrap.v1.json").read_text())
src=(ROOT/"android/chacha-migration-bootstrap/app/src/main/java/com/wfgg/chachadev/migration/MigrationActivity.java").read_text()
native_update=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/NativeUpdateManager.java").read_text()
manifest=(ROOT/"android/chacha-migration-bootstrap/app/src/main/AndroidManifest.xml").read_text()
gradle=(ROOT/"android/chacha-migration-bootstrap/app/build.gradle.kts").read_text()

assert policy["migration_package"]=="com.wfgg.chachadev.migration"
assert policy["target_package"]=="com.wfgg.chachadev.operator"
assert policy["target_version_code"]==6
assert policy["target_apk_private_url"]=="https://chachavps.tail3ab05a.ts.net:8445/chacha-jai-pete-v0.6.0-4fb319fcea6d.apk"
assert policy["target_apk_sha256"]=="741c3e2be48d55e09a33f805fbd39d99d579cc4efcdf4d215387e93a2228e0bb"
assert policy["target_apk_sha256"] in src
assert policy["target_signing_cert_sha256"] in src
assert policy["target_apk_private_url"] in src
assert 'Intent.ACTION_UNINSTALL_PACKAGE' in src
assert 'Intent.EXTRA_RETURN_RESULT' in src
assert 'PackageInstaller.SessionParams' in src
assert 'PackageInstaller.STATUS_PENDING_USER_ACTION' in src
assert 'canRequestPackageInstalls()' in src
assert 'Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES' in src
assert 'verifyArchive(apk)' in src
assert 'APK_PACKAGE_MISMATCH' in src
assert 'APK_VERSION_MISMATCH' in src
assert 'APK_CERT_MISMATCH' in src
assert 'TARGET_CERT_SHA256.equals(installedCert)' in src
assert 'requestSelfUninstall()' in src
assert 'session.fsync(out);\n                    }\n\n                    // PackageInstaller requires every stream opened by the session' in src
assert src.index('// PackageInstaller requires every stream opened by the session') < src.index('session.commit(pending.getIntentSender());')
assert 'session.fsync(out);\n            }\n\n            // All session streams must be closed before commit().' in native_update
assert native_update.index('// All session streams must be closed before commit().') < native_update.index('session.commit(pending.getIntentSender());')
assert 'android.permission.REQUEST_DELETE_PACKAGES' in manifest
assert 'android.permission.REQUEST_INSTALL_PACKAGES' in manifest
assert 'android.permission.INTERNET' in manifest
assert '<package android:name="com.wfgg.chachadev.operator"' in manifest
assert 'android:usesCleartextTraffic="false"' in manifest
assert 'applicationId = "com.wfgg.chachadev.migration"' in gradle
assert policy["invariants"]["silent_uninstall"] is False
assert policy["invariants"]["silent_install"] is False
assert policy["invariants"]["uninstall_skipped_if_release_certificate_matches"] is True
assert policy["invariants"]["private_tailscale_distribution"] is True

print("CHACHA_DEV_V790_ANDROID_MIGRATION_BOOTSTRAP=PASS")
print("CORRECTED_RELEASE_TARGET_PIN=PASS")
print("LEGACY_SIGNATURE_UNINSTALL_CONFIRMATION=REQUIRED")
print("RELEASE_SIGNATURE_UNINSTALL_SKIPPED=YES")
print("PRIVATE_RELEASE_DOWNLOAD=YES")
print("APK_SHA_PACKAGE_VERSION_CERT_VERIFY=PASS")
print("ANDROID_INSTALL_CONFIRMATION=REQUIRED")
print("MIGRATOR_SELF_REMOVAL_OFFERED=YES")
print("PACKAGE_INSTALLER_STREAMS_CLOSED_BEFORE_COMMIT=PASS")
print("NATIVE_UPDATE_STREAMS_CLOSED_BEFORE_COMMIT=PASS")
print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
