#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,subprocess,tempfile,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/assurance-exchange-runtime-policy.v1.json")
MAX_RESPONSE=2*1024*1024

def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def public_b64(private_key:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(private_key),"-pubout","-outform","DER"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("EXCHANGE_PRIVATE_KEY_READ_FAILED")
    return base64.b64encode(p.stdout).decode()
def key_id(private_key:Path)->str:
    import hashlib
    return "central-"+hashlib.sha256(public_b64(private_key).encode()).hexdigest()[:16]
def sign(private_key:Path,message:bytes)->str:
    with tempfile.NamedTemporaryFile(prefix="chacha-exchange-msg-",delete=True) as f:
        f.write(message);f.flush()
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private_key),"-in",f.name],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("EXCHANGE_SIGN_FAILED:"+p.stderr.decode(errors="replace")[-300:])
    return base64.urlsafe_b64encode(p.stdout).decode().rstrip("=")
def request_message(method:str,url:str,timestamp:str,body:bytes=b"")->bytes:
    u=urllib.parse.urlsplit(url);path=u.path or "/"
    if u.query:path+="?"+u.query
    return (timestamp+"\n"+method.upper()+"\n"+path+"\n").encode()+body
def signed_request(method:str,url:str,key:Path,body:bytes=b"")->urllib.request.Request:
    ts=now()
    headers={"User-Agent":"ChaCha-DEV-Assurance-Exchange-Client/1.0","Accept":"application/json",
             "X-ChaCha-Key-Id":key_id(key),"X-ChaCha-Timestamp":ts,
             "X-ChaCha-Signature":sign(key,request_message(method,url,ts,body))}
    if method.upper()!="GET":headers["Content-Type"]="application/json"
    return urllib.request.Request(url,data=(body if method.upper()!="GET" else None),
                                  headers=headers,method=method.upper())
def unsigned_json_request(method:str,url:str,payload:dict[str,Any])->urllib.request.Request:
    body=json.dumps(payload,separators=(",",":")).encode()
    return urllib.request.Request(url,data=body,headers={"Content-Type":"application/json",
      "Accept":"application/json","User-Agent":"ChaCha-DEV-Assurance-Exchange-Client/1.0"},method=method)
def http(req:urllib.request.Request)->tuple[int,dict[str,Any]]:
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise RuntimeError("EXCHANGE_RESPONSE_TOO_LARGE")
            return r.status,json.loads(raw)
    except urllib.error.HTTPError as e:
        raw=e.read(MAX_RESPONSE+1)
        try:x=json.loads(raw)
        except Exception:x={"error":"exchange_http_error","status":e.code,"raw":raw.decode("utf-8","replace")[:1000]}
        return e.code,x
def policy_values(path:Path)->tuple[dict[str,Any],str,Path]:
    p=load(path);return p,str(p["external_url"]).rstrip("/"),Path(p["private_key"])
def register_project_assurance_identity(policy_path:Path,registration:Path)->int:
    _,url,key=policy_values(policy_path)
    if not key.is_file():return 30
    payload=load(registration)
    body=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    try:status,x=http(signed_request("POST",url+"/v1/project-assurance-identities/register",key,body))
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/assurance-exchange-client-result/v1","status":"UNAVAILABLE","reason":str(exc)[:300]}));return 30
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status==200 and x.get("status")=="PASS" else 30

def recommendations(a)->int:
    _,url,key=policy_values(a.policy)
    q={"status":a.status}
    if a.project_id:q["project_id"]=a.project_id
    full=url+"/v1/recommendations?"+urllib.parse.urlencode(q)
    try:status,x=http(signed_request("GET",full,key))
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/assurance-exchange-client-result/v1","status":"UNAVAILABLE","reason":str(exc)[:300]}));return 30
    print(json.dumps(x,ensure_ascii=False));return 0 if status==200 else 30
def delivered(a)->int:
    _,url,key=policy_values(a.policy)
    body=json.dumps({"correlation_ids":a.correlation_id},separators=(",",":")).encode()
    try:status,x=http(signed_request("POST",url+"/v1/recommendations/delivered",key,body))
    except Exception:return 30
    print(json.dumps(x,ensure_ascii=False));return 0 if status==200 else 30
def observe(a)->int:
    _,url,_=policy_values(a.policy)
    payload={"schema":"chacha.dev/assurance-exchange-observation-ref/v1","source":a.source.upper(),"receipt_id":a.receipt_id}
    try:status,x=http(unsigned_json_request("POST",url+"/v1/observations",payload))
    except Exception as exc:
        print(json.dumps({"status":"UNAVAILABLE","reason":str(exc)[:300]}));return 30
    print(json.dumps(x,ensure_ascii=False));return 0 if status==200 else 20
def specialist_reviews(a)->int:
    _,url,key=policy_values(a.policy)
    q={"project_id":a.project_id,"revision":a.revision,"compromise_digest":a.compromise_digest}
    full=url+"/v1/specialist-reviews?"+urllib.parse.urlencode(q)
    try:status,x=http(signed_request("GET",full,key))
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/assurance-exchange-client-result/v1","status":"UNAVAILABLE","reason":str(exc)[:300]}));return 30
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status==200 else 30

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("recommendations");r.add_argument("--status",default="OPEN");r.add_argument("--project-id")
    sr=sub.add_parser("specialist-reviews");sr.add_argument("--project-id",required=True);sr.add_argument("--revision",required=True);sr.add_argument("--compromise-digest",required=True)
    pi=sub.add_parser("register-project-assurance-identity");pi.add_argument("--registration",type=Path,required=True)
    d=sub.add_parser("mark-delivered");d.add_argument("--correlation-id",action="append",required=True)
    o=sub.add_parser("observe");o.add_argument("--source",choices=["guardian","sentinel"],required=True);o.add_argument("--receipt-id",required=True)
    a=ap.parse_args()
    if a.cmd=="recommendations":return recommendations(a)
    if a.cmd=="specialist-reviews":return specialist_reviews(a)
    if a.cmd=="register-project-assurance-identity":return register_project_assurance_identity(a.policy,a.registration)
    if a.cmd=="mark-delivered":return delivered(a)
    return observe(a)
if __name__=="__main__":raise SystemExit(main())
