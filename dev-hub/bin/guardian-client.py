#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,hashlib,json,subprocess,tempfile,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")
MAX_RESPONSE=2*1024*1024

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise RuntimeError("JSON_ROOT_NOT_OBJECT")
    return x

def public_b64(private_key:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(private_key),"-pubout","-outform","DER"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0: raise RuntimeError("GUARDIAN_PRIVATE_KEY_READ_FAILED")
    return base64.b64encode(p.stdout).decode()

def key_id(private_key:Path)->str:
    return "central-"+hashlib.sha256(public_b64(private_key).encode()).hexdigest()[:16]

def sign(private_key:Path,message:bytes)->str:
    with tempfile.NamedTemporaryFile(prefix="chacha-guardian-msg-",delete=True) as f:
        f.write(message);f.flush()
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private_key),"-in",f.name],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0: raise RuntimeError("GUARDIAN_SIGN_FAILED:"+p.stderr.decode(errors="replace")[-300:])
    return base64.urlsafe_b64encode(p.stdout).decode().rstrip("=")

def request_message(method:str,url:str,timestamp:str,body:bytes=b"")->bytes:
    u=urllib.parse.urlsplit(url)
    path=u.path or "/"
    if u.query:path+="?"+u.query
    return (timestamp+"\n"+method.upper()+"\n"+path+"\n").encode()+body

def signed_request(method:str,url:str,private_key:Path,body:bytes=b"")->urllib.request.Request:
    ts=now_iso();kid=key_id(private_key)
    headers={
      "User-Agent":"ChaCha-DEV-Guardian-Client/1.0",
      "Accept":"application/json",
      "X-ChaCha-Key-Id":kid,
      "X-ChaCha-Timestamp":ts,
      "X-ChaCha-Signature":sign(private_key,request_message(method,url,ts,body))
    }
    if method.upper()!="GET":headers["Content-Type"]="application/json"
    return urllib.request.Request(url,data=(body if method.upper()!="GET" else None),headers=headers,method=method.upper())

def http_json(req:urllib.request.Request,timeout:int=20)->tuple[int,dict[str,Any]]:
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE: raise RuntimeError("GUARDIAN_RESPONSE_TOO_LARGE")
            return r.status,json.loads(raw)
    except urllib.error.HTTPError as e:
        raw=e.read(MAX_RESPONSE+1)
        try:x=json.loads(raw)
        except Exception:x={"error":"guardian_http_error","status":e.code,"raw":raw.decode("utf-8","replace")[:1000]}
        return e.code,x

def policy_values(policy_path:Path):
    p=load(policy_path)
    url=str(p["external_url"]).rstrip("/")
    key=Path(p["private_key"])
    return p,url,key

def check(event_path:Path,policy_path:Path)->int:
    p,url,key=policy_values(policy_path)
    if not key.is_file():
        print(json.dumps({"schema":"chacha.dev/guardian-client-result/v1","status":"UNAVAILABLE",
                          "reason":"CENTRAL_PRIVATE_KEY_MISSING","policy":str(policy_path)}))
        return 30
    event=load(event_path)
    body=json.dumps(event,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    try:
        status,x=http_json(signed_request("POST",url+"/v1/check",key,body))
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/guardian-client-result/v1","status":"UNAVAILABLE",
                          "reason":type(exc).__name__+":"+str(exc)[:300]}))
        return 30
    print(json.dumps(x,ensure_ascii=False))
    verdict=str(x.get("verdict") or "")
    if verdict in {"PASS","WARNING"} and status==200:return 0
    if verdict=="BLOCK":return 20
    if verdict=="CRITICAL":return 21
    return 30

def alerts(policy_path:Path,status_filter:str,limit:int)->int:
    _,url,key=policy_values(policy_path)
    if not key.is_file():return 30
    q=urllib.parse.urlencode({"status":status_filter,"limit":max(1,min(limit,100))})
    try:
        status,x=http_json(signed_request("GET",url+"/v1/alerts?"+q,key))
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/guardian-client-result/v1","status":"UNAVAILABLE","reason":str(exc)[:300]}))
        return 30
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status==200 else 30

def ack(policy_path:Path,ids:list[str])->int:
    _,url,key=policy_values(policy_path)
    if not key.is_file():return 30
    body=json.dumps({"alert_ids":ids},separators=(",",":")).encode()
    try:
        status,x=http_json(signed_request("POST",url+"/v1/alerts/ack",key,body))
    except Exception:return 30
    print(json.dumps(x,ensure_ascii=False))
    return 0 if status==200 else 30

def coverage(policy_path:Path,snapshot:Path)->int:
    _,url,key=policy_values(policy_path)
    if not key.is_file():return 30
    payload=load(snapshot)
    body=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    try:
        status,x=http_json(signed_request("POST",url+"/v1/coverage",key,body))
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/guardian-client-result/v1","status":"UNAVAILABLE","reason":str(exc)[:300]}))
        return 30
    print(json.dumps(x,ensure_ascii=False))
    verdict=str(x.get("verdict") or "")
    if status==200 and verdict in {"PASS","WARNING"}:return 0
    if verdict=="BLOCK":return 20
    if verdict=="CRITICAL":return 21
    return 30

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    sub=ap.add_subparsers(dest="cmd",required=True)
    c=sub.add_parser("check");c.add_argument("--event",type=Path,required=True)
    a=sub.add_parser("alerts");a.add_argument("--status",default="OPEN");a.add_argument("--limit",type=int,default=25)
    k=sub.add_parser("ack");k.add_argument("--alert-id",action="append",required=True)
    v=sub.add_parser("coverage");v.add_argument("--snapshot",type=Path,required=True)
    args=ap.parse_args()
    if args.cmd=="check":return check(args.event,args.policy)
    if args.cmd=="alerts":return alerts(args.policy,args.status,args.limit)
    if args.cmd=="coverage":return coverage(args.policy,args.snapshot)
    return ack(args.policy,args.alert_id)

if __name__=="__main__":
    raise SystemExit(main())
