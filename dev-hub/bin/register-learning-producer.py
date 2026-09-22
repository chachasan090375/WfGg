#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,hashlib,json,subprocess,tempfile,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from typing import Any

DEFAULT_RELAY="https://chacha-dev-learning-relay.chachasan090375.workers.dev"
DEFAULT_KEY=Path("/opt/chacha-dev/runtime/secrets/central-learning-key.pem")

def now_iso():return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT")
    return x
def central_pub(private:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(private),"-pubout","-outform","DER"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("CENTRAL_KEY_READ_FAILED")
    return base64.b64encode(p.stdout).decode()
def key_id(private:Path)->str:return "central-"+hashlib.sha256(central_pub(private).encode()).hexdigest()[:16]
def sign(private:Path,msg:bytes)->str:
    with tempfile.NamedTemporaryFile(prefix="chacha-learning-register-",delete=True) as f:
        f.write(msg);f.flush()
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private),"-in",f.name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("CENTRAL_SIGN_FAILED")
    return base64.urlsafe_b64encode(p.stdout).decode().rstrip("=")
def request_message(method,url,ts,body=b""):
    u=urllib.parse.urlsplit(url);path=u.path or "/"
    if u.query:path+="?"+u.query
    return (ts+"\n"+method+"\n"+path+"\n").encode()+body
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--enrollment",type=Path,required=True)
    ap.add_argument("--relay-url",default=DEFAULT_RELAY);ap.add_argument("--central-key",type=Path,default=DEFAULT_KEY)
    a=ap.parse_args();x=load(a.enrollment)
    if x.get("schema")!="chacha.dev/learning-producer-enrollment/v1":raise SystemExit("LEARNING_PRODUCER_ENROLLMENT_SCHEMA_INVALID")
    if x.get("role")!="PRODUCER" or x.get("private_key_exported") is not False:raise SystemExit("LEARNING_PRODUCER_ENROLLMENT_INVALID")
    body=json.dumps({k:x[k] for k in ("key_id","role","public_key_spki_b64","project_id","deployment_id")},separators=(",",":")).encode()
    url=a.relay_url.rstrip("/")+"/v1/central/identities";ts=now_iso()
    req=urllib.request.Request(url,data=body,method="POST",headers={
      "Content-Type":"application/json","Accept":"application/json","X-ChaCha-Key-Id":key_id(a.central_key),
      "X-ChaCha-Timestamp":ts,"X-ChaCha-Signature":sign(a.central_key,request_message("POST",url,ts,body)),
      "User-Agent":"ChaCha-DEV-Learning-Producer-Registrar/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:out=json.loads(r.read(1024*1024))
    except urllib.error.HTTPError as e:raise SystemExit(f"LEARNING_PRODUCER_REGISTER_HTTP_{e.code}:"+e.read(1000).decode())
    if out.get("status")!="REGISTERED":raise SystemExit("LEARNING_PRODUCER_REGISTER_FAILED")
    print(json.dumps(out,indent=2));print("CHACHA_DEV_LEARNING_PRODUCER_REGISTER=PASS")
if __name__=="__main__":main()
