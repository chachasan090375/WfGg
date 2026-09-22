#!/usr/bin/env python3
from __future__ import annotations
import hashlib,hmac,json,os,socket,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
INGRESS=ROOT/"dev-hub/bin/central-learning-ingress.py"
INGEST=ROOT/"dev-hub/bin/learning-delta-ingest.py"
CFG=json.load(open(ROOT/"dev-hub/config/central-learning-ingress.v1.json",encoding="utf-8"))
assert CFG["scope"]=="PLATFORM_GLOBAL"
assert CFG["app_specific"] is False
assert CFG["core"]["public_bind_forbidden"] is True
assert CFG["edge"]["provider_neutral"] is True
assert CFG["economics"]["automatic_external_spend_eur"]==0

def free_port():
    s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();return p

with tempfile.TemporaryDirectory(prefix="chacha-v67-ingress-") as td:
    td=Path(td);port=free_port();keys=td/"keys.json";db=td/"deltas.db";q=td/"q"
    secret="this-is-a-long-ci-secret-0123456789"
    keys.write_text(json.dumps({"schema":"chacha.dev/learning-ingress-keys/v1","keys":{"deploy-a":{"status":"ACTIVE","secret":secret,"project_ids":["app-a"],"deployment_ids":["prod-a"]}}}))
    proc=subprocess.Popen(["python3",str(INGRESS),"--bind","127.0.0.1","--port",str(port),"--key-registry",str(keys),"--delta-db",str(db),"--ingest",str(INGEST),"--anomaly-queue",str(q)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz",timeout=.5) as r:
                    if r.status==200:break
            except Exception:time.sleep(.1)
        else:raise AssertionError("ingress_not_ready")
        delta={"schema":"chacha.dev/learning-delta/v1","delta_id":"delta-v67-0001","project_id":"app-a","source_id":"agent-a","source_kind":"embedded-application-agent","deployment_id":"prod-a","sequence":1,"observed_at":"2026-09-22T15:00:00Z","changes":[{"path":"policy.cache","before":"a","after":"b"}],"anomaly":{"severity":"high","class":"behavior-drift"},"evidence_refs":["metric://drift"],"privacy":{"raw_user_content":False,"contains_secrets":False,"personal_data_class":"aggregated"}}
        raw=json.dumps(delta,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
        sig=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
        packet={"schema":"chacha.dev/learning-uplink-packet/v1","key_id":"deploy-a","algorithm":"HMAC-SHA256","signature":sig,"delta":delta}
        req=urllib.request.Request(f"http://127.0.0.1:{port}/v1/learning-deltas",data=json.dumps(packet).encode(),headers={"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=5) as r: ack=json.loads(r.read())
        assert ack["status"]=="RECORDED",ack
        assert ack["remediation_candidate"] is True,ack
        assert q.joinpath("delta-v67-0001.json").is_file()
        with urllib.request.urlopen(req,timeout=5) as r: ack2=json.loads(r.read())
        assert ack2["status"]=="DEDUPLICATED",ack2
        bad=dict(packet);bad["signature"]="0"*64
        req2=urllib.request.Request(f"http://127.0.0.1:{port}/v1/learning-deltas",data=json.dumps(bad).encode(),headers={"Content-Type":"application/json"},method="POST")
        try:urllib.request.urlopen(req2,timeout=5);raise AssertionError("bad_signature_accepted")
        except urllib.error.HTTPError as e:assert e.code==403
    finally:
        proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill()
print("CHACHA_DEV_V67_PLATFORM_GLOBAL_INGRESS=PASS")
print("CHACHA_DEV_V67_HMAC_AUTH=PASS")
print("CHACHA_DEV_V67_INCREMENTAL_INGEST=PASS")
print("CHACHA_DEV_V67_REPLAY_DEDUP=PASS")
print("CHACHA_DEV_V67_ANOMALY_QUEUE=PASS")
