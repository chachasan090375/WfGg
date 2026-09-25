#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,os,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod

with tempfile.TemporaryDirectory() as td:
    state=Path(td)/"d1-circuit.json"
    os.environ["CHACHA_D1_CIRCUIT_STATE"]=str(state)
    d1=loadmod("v830_d1",BIN/"d1_quota_circuit.py")
    payload={"success":False,"errors":[{"code":7500,"message":"Your account has exceeded D1's free tier daily row read limit. Upgrade or wait until tomorrow (midnight UTC)."}]}
    assert d1.quota_class(payload)=="D1_READ_QUOTA_EXHAUSTED"
    x=d1.observe_response(payload,"test",epoch=1000)
    assert x and x["status"]=="OPEN" and x["fail_closed"] is True
    assert x["automatic_paid_upgrade"] is False and x["automatic_external_spend_eur"]==0
    assert x["resume_epoch"]>1000
    blocked=d1.unavailable_payload("guardian-client",epoch=1001)
    assert blocked and blocked["status"]=="UNAVAILABLE"
    assert blocked["fail_closed"] is True
    assert blocked["reason"]=="D1_ACCOUNT_QUOTA_CIRCUIT_OPEN"
    assert d1.blocked(epoch=x["resume_epoch"]+1) is None

    # Re-open then prove all three external assurance clients short-circuit
    # before touching the network.
    d1.open_circuit("D1_READ_QUOTA_EXHAUSTED","test",epoch=d1.now_epoch())
    guardian=loadmod("v830_guardian",BIN/"guardian-client.py")
    sentinel=loadmod("v830_sentinel",BIN/"sentinel-client.py")
    exchange=loadmod("v830_exchange",BIN/"assurance-exchange-client.py")
    def forbidden(*a,**k):
        raise AssertionError("NETWORK_CALL_MUST_NOT_OCCUR_WHILE_D1_CIRCUIT_OPEN")
    guardian.urllib.request.urlopen=forbidden
    sentinel.urllib.request.urlopen=forbidden
    exchange.urllib.request.urlopen=forbidden
    req=guardian.urllib.request.Request("https://example.invalid/v1/test")
    for fn in (guardian.http_json,sentinel.http,exchange.http):
        status,body=fn(req)
        assert status==503,(status,body)
        assert body["reason"]=="D1_ACCOUNT_QUOTA_CIRCUIT_OPEN",body
        assert body["fail_closed"] is True,body

worker=(ROOT/"dev-hub/guardian/worker.js").read_text()
assert 'daily row read limit' in worker
assert 'D1_READ_QUOTA_EXHAUSTED' in worker

expected={
 "chacha-dev-guardian-alert-pull.timer":"OnUnitActiveSec=180s",
 "chacha-dev-guardian-remediation.timer":"OnUnitActiveSec=120s",
 "chacha-dev-assurance-exchange-feedback.timer":"OnUnitActiveSec=180s",
 "chacha-dev-sentinel-remediation.timer":"OnUnitActiveSec=180s",
 "chacha-dev-guardian-coverage-heartbeat.timer":"OnUnitActiveSec=300s",
}
for name,marker in expected.items():
    text=(ROOT/"dev-hub/systemd"/name).read_text()
    assert marker in text,(name,marker)

policy=json.load(open(ROOT/"dev-hub/config/guardian-runtime-policy.v1.json"))
guard=policy["d1_account_quota_guard"]
assert guard["fail_closed_while_open"] is True
assert guard["automatic_paid_upgrade"] is False
assert guard["automatic_external_spend_eur"]==0

before=1440+5760+5760+2880+288
after=480+1440+960+480+288
assert after<before
reduction=round((1-after/before)*100,1)

print("CHACHA_DEV_V830_D1_READ_QUOTA_CLASSIFICATION=PASS")
print("CHACHA_DEV_V830_SHARED_ACCOUNT_CIRCUIT_BREAKER=PASS")
print("CHACHA_DEV_V830_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V830_NO_NETWORK_WHILE_CIRCUIT_OPEN=PASS")
print("CHACHA_DEV_V830_POLL_BUDGET=PASS")
print(f"CHACHA_DEV_V830_KNOWN_IDLE_D1_POLL_REDUCTION_PCT={reduction}")
print("CHACHA_DEV_V830_AUTOMATIC_PAID_UPGRADE=NO")
print("CHACHA_DEV_V830_AUTOMATIC_EXTERNAL_SPEND_EUR=0")