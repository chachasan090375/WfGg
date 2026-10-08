#!/usr/bin/env python3
import argparse,base64,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path

a=argparse.ArgumentParser()
a.add_argument("--envelope",required=True); a.add_argument("--payload",required=True)
a.add_argument("--public-key",required=True); a.add_argument("--node",required=True); a.add_argument("--allow",action="append",default=[]); a.add_argument("--replay-cache")
x=a.parse_args(); e=json.load(open(x.envelope)); sig=e.pop("signature_b64","")

def resolve_openssl():
    if sys.platform == "darwin":
        for candidate in (
            "/opt/homebrew/bin/openssl",
            "/usr/local/bin/openssl",
        ):
            p = Path(candidate)
            if p.is_file() and os.access(p, os.X_OK):
                return str(p)

    candidate = shutil.which("openssl")
    if candidate:
        return candidate

    raise SystemExit("BLOCK=OPENSSL_UNAVAILABLE")

OPENSSL=resolve_openssl()

def walk(v):
    if isinstance(v,dict):
        for k,z in v.items():
            if k.lower() in {"password","token","secret","private_key","api_key"}: raise SystemExit("BLOCK=RAW_SECRET")
            walk(z)
    elif isinstance(v,list):
        for z in v: walk(z)

walk(e)
if e.get("target_node")!=x.node: raise SystemExit("BLOCK=TARGET")
if x.allow and e.get("capability") not in x.allow: raise SystemExit("BLOCK=LOCAL_VETO")
nonce=str(e.get("nonce", ""))
if x.replay_cache:
    rp=Path(x.replay_cache)
    seen=set(rp.read_text().splitlines()) if rp.exists() else set()
    if nonce in seen: raise SystemExit("BLOCK=REPLAY")
if not re.fullmatch(r"[0-9a-fA-F]{32,}",nonce): raise SystemExit("BLOCK=NONCE")
if datetime.fromisoformat(e["expires_at"].replace("Z","+00:00"))<=datetime.now(timezone.utc): raise SystemExit("BLOCK=EXPIRED")
p=Path(x.payload).read_bytes()
if hashlib.sha256(p).hexdigest()!=e.get("payload_sha256"): raise SystemExit("BLOCK=DIGEST")
if str(e.get("classification","")).upper() in {"CONFIDENTIAL","RESTRICTED"}:
    enc=e.get("payload_encryption") or {}
    if enc.get("encrypted") is not True or enc.get("algorithm")!="age-X25519": raise SystemExit("BLOCK=ENCRYPTION")

msg=json.dumps(e,sort_keys=True,separators=(",",":")).encode()
with tempfile.TemporaryDirectory() as d:
    Path(d+"/m").write_bytes(msg); Path(d+"/s").write_bytes(base64.b64decode(sig))
    r=subprocess.run([OPENSSL,"pkeyutl","-verify","-rawin","-pubin","-inkey",x.public_key,"-sigfile",d+"/s","-in",d+"/m"])
    if r.returncode: raise SystemExit("BLOCK=SIGNATURE")
if x.replay_cache:
    rp.parent.mkdir(parents=True,exist_ok=True)
    with rp.open("a") as f: f.write(nonce+"\n")

print("NODE_CRYPTO_VERIFY=PASS")
