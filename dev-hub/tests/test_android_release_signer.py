#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,shutil,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("android_release_signer",ROOT/"dev-hub/bin/android_release_signer.py")
assert spec and spec.loader
signer=importlib.util.module_from_spec(spec);spec.loader.exec_module(signer)

PIN="3a39f13de1191aec28526d5d8e7c9b490723d514b8dd87e5cb30aaa86a6bff88"
REV="c"*40

with tempfile.TemporaryDirectory(prefix="android-release-signer-") as td:
    t=Path(td)
    unsigned=t/"app-release-unsigned.apk";unsigned.write_bytes(b"unsigned-apk-test")
    key=t/"release-key.pem";key.write_text("PRIVATE-KEY-NOT-REAL",encoding="utf-8")
    cert=t/"release-cert.pem";cert.write_text("CERT-NOT-REAL",encoding="utf-8")
    policy={
      "schema":"chacha.dev/android-release-signing-policy/v1",
      "app_id":"com.wfgg.chachadev.operator",
      "key_path":str(key),"certificate_path":str(cert),
      "pinned_certificate_sha256":PIN,
      "required_workflows":["ChaCha DEV V7.6 native update qualification","ChaCha DEV Sentinel technical assurance"]
    }
    unsigned_sha=signer.sha256_file(unsigned)
    handoff={
      "schema":"chacha.dev/android-release-signing-handoff/v1",
      "handoff_id":"sign-"+REV[:8],"actor":"central-orchestrator","revision":REV,
      "package_id":"com.wfgg.chachadev.operator","sign_authorized":True,
      "unsigned_apk_sha256":unsigned_sha,"signing_cert_sha256":PIN,
      "key_export_authorized":False,"single_use":True,"automatic_external_spend_eur":0
    }
    receipts=[
      {"schema":"chacha.dev/exact-sha-workflow-receipt/v1","workflow_name":"ChaCha DEV V7.6 native update qualification","head_sha":REV,"conclusion":"success","exact_sha_verified":True},
      {"schema":"chacha.dev/exact-sha-workflow-receipt/v1","workflow_name":"ChaCha DEV Sentinel technical assurance","head_sha":REV,"conclusion":"success","exact_sha_verified":True}
    ]
    class Result:
        def __init__(self,rc=0,out="",err=""):self.returncode=rc;self.stdout=out;self.stderr=err
    def fake_runner(args,**kwargs):
        if args[0]=="openssl":
            return Result(out="sha256 Fingerprint="+":".join(PIN[i:i+2] for i in range(0,64,2)).upper()+"\n")
        if args[0]=="apksigner" and args[1]=="sign":
            out=Path(args[args.index("--out")+1]);src=Path(args[-1]);shutil.copy2(src,out)
            return Result()
        if args[0]=="apksigner" and args[1]=="verify":
            return Result(out="Signer #1 certificate SHA-256 digest: "+PIN+"\nVerified using v2 scheme (APK Signature Scheme v2): true\nVerified using v3 scheme (APK Signature Scheme v3): true\n")
        raise AssertionError(args)

    output=t/"signed.apk"
    receipt=signer.sign(policy,unsigned,output,REV,handoff,receipts,fake_runner)
    assert receipt["status"]=="PASS",receipt
    assert receipt["signing_cert_sha256"]==PIN,receipt
    assert receipt["unsigned_apk_sha256"]==unsigned_sha,receipt
    assert receipt["key_exported"] is False,receipt
    assert output.is_file()

    bad=dict(handoff);bad["signing_cert_sha256"]="0"*64
    try:signer.sign(policy,unsigned,t/"bad.apk",REV,bad,receipts,fake_runner)
    except ValueError as e:assert "HANDOFF_INVALID" in str(e),e
    else:raise AssertionError("wrong cert pin accepted")

    missing=receipts[:1]
    try:signer.sign(policy,unsigned,t/"bad2.apk",REV,handoff,missing,fake_runner)
    except ValueError as e:assert "EXACT_SHA_GATES_MISSING" in str(e),e
    else:raise AssertionError("missing Sentinel receipt accepted")

policy=json.loads((ROOT/"dev-hub/config/android-release-signing.v1.json").read_text(encoding="utf-8"))
assert policy["pinned_certificate_sha256"]==PIN
assert policy["invariants"]["key_export_forbidden"] is True
assert policy["invariants"]["key_material_in_repository_forbidden"] is True

print("CHACHA_DEV_V760_ANDROID_RELEASE_SIGNER=PASS")
print("CHACHA_DEV_V760_ANDROID_SIGNER_CERT_PIN=PASS")
print("CHACHA_DEV_V760_ANDROID_SIGNER_EXACT_SHA_GATES=PASS")
print("CHACHA_DEV_V760_ANDROID_SIGNER_KEY_EXPORT=NO")
print("CHACHA_DEV_V760_ANDROID_SIGNER_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
