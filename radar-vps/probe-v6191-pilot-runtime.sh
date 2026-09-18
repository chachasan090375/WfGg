#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="wfgg-radar-connector"
ROOT="/opt/wfgg-radar"
BIN="$ROOT/bin"
DB="/opt/wfgg-collector/data/collector.db"
EXPECTED_CONNECTOR="d2add7beece7c4714b11a4128305c2a37ff7b307cab9bd44e9f092ba62a2fc51"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"

fail(){ printf 'RADAR_V6191_RUNTIME_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE

CONNECTOR_SHA="$(sha256sum "$BIN/radar-connector" | awk '{print $1}')"
NATIVE_SHA="$(sha256sum "$BIN/radar-native-template" | awk '{print $1}')"
echo "RADAR_V6191_CONNECTOR_SHA=$CONNECTOR_SHA"
echo "RADAR_V6191_NATIVE_SHA=$NATIVE_SHA"
[[ "$CONNECTOR_SHA" == "$EXPECTED_CONNECTOR" ]] || fail CONNECTOR_SHA
[[ "$NATIVE_SHA" == "$EXPECTED_NATIVE" ]] || fail NATIVE_SHA

grep -aFq '/v1/collector/profile/refresh' "$BIN/radar-connector" || fail PROFILE_REFRESH_ROUTE_MISSING
grep -aFq 'PROFILE_TARGET_REFRESH_FAILED' "$BIN/radar-connector" || fail PROFILE_ONLY_RUNTIME_MISSING
echo "RADAR_V6191_PROFILE_ROUTE_BINARY=PASS"

CAPS="$("$BIN/radar-native-template" --capabilities)"
python3 - "$CAPS" <<'PY'
import json,sys
d=json.loads(sys.argv[1])
assert d.get("ok") is True
assert d.get("readonly") is True
assert d.get("profileCLI") is True
assert d.get("profileCommand") == "get.user.info.multi"
assert d.get("profileHandshake") == "v6.9.1"
print("RADAR_V6191_HELPER_CAPABILITIES=PASS")
print("RADAR_V6191_PROFILE_COMMAND="+str(d.get("profileCommand")))
print("RADAR_V6191_PROFILE_HANDSHAKE="+str(d.get("profileHandshake")))
PY

python3 - "$DB" <<'PY'
import sqlite3,sys
db=sys.argv[1]
c=sqlite3.connect("file:"+db+"?mode=ro",uri=True)
tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
cols={r[1] for r in c.execute("PRAGMA table_info(observations)")}
for forbidden in ("army_power","army_kill","svip_level","country","avatar_ref"):
    assert forbidden not in cols, forbidden
print("COLLECTOR_TABLE_COUNT="+str(len(tables)))
assert len(tables)==11, tables
print("COLLECTOR_SCHEMA_UNCHANGED=PASS")
PY

PID="$(systemctl show -p MainPID --value "$SERVICE")"
[[ "$PID" =~ ^[0-9]+$ && "$PID" -gt 1 ]] || fail MAINPID
KEY="$(
python3 - "$PID" <<'PY'
import sys
raw=open(f"/proc/{sys.argv[1]}/environ","rb").read().split(b"\0")
for item in raw:
    if item.startswith(b"RADAR_CONNECTOR_SHARED_KEY="):
        print(item.split(b"=",1)[1].decode())
        break
PY
)"
[[ "${#KEY}" -ge 32 ]] || fail SHARED_KEY
export KEY EXPECTED_CONNECTOR EXPECTED_NATIVE

python3 - <<'PY'
import hashlib,hmac,json,os,secrets,time,urllib.request,urllib.error

def signed(method,path,body=b""):
    ts=str(int(time.time()))
    nonce=secrets.token_hex(16)
    canonical="\n".join([method,path,ts,nonce,hashlib.sha256(body).hexdigest()])
    sig=hmac.new(os.environ["KEY"].encode(),canonical.encode(),hashlib.sha256).hexdigest()
    return urllib.request.Request(
        "http://127.0.0.1:8788"+path,
        data=(body if method!="GET" else None),
        method=method,
        headers={
            "Content-Type":"application/json",
            "X-Radar-Timestamp":ts,
            "X-Radar-Nonce":nonce,
            "X-Radar-Signature":sig,
        },
    )

with urllib.request.urlopen(signed("GET","/v1/health"),timeout=15) as r:
    d=json.load(r)
assert d.get("ok") is True
assert d.get("readonly") is True
runtime=d.get("connectorRuntime") or {}
helper=d.get("nativeHelper") or {}
assert runtime.get("state")=="CONNECTOR_READY",runtime
assert runtime.get("sha256")==os.environ["EXPECTED_CONNECTOR"],runtime
assert helper.get("helperState")=="PROFILE_READY",helper
assert helper.get("helperSha256")==os.environ["EXPECTED_NATIVE"],helper
print("RADAR_V6191_SIGNED_HEALTH=PASS")
print("RADAR_V6191_CONNECTOR_STATE="+str(runtime.get("state")))
print("RADAR_V6191_HELPER_STATE="+str(helper.get("helperState")))

body=b"{}"
try:
    urllib.request.urlopen(signed("POST","/v1/collector/profile/refresh",body),timeout=15)
    raise AssertionError("empty profile refresh unexpectedly succeeded")
except urllib.error.HTTPError as e:
    payload=e.read().decode("utf-8","replace")
    assert e.code==400,(e.code,payload)
    assert "TOKEN_AND_UID_REQUIRED" in payload,payload
print("RADAR_V6191_PROFILE_ROUTE_LIVE=PASS")
print("RADAR_V6191_PROFILE_ROUTE_EXTERNAL_CALL=NO")
PY

echo "RADAR_V6191_SERVICE=active"
echo "RADAR_V6191_READONLY=PASS"
echo "RADAR_V6191_RUNTIME_PROBE=PASS"
