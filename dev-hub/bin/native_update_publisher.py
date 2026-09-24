#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
from typing import Any,Callable

POLICY_SCHEMA="chacha.dev/android-native-update-policy/v1"
HANDOFF_SCHEMA="chacha.dev/native-update-publish-handoff/v1"
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
        if r.get("head_sha")!=revision:continue
        if r.get("conclusion")!="success" or r.get("exact_sha_verified") is not True:continue
        passed.add(str(r.get("workflow_name") or ""))
    missing=sorted(required-passed)
    if missing:raise ValueError("NATIVE_UPDATE_EXACT_SHA_GATES_MISSING:"+",".join(missing))

def validate_handoff(policy:dict[str,Any],h:dict[str,Any],revision:str,version_code:int,version_name:str)->None:
    pinned=norm(policy.get("pinned_signing_certificate_sha256") or "")
    checks={
      "schema":h.get("schema")==HANDOFF_SCHEMA,
      "actor":h.get("actor")=="central-orchestrator",
      "revision":h.get("revision")==revision,
      "publish_authorized":h.get("publish_authorized") is True,
      "package_id":h.get("package_id")==policy.get("app_id"),
      "version_code":int(h.get("version_code") or 0)==version_code,
      "version_name":str(h.get("version_name") or "")==version_name,
      "signing_cert":norm(h.get("signing_cert_sha256") or "")==pinned and len(pinned)==64,
      "user_confirmation":h.get("user_android_install_confirmation_required") is True,
      "silent_install_forbidden":h.get("silent_install_authorized") is False,
      "rollback_required":h.get("rollback_required") is True,
      "single_use":h.get("single_use") is True,
      "zero_spend":float(h.get("automatic_external_spend_eur") or 0)==0,
    }
    bad=sorted(k for k,v in checks.items() if not v)
    if bad:raise ValueError("NATIVE_UPDATE_HANDOFF_INVALID:"+",".join(bad))

def verify_apk(apk:Path,pinned_cert:str,runner:Callable|None=None)->dict[str,Any]:
    runner=runner or subprocess.run
    p=runner(["apksigner","verify","--verbose","--print-certs",str(apk)],
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    if p.returncode!=0:raise ValueError("NATIVE_UPDATE_APKSIGNER_VERIFY_FAILED:"+str(p.stderr)[-500:])
    out=str(p.stdout)+"\n"+str(p.stderr)
    m=re.search(r"certificate SHA-256 digest:\s*([0-9A-Fa-f: ]+)",out)
    if not m:raise ValueError("NATIVE_UPDATE_SIGNER_DIGEST_MISSING")
    cert=norm(m.group(1))
    if cert!=norm(pinned_cert):raise ValueError("NATIVE_UPDATE_SIGNING_CERT_MISMATCH")
    return {"apk_sha256":sha256_file(apk),"signing_cert_sha256":cert}

def atomic_link(link:Path,target:str)->None:
    tmp=link.with_name(link.name+".next-"+str(os.getpid()))
    try:tmp.unlink()
    except FileNotFoundError:pass
    os.symlink(target,tmp);os.replace(tmp,link)

def prune(root:Path,current_name:str,keep:int)->None:
    releases=root/"releases"
    rows=sorted([p for p in releases.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True)
    protected={current_name}
    protected.update(p.name for p in rows if p.name!=current_name for _ in [0] if len(protected)<max(1,keep))
    for p in rows:
        if p.name not in protected:shutil.rmtree(p)

def publish(policy:dict[str,Any],apk:Path,revision:str,version_code:int,version_name:str,
            handoff:dict[str,Any],receipts:list[dict[str,Any]],runtime_root:Path|None=None,runner:Callable|None=None)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("NATIVE_UPDATE_POLICY_SCHEMA_INVALID")
    validate_handoff(policy,handoff,revision,version_code,version_name)
    validate_receipts(policy,revision,receipts)
    if not apk.is_file():raise ValueError("NATIVE_UPDATE_APK_MISSING")
    verified=verify_apk(apk,str(policy.get("pinned_signing_certificate_sha256") or ""),runner)
    root=(runtime_root or Path(str(policy.get("runtime_root") or ""))).resolve()
    releases=root/"releases";releases.mkdir(parents=True,exist_ok=True)
    stamp=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
    name=stamp+"-"+revision[:12]+"-v"+version_name.replace("/","-")
    final=releases/name
    if final.exists():raise ValueError("NATIVE_UPDATE_RELEASE_ALREADY_EXISTS:"+name)
    staging=releases/("."+name+".staging")
    if staging.exists():shutil.rmtree(staging)
    packages=staging/"packages";packages.mkdir(parents=True)
    apk_name="chacha-jai-pete-v"+version_name+"-"+revision[:12]+".apk"
    shutil.copy2(apk,packages/apk_name)
    manifest={
      "schema":"chacha.dev/android-native-update/v1","status":"AVAILABLE",
      "package_id":policy.get("app_id"),"version_code":version_code,"version_name":version_name,
      "revision":revision,"apk_path":"/native-updates/"+apk_name,
      "apk_sha256":verified["apk_sha256"],"signing_cert_sha256":verified["signing_cert_sha256"],
      "user_android_install_confirmation_required":True,"silent_install":False,
      "published_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "automatic_external_spend_eur":0
    }
    save(staging/"manifest.json",manifest)
    previous=None;link=root/"current"
    if link.is_symlink():previous=os.readlink(link)
    os.replace(staging,final);atomic_link(link,"releases/"+name)
    prune(root,name,int(policy.get("retention") or 2))
    return {
      "schema":"chacha.dev/native-update-publish-receipt/v1","status":"PASS",
      "revision":revision,"version_code":version_code,"version_name":version_name,
      "release":name,"current_target":"releases/"+name,"previous_target":previous,
      "apk_sha256":verified["apk_sha256"],"signing_cert_sha256":verified["signing_cert_sha256"],
      "handoff_id":handoff.get("handoff_id"),"rollback_available":bool(previous),
      "silent_install_performed":False,"automatic_external_spend_eur":0
    }

def rollback(policy:dict[str,Any],receipt:dict[str,Any],runtime_root:Path|None=None)->dict[str,Any]:
    root=(runtime_root or Path(str(policy.get("runtime_root") or ""))).resolve()
    previous=str(receipt.get("previous_target") or "")
    if not previous:raise ValueError("NATIVE_UPDATE_NO_PREVIOUS_RELEASE")
    target=(root/previous).resolve();releases=(root/"releases").resolve()
    if not str(target).startswith(str(releases)+os.sep) or not target.is_dir():
        raise ValueError("NATIVE_UPDATE_ROLLBACK_TARGET_INVALID")
    atomic_link(root/"current",previous)
    return {"schema":"chacha.dev/native-update-rollback-receipt/v1","status":"PASS",
            "restored_target":previous,"silent_install_performed":False,
            "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("publish");p.add_argument("--apk",type=Path,required=True);p.add_argument("--revision",required=True);p.add_argument("--version-code",type=int,required=True);p.add_argument("--version-name",required=True);p.add_argument("--handoff",type=Path,required=True);p.add_argument("--receipt",type=Path,action="append",required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--apply",action="store_true")
    r=sub.add_parser("rollback");r.add_argument("--publish-receipt",type=Path,required=True);r.add_argument("--output",type=Path,required=True);r.add_argument("--apply",action="store_true")
    a=ap.parse_args();policy=load(a.policy)
    if not a.apply:raise SystemExit("NATIVE_UPDATE_APPLY_FLAG_REQUIRED")
    if a.cmd=="publish":
        out=publish(policy,a.apk,a.revision,a.version_code,a.version_name,load(a.handoff),[load(x) for x in a.receipt])
    else:out=rollback(policy,load(a.publish_receipt))
    save(a.output,out);print(json.dumps(out,ensure_ascii=False));return 0

if __name__=="__main__":raise SystemExit(main())
