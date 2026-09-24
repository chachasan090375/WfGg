#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
from pathlib import Path
from typing import Any,Callable

POLICY_SCHEMA="chacha.dev/android-release-signing-policy/v1"
HANDOFF_SCHEMA="chacha.dev/android-release-signing-handoff/v1"
RECEIPT_SCHEMA="chacha.dev/exact-sha-workflow-receipt/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+".tmp-"+str(os.getpid()))
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,p)

def norm(v:str)->str:
    return re.sub(r"[^0-9a-f]","",str(v).lower())

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def validate_receipts(policy:dict[str,Any],revision:str,receipts:list[dict[str,Any]])->None:
    required=set(str(x) for x in policy.get("required_workflows") or [])
    passed=set()
    for r in receipts:
        if r.get("schema")!=RECEIPT_SCHEMA:continue
        if str(r.get("head_sha") or "")!=revision:continue
        if r.get("conclusion")!="success" or r.get("exact_sha_verified") is not True:continue
        passed.add(str(r.get("workflow_name") or ""))
    missing=sorted(required-passed)
    if missing:raise ValueError("ANDROID_SIGNER_EXACT_SHA_GATES_MISSING:"+",".join(missing))

def validate_handoff(policy:dict[str,Any],handoff:dict[str,Any],revision:str,unsigned_sha:str)->None:
    checks={
      "schema":handoff.get("schema")==HANDOFF_SCHEMA,
      "actor":handoff.get("actor")=="central-orchestrator",
      "revision":handoff.get("revision")==revision,
      "package_id":handoff.get("package_id")==policy.get("app_id"),
      "sign_authorized":handoff.get("sign_authorized") is True,
      "unsigned_sha":norm(handoff.get("unsigned_apk_sha256") or "")==norm(unsigned_sha),
      "signing_cert_pin":norm(handoff.get("signing_cert_sha256") or "")==norm(policy.get("pinned_certificate_sha256") or ""),
      "key_export_forbidden":handoff.get("key_export_authorized") is False,
      "single_use":handoff.get("single_use") is True,
      "zero_spend":float(handoff.get("automatic_external_spend_eur") or 0)==0,
    }
    bad=sorted(k for k,v in checks.items() if not v)
    if bad:raise ValueError("ANDROID_SIGNER_HANDOFF_INVALID:"+",".join(bad))

def cert_fingerprint(cert:Path,runner:Callable=subprocess.run)->str:
    p=runner(["openssl","x509","-in",str(cert),"-noout","-fingerprint","-sha256"],
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    if p.returncode!=0:raise ValueError("ANDROID_SIGNER_CERT_READ_FAILED")
    m=re.search(r"Fingerprint\s*=\s*([0-9A-Fa-f:]+)",str(p.stdout))
    if not m:raise ValueError("ANDROID_SIGNER_CERT_FINGERPRINT_MISSING")
    return norm(m.group(1))

def verify_signed(apk:Path,pinned:str,runner:Callable=subprocess.run)->dict[str,Any]:
    p=runner(["apksigner","verify","--verbose","--print-certs",str(apk)],
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    if p.returncode!=0:raise ValueError("ANDROID_SIGNER_OUTPUT_VERIFY_FAILED:"+str(p.stderr)[-500:])
    out=str(p.stdout)+"\n"+str(p.stderr)
    m=re.search(r"certificate SHA-256 digest:\s*([0-9A-Fa-f: ]+)",out)
    if not m:raise ValueError("ANDROID_SIGNER_OUTPUT_CERT_MISSING")
    cert=norm(m.group(1))
    if cert!=norm(pinned):raise ValueError("ANDROID_SIGNER_OUTPUT_CERT_MISMATCH")
    if "Verified using v2 scheme (APK Signature Scheme v2): true" not in out:
        raise ValueError("ANDROID_SIGNER_V2_REQUIRED")
    return {"signed_apk_sha256":sha256_file(apk),"signing_cert_sha256":cert}

def sign(policy:dict[str,Any],unsigned:Path,output:Path,revision:str,handoff:dict[str,Any],
         receipts:list[dict[str,Any]],runner:Callable=subprocess.run)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("ANDROID_SIGNER_POLICY_SCHEMA_INVALID")
    if not unsigned.is_file():raise ValueError("ANDROID_SIGNER_UNSIGNED_APK_MISSING")
    unsigned_sha=sha256_file(unsigned)
    validate_handoff(policy,handoff,revision,unsigned_sha)
    validate_receipts(policy,revision,receipts)
    key=Path(str(policy.get("key_path") or ""))
    cert=Path(str(policy.get("certificate_path") or ""))
    if not key.is_absolute() or not cert.is_absolute():raise ValueError("ANDROID_SIGNER_SECRET_PATH_MUST_BE_ABSOLUTE")
    if not key.is_file() or not cert.is_file():raise ValueError("ANDROID_SIGNER_SECRET_MISSING")
    pin=norm(policy.get("pinned_certificate_sha256") or "")
    if cert_fingerprint(cert,runner)!=pin:raise ValueError("ANDROID_SIGNER_PRIVATE_CERT_PIN_MISMATCH")
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chacha-apk-sign-") as td:
        tmp=Path(td)/"signed.apk"
        p=runner(["apksigner","sign","--key",str(key),"--cert",str(cert),
                  "--v1-signing-enabled","true","--v2-signing-enabled","true","--v3-signing-enabled","true",
                  "--out",str(tmp),str(unsigned)],
                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
        if p.returncode!=0:raise ValueError("ANDROID_SIGNER_APKSIGNER_FAILED:"+str(p.stderr)[-500:])
        verified=verify_signed(tmp,pin,runner)
        shutil.copy2(tmp,output)
    return {
      "schema":"chacha.dev/android-release-signing-receipt/v1","status":"PASS",
      "revision":revision,"package_id":policy.get("app_id"),
      "unsigned_apk_sha256":unsigned_sha,
      "signed_apk_sha256":verified["signed_apk_sha256"],
      "signing_cert_sha256":verified["signing_cert_sha256"],
      "handoff_id":handoff.get("handoff_id"),
      "key_exported":False,"automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--unsigned-apk",type=Path,required=True)
    ap.add_argument("--output-apk",type=Path,required=True)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--handoff",type=Path,required=True)
    ap.add_argument("--receipt",type=Path,action="append",required=True)
    ap.add_argument("--output-receipt",type=Path,required=True)
    ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    if not a.apply:raise SystemExit("ANDROID_SIGNER_APPLY_FLAG_REQUIRED")
    out=sign(load(a.policy),a.unsigned_apk,a.output_apk,a.revision,load(a.handoff),[load(x) for x in a.receipt])
    save(a.output_receipt,out);print(json.dumps(out,ensure_ascii=False));return 0

if __name__=="__main__":raise SystemExit(main())
