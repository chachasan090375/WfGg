#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY=Path("/opt/chacha-dev/runtime/secrets/learning-ingress-keys.json")
SAFE=re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
KEY_SCHEMA="chacha.dev/learning-ingress-keys/v1"

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def slug(v:str)->str:
    s=re.sub(r"[^A-Za-z0-9._-]+","-",v).strip(".-")
    return s[:96] or "deployment"

def atomic_write(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600)
    os.replace(tmp,path)

def load_registry(path:Path)->dict[str,Any]:
    if not path.exists():
        return {"schema":KEY_SCHEMA,"version":"1.0.0","keys":{}}
    x=json.loads(path.read_text(encoding="utf-8"))
    if x.get("schema")!=KEY_SCHEMA or not isinstance(x.get("keys"),dict):
        raise SystemExit("LEARNING_IDENTITY_REGISTRY_INVALID")
    return x

def validate_id(label:str,value:str)->str:
    value=str(value).strip()
    if not SAFE.fullmatch(value):
        raise SystemExit(f"{label}_INVALID")
    return value

def provision(args:argparse.Namespace)->dict[str,Any]:
    project=validate_id("PROJECT_ID",args.project_id)
    deployment=validate_id("DEPLOYMENT_ID",args.deployment_id)
    source_scope=validate_id("SOURCE_SCOPE",args.source_scope)
    if not args.endpoint.startswith("https://"):
        raise SystemExit("LEARNING_IDENTITY_HTTPS_ENDPOINT_REQUIRED")
    args.registry.parent.mkdir(parents=True,exist_ok=True)
    lock_path=args.registry.with_suffix(args.registry.suffix+".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        reg=load_registry(args.registry)
        existing=None
        for key_id,meta in reg["keys"].items():
            if not isinstance(meta,dict):
                continue
            if meta.get("status")=="ACTIVE" and meta.get("project_ids")==[project] and meta.get("deployment_ids")==[deployment] and meta.get("source_scope")==source_scope:
                existing=(key_id,meta);break
        if existing and not args.rotate:
            key_id,meta=existing
            return {"status":"EXISTS","key_id":key_id,"bundle_created":False,"secret_revealed":False}
        if existing and args.rotate:
            existing[1]["status"]="REVOKED"
            existing[1]["revoked_at"]=now_iso()
            existing[1]["revocation_reason"]="ROTATED"
        key_id=f"{slug(project)}:{slug(deployment)}:{secrets.token_hex(6)}"
        secret=secrets.token_urlsafe(48)
        reg["keys"][key_id]={
            "status":"ACTIVE",
            "secret":secret,
            "project_ids":[project],
            "deployment_ids":[deployment],
            "source_scope":source_scope,
            "created_at":now_iso(),
            "purpose":"central-learning-uplink"
        }
        atomic_write(args.registry,reg)
        bundle=args.bundle_dir
        bundle.mkdir(parents=True,exist_ok=True)
        os.chmod(bundle,0o700)
        env_path=bundle/f"{slug(project)}-{slug(deployment)}.learning-uplink.env"
        env_path.write_text(
            "\n".join([
                f"CHACHA_LEARNING_INGRESS_ENDPOINT={args.endpoint.rstrip('/')}/v1/learning-deltas",
                f"CHACHA_LEARNING_UPLINK_KEY_ID={key_id}",
                f"CHACHA_LEARNING_UPLINK_SECRET={secret}",
                f"CHACHA_LEARNING_PROJECT_ID={project}",
                f"CHACHA_LEARNING_DEPLOYMENT_ID={deployment}",
                f"CHACHA_LEARNING_SOURCE_SCOPE={source_scope}",
                ""
            ]),
            encoding="utf-8"
        )
        os.chmod(env_path,0o600)
        public_path=bundle/f"{slug(project)}-{slug(deployment)}.learning-identity.json"
        public_path.write_text(json.dumps({
            "schema":"chacha.dev/learning-identity/v1",
            "key_id":key_id,
            "project_id":project,
            "deployment_id":deployment,
            "source_scope":source_scope,
            "endpoint":args.endpoint.rstrip("/")+"/v1/learning-deltas",
            "created_at":reg["keys"][key_id]["created_at"],
            "secret_in_this_file":False
        },indent=2)+"\n",encoding="utf-8")
        os.chmod(public_path,0o644)
        return {
            "status":"PROVISIONED",
            "key_id":key_id,
            "bundle_path":str(env_path),
            "public_identity_path":str(public_path),
            "secret_revealed":False,
            "rotation":bool(args.rotate)
        }

def revoke(args:argparse.Namespace)->dict[str,Any]:
    key_id=validate_id("KEY_ID",args.key_id)
    with args.registry.open("r+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        reg=load_registry(args.registry)
        meta=reg["keys"].get(key_id)
        if not isinstance(meta,dict):
            raise SystemExit("LEARNING_IDENTITY_KEY_NOT_FOUND")
        meta["status"]="REVOKED";meta["revoked_at"]=now_iso();meta["revocation_reason"]=str(args.reason)[:200]
        atomic_write(args.registry,reg)
    return {"status":"REVOKED","key_id":key_id}

def status(args:argparse.Namespace)->dict[str,Any]:
    reg=load_registry(args.registry)
    items=[]
    for key_id,meta in sorted(reg["keys"].items()):
        if not isinstance(meta,dict):continue
        items.append({
            "key_id":key_id,"status":meta.get("status"),"project_ids":meta.get("project_ids") or [],
            "deployment_ids":meta.get("deployment_ids") or [],"source_scope":meta.get("source_scope"),
            "created_at":meta.get("created_at"),"revoked_at":meta.get("revoked_at")
        })
    return {"schema":"chacha.dev/learning-identity-status/v1","identities":items,"secret_values_exposed":False}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--registry",type=Path,default=DEFAULT_REGISTRY)
    sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("provision");p.add_argument("--project-id",required=True);p.add_argument("--deployment-id",required=True);p.add_argument("--source-scope",default="all-learning-capable-components");p.add_argument("--endpoint",required=True);p.add_argument("--bundle-dir",type=Path,required=True);p.add_argument("--rotate",action="store_true")
    r=sub.add_parser("revoke");r.add_argument("--key-id",required=True);r.add_argument("--reason",required=True)
    sub.add_parser("status")
    a=ap.parse_args()
    if a.cmd=="provision":out=provision(a)
    elif a.cmd=="revoke":out=revoke(a)
    else:out=status(a)
    print(json.dumps(out,indent=2,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
