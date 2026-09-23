#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,hashlib,json,os,shutil,subprocess,tempfile,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from typing import Any

BATCH_SCHEMA="chacha.dev/project-assurance-event-batch/v1"
EVENT_SCHEMA="chacha.dev/project-assurance-event/v1"
MAX_RESPONSE=1024*1024

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def public_b64(private_key:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(private_key),"-pubout","-outform","DER"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("ASSURANCE_PRIVATE_KEY_READ_FAILED")
    return base64.b64encode(p.stdout).decode()
def key_id(private_key:Path)->str:
    return "project-"+hashlib.sha256(public_b64(private_key).encode()).hexdigest()[:16]
def sign(private_key:Path,message:bytes)->str:
    with tempfile.NamedTemporaryFile(prefix="chacha-project-assurance-",delete=True) as f:
        f.write(message);f.flush()
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private_key),"-in",f.name],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("ASSURANCE_SIGN_FAILED")
    return base64.urlsafe_b64encode(p.stdout).decode().rstrip("=")
def request_message(method:str,url:str,ts:str,body:bytes)->bytes:
    u=urllib.parse.urlsplit(url);path=u.path or "/"
    if u.query:path+="?"+u.query
    return (ts+"\n"+method+"\n"+path+"\n").encode()+body
def post(url:str,key:Path,payload:dict[str,Any])->tuple[int,dict[str,Any]]:
    body=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    ts=now();headers={
      "content-type":"application/json","accept":"application/json",
      "user-agent":"ChaCha-Project-Assurance-Relay/1.0",
      "x-chacha-key-id":key_id(key),"x-chacha-timestamp":ts,
      "x-chacha-signature":sign(key,request_message("POST",url,ts,body))
    }
    req=urllib.request.Request(url,data=body,headers=headers,method="POST")
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read(MAX_RESPONSE+1);return r.status,json.loads(raw)
    except urllib.error.HTTPError as e:
        raw=e.read(MAX_RESPONSE+1)
        try:x=json.loads(raw)
        except Exception:x={"error":"relay_http_error","status":e.code}
        return e.code,x
def relay_role(bundle:Path,policy:dict[str,Any],key:Path,role:str)->dict[str,Any]:
    transport=policy.get("transport") or {};central=policy.get("central_authority") or {}
    base=str(central["guardian_url"] if role=="guardian" else central["sentinel_url"]).rstrip("/")
    url=base+str(transport["guardian_path"] if role=="guardian" else transport["sentinel_path"])
    limit=int(transport.get("incremental_batch_max_events") or 50)
    src=bundle/"outbox"/role;dst=bundle/"delivered"/role;dst.mkdir(parents=True,exist_ok=True)
    files=sorted(src.glob("*.json"),key=lambda p:p.stat().st_mtime)[:limit]
    if not files:return {"role":role,"status":"EMPTY","delivered":0}
    events=[]
    for p in files:
        e=load(p)
        if e.get("schema")!=EVENT_SCHEMA or e.get("assurance_role")!=role:
            raise RuntimeError("OUTBOX_EVENT_INVALID:"+str(p))
        if (e.get("privacy") or {}).get("raw_user_content") is not False or e.get("direct_mutation") is not False:
            raise RuntimeError("OUTBOX_PRIVACY_OR_MUTATION_INVALID:"+str(p))
        events.append(e)
    status,ack=post(url,key,{"schema":BATCH_SCHEMA,"project_id":events[0]["project_id"],"events":events})
    if status!=200 or ack.get("accepted")!=len(events):
        return {"role":role,"status":"DEFERRED","delivered":0,"http_status":status,"ack":ack}
    for p in files:shutil.move(str(p),str(dst/p.name))
    return {"role":role,"status":"DELIVERED","delivered":len(events),"http_status":status,"ack":ack}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--bundle",type=Path,required=True);ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--private-key",type=Path);ap.add_argument("--role",choices=["guardian","sentinel","both"],default="both")
    a=ap.parse_args();policy=load(a.policy)
    key=a.private_key or (Path(os.environ["CHACHA_PROJECT_ASSURANCE_PRIVATE_KEY"]) if os.environ.get("CHACHA_PROJECT_ASSURANCE_PRIVATE_KEY") else None)
    if key is None or not key.is_file():raise SystemExit("SERVER_SIDE_ASSURANCE_PRIVATE_KEY_REQUIRED")
    roles=["guardian","sentinel"] if a.role=="both" else [a.role]
    rows=[relay_role(a.bundle,policy,key,r) for r in roles]
    print(json.dumps({"schema":"chacha.dev/project-assurance-relay-result/v1","results":rows,
                      "client_secret_embedded":False,"direct_mutation":False},ensure_ascii=False))
    if any(x["status"]=="DEFERRED" for x in rows):return 30
    print("CHACHA_DEV_PROJECT_ASSURANCE_RELAY=PASS")
    print("RAW_USER_CONTENT=NO");print("DIRECT_MUTATION=NO");return 0
if __name__=="__main__":raise SystemExit(main())
