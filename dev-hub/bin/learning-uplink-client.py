#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,hmac,json,os,time,urllib.request
from pathlib import Path

def canon(x): return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    e=sub.add_parser("emit");e.add_argument("--delta",type=Path,required=True);e.add_argument("--spool",type=Path,required=True);e.add_argument("--key-id",required=True)
    f=sub.add_parser("flush");f.add_argument("--spool",type=Path,required=True);f.add_argument("--endpoint",required=True)
    a=ap.parse_args()
    secret=os.environ.get("CHACHA_LEARNING_UPLINK_SECRET","")
    if not secret: raise SystemExit("LEARNING_UPLINK_SECRET_REQUIRED")
    if a.cmd=="emit":
        x=json.loads(a.delta.read_text(encoding="utf-8"));p=x.get("privacy") or {}
        if p.get("raw_user_content") is not False or p.get("contains_secrets") is not False: raise SystemExit("LEARNING_UPLINK_PRIVACY_BLOCK")
        sig=hmac.new(secret.encode(),canon(x),hashlib.sha256).hexdigest()
        packet={"schema":"chacha.dev/learning-uplink-packet/v1","key_id":a.key_id,"algorithm":"HMAC-SHA256","signature":sig,"delta":x}
        a.spool.mkdir(parents=True,exist_ok=True);os.chmod(a.spool,0o700)
        path=a.spool/(str(x["delta_id"])+".json");path.write_text(json.dumps(packet,separators=(",",":"))+"\n",encoding="utf-8");os.chmod(path,0o600)
        print("CHACHA_LEARNING_UPLINK_SPOOLED="+str(path));return
    if not a.endpoint.startswith("https://"): raise SystemExit("LEARNING_UPLINK_HTTPS_REQUIRED")
    sent=0
    for path in sorted(a.spool.glob("*.json")):
        raw=path.read_bytes();req=urllib.request.Request(a.endpoint,data=raw,headers={"Content-Type":"application/json","User-Agent":"ChaCha-Learning-Uplink/1"},method="POST")
        with urllib.request.urlopen(req,timeout=20) as r:
            if not 200<=r.status<300: raise SystemExit("LEARNING_UPLINK_HTTP_FAILED")
        path.unlink();sent+=1
    print("CHACHA_LEARNING_UPLINK_FLUSHED="+str(sent))
if __name__=="__main__":main()
