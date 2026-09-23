#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,hashlib,json,os,subprocess,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/project-assurance-identity-registration/v1"

def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def save(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)
def run(argv:list[str],timeout:int=30)->subprocess.CompletedProcess[str]:
    return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
def ensure_key(path:Path)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        path.chmod(0o600);return
    p=run(["/usr/bin/openssl","genpkey","-algorithm","ED25519","-out",str(path)])
    if p.returncode!=0:raise RuntimeError("PROJECT_ASSURANCE_KEY_GENERATION_FAILED:"+p.stderr[-300:])
    path.chmod(0o600)
def public_b64(path:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(path),"-pubout","-outform","DER"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("PROJECT_ASSURANCE_PUBLIC_KEY_FAILED")
    return base64.b64encode(p.stdout).decode()
def key_id(pub:str)->str:return "project-"+hashlib.sha256(pub.encode()).hexdigest()[:16]
def register(client:Path,policy:Path,registration:Path)->dict[str,Any]:
    p=run(["/usr/bin/python3",str(client),"--policy",str(policy),
           "register-project-assurance-identity","--registration",str(registration)],45)
    if p.returncode!=0:
        raise RuntimeError("PROJECT_ASSURANCE_IDENTITY_REGISTRATION_FAILED:"+client.name+":"+p.stderr[-300:]+p.stdout[-300:])
    try:x=json.loads(p.stdout.strip())
    except Exception as exc:raise RuntimeError("PROJECT_ASSURANCE_IDENTITY_RESPONSE_INVALID:"+client.name) from exc
    if x.get("status")!="PASS":raise RuntimeError("PROJECT_ASSURANCE_IDENTITY_NOT_PASS:"+client.name)
    return x

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--secret-root",type=Path,default=Path("/opt/chacha-dev/runtime/secrets/project-assurance"))
    ap.add_argument("--guardian-client",type=Path,required=True);ap.add_argument("--guardian-policy",type=Path,required=True)
    ap.add_argument("--sentinel-client",type=Path,required=True);ap.add_argument("--sentinel-policy",type=Path,required=True)
    ap.add_argument("--exchange-client",type=Path,required=True);ap.add_argument("--exchange-policy",type=Path,required=True)
    ap.add_argument("--registration",type=Path,required=True);ap.add_argument("--receipt",type=Path,required=True)
    ap.add_argument("--bundle",type=Path)
    a=ap.parse_args()
    key=a.secret_root/(a.project_id+".pem")
    ensure_key(key);pub=public_b64(key);kid=key_id(pub)
    registration={
      "schema":SCHEMA,"project_id":a.project_id,"key_id":kid,"public_key_spki_b64":pub,
      "server_side_only":True,"client_secret_allowed":False,"private_key_exported":False,
      "created_at":now()
    }
    save(a.registration,registration)
    g=register(a.guardian_client,a.guardian_policy,a.registration)
    s=register(a.sentinel_client,a.sentinel_policy,a.registration)
    e=register(a.exchange_client,a.exchange_policy,a.registration)
    receipt={
      "schema":"chacha.dev/project-assurance-identity-provisioning-receipt/v1",
      "project_id":a.project_id,"key_id":kid,"guardian_status":g.get("status"),
      "sentinel_status":s.get("status"),"exchange_status":e.get("status"),"private_key_path":str(key),
      "private_key_exported":False,"client_secret_allowed":False,
      "project_identity_active":True,"created_at":now()
    }
    save(a.receipt,receipt)
    if a.bundle:
        manifest_path=a.bundle/"embedded-assurance.json"
        if not manifest_path.is_file():raise RuntimeError("EMBEDDED_ASSURANCE_MANIFEST_MISSING")
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("relay",{})["identity_status"]="ACTIVE"
        ready=manifest.setdefault("production_readiness",{})
        ready["relay_identity_active"]=True
        ready["ready"]=bool(ready.get("guardian_local") and ready.get("sentinel_local") and
                             ready.get("privacy_contract") and ready.get("functional_contract_bound"))
        manifest["project_assurance_key_id"]=kid
        save(manifest_path,manifest)
    print("CHACHA_DEV_PROJECT_ASSURANCE_IDENTITY=PASS")
    print("PROJECT_ID="+a.project_id);print("KEY_ID="+kid)
    print("GUARDIAN_REGISTRATION=PASS");print("SENTINEL_REGISTRATION=PASS");print("EXCHANGE_REGISTRATION=PASS")
    print("CLIENT_SECRET=NO");print("PRIVATE_KEY_EXPORT=NO")
    return 0

if __name__=="__main__":raise SystemExit(main())
