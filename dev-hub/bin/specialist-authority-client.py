#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,subprocess,tempfile,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from typing import Any

MAX_RESPONSE=2*1024*1024

def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def public_b64(private_key:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(private_key),"-pubout","-outform","DER"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("SPECIALIST_PRIVATE_KEY_READ_FAILED")
    return base64.b64encode(p.stdout).decode()
def key_id(private_key:Path)->str:
    import hashlib
    return "central-"+hashlib.sha256(public_b64(private_key).encode()).hexdigest()[:16]
def sign(private_key:Path,message:bytes)->str:
    with tempfile.NamedTemporaryFile(prefix="chacha-specialist-msg-",delete=True) as f:
        f.write(message);f.flush()
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private_key),"-in",f.name],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("SPECIALIST_SIGN_FAILED:"+p.stderr.decode(errors="replace")[-300:])
    return base64.urlsafe_b64encode(p.stdout).decode().rstrip("=")
def request_message(method:str,url:str,timestamp:str,body:bytes=b"")->bytes:
    u=urllib.parse.urlsplit(url);path=u.path or "/"
    if u.query:path+="?"+u.query
    return (timestamp+"\n"+method.upper()+"\n"+path+"\n").encode()+body
def signed_request(method:str,url:str,key:Path,body:bytes=b"")->urllib.request.Request:
    ts=now()
    headers={"User-Agent":"ChaCha-DEV-Specialist-Authority-Client/1.0","Accept":"application/json",
             "X-ChaCha-Key-Id":key_id(key),"X-ChaCha-Timestamp":ts,
             "X-ChaCha-Signature":sign(key,request_message(method,url,ts,body))}
    if method.upper()!="GET":headers["Content-Type"]="application/json"
    return urllib.request.Request(url,data=(body if method.upper()!="GET" else None),headers=headers,method=method.upper())
def http(req:urllib.request.Request)->tuple[int,dict[str,Any]]:
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise RuntimeError("SPECIALIST_RESPONSE_TOO_LARGE")
            return r.status,json.loads(raw)
    except urllib.error.HTTPError as e:
        raw=e.read(MAX_RESPONSE+1)
        try:x=json.loads(raw)
        except Exception:x={"error":"specialist_http_error","status":e.code,"raw":raw.decode("utf-8","replace")[:1000]}
        return e.code,x
def policy_values(path:Path)->tuple[dict[str,Any],str,Path]:
    p=load(path);return p,str(p["external_url"]).rstrip("/"),Path(p["private_key"])
def register_identity(a)->int:
    _,url,key=policy_values(a.policy)
    body=json.dumps(load(a.registration),sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    status,x=http(signed_request("POST",url+"/v1/project-assurance-identities/register",key,body))
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status==200 and x.get("status")=="PASS" else 30
def review(a)->int:
    _,url,key=policy_values(a.policy)
    payload={"schema":"chacha.dev/specialist-review-request/v1","project_id":a.project_id,"revision":a.revision,
             "compromise_digest":a.compromise_digest,"implementation_verified":a.implementation_verified}
    body=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    status,x=http(signed_request("POST",url+"/v1/review",key,body))
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status in (200,409) and x.get("schema")=="chacha.dev/compromise-agent-review/v1" else 30
def directives(a)->int:
    _,url,key=policy_values(a.policy)
    status,x=http(signed_request("GET",url+"/v1/incidents/directives",key))
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status==200 else 30
def escalate(a)->int:
    _,url,key=policy_values(a.policy)
    payload={"incident_id":a.incident_id,"scope":a.scope,"independent_corroborations":a.corroborations}
    body=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    status,x=http(signed_request("POST",url+"/v1/incidents/escalate",key,body))
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status==200 and x.get("status")=="PASS" else 30
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True)
    sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("register-project-assurance-identity");r.add_argument("--registration",type=Path,required=True)
    v=sub.add_parser("review");v.add_argument("--project-id",required=True);v.add_argument("--revision",required=True)
    v.add_argument("--compromise-digest",required=True);v.add_argument("--implementation-verified",action="store_true")
    d=sub.add_parser("directives")
    e=sub.add_parser("escalate");e.add_argument("--incident-id",required=True);e.add_argument("--scope",choices=["PROJECT","CORE","PLATFORM"],required=True)
    e.add_argument("--corroborations",type=int,default=0)
    a=ap.parse_args()
    if a.cmd=="register-project-assurance-identity":return register_identity(a)
    if a.cmd=="review":return review(a)
    if a.cmd=="directives":return directives(a)
    return escalate(a)
if __name__=="__main__":raise SystemExit(main())
