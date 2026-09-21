#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="wfgg-radar-connector"
BIN="/opt/wfgg-radar/bin/radar-connector"
NATIVE="/opt/wfgg-radar/bin/radar-native-template"
EXPECTED_CONNECTOR="4d66709f10d3a6b27ac255a1dfdc62e51d2817652634409ffe2edc071762c69f"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"

fail(){ printf 'RADAR_V61911_GUARD_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE
command -v python3 >/dev/null 2>&1 || fail PYTHON3_MISSING

ACTUAL_CONNECTOR="$(sha256sum "$BIN" | awk '{print $1}')"
ACTUAL_NATIVE="$(sha256sum "$NATIVE" | awk '{print $1}')"
echo "RADAR_V61911_CONNECTOR_SHA=$ACTUAL_CONNECTOR"
echo "RADAR_V61911_NATIVE_SHA=$ACTUAL_NATIVE"
[[ "$ACTUAL_CONNECTOR" == "$EXPECTED_CONNECTOR" ]] || fail CONNECTOR_SHA_MISMATCH
[[ "$ACTUAL_NATIVE" == "$EXPECTED_NATIVE" ]] || fail NATIVE_SHA_MISMATCH

grep -aFq 'MANUAL_SEARCH_STOPPED' "$BIN" || fail MANUAL_STOP_MARKER_MISSING
grep -aFq '/v1/collector/search/stop' "$BIN" || fail STOP_ROUTE_MARKER_MISSING
echo "RADAR_V61911_MANUAL_STOP_MARKERS=PASS"

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
export KEY

python3 - <<'PY'
import hashlib,hmac,json,os,secrets,time,urllib.request,urllib.error,urllib.parse

def request(method,path,body_obj=None):
    body=b"" if body_obj is None else json.dumps(body_obj,separators=(",",":")).encode()
    ts=str(int(time.time()))
    nonce=secrets.token_hex(16)
    canonical_path=urllib.parse.urlsplit(path).path
    canonical="\n".join([method,canonical_path,ts,nonce,hashlib.sha256(body).hexdigest()])
    sig=hmac.new(os.environ["KEY"].encode(),canonical.encode(),hashlib.sha256).hexdigest()
    req=urllib.request.Request(
        "http://127.0.0.1:8788"+path,
        data=body if method!="GET" else None,
        method=method,
        headers={"Content-Type":"application/json","X-Radar-Timestamp":ts,"X-Radar-Nonce":nonce,"X-Radar-Signature":sig},
    )
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            raw=r.read().decode()
            return r.status,json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: payload=json.loads(raw)
        except Exception: payload={"raw":raw[:300]}
        return e.code,payload

status,payload=request("POST","/v1/collector/search/stop",{"id":"guard-nonexistent-v61911"})
assert status==404,(status,payload)
assert payload.get("error")=="JOB_NOT_FOUND",payload
print("RADAR_V61911_STOP_ROUTE_GUARD=PASS")

status,payload=request("POST","/v1/collector/search/stop",{"id":""})
assert status==400,(status,payload)
assert payload.get("error")=="COLLECTOR_JOB_ID_REQUIRED",payload
print("RADAR_V61911_STOP_INPUT_GUARD=PASS")

status,payload=request("GET","/v1/collector/search/status?id=guard-nonexistent-v61911")
assert status==404,(status,payload)
assert payload.get("error")=="JOB_NOT_FOUND",payload
print("RADAR_V61911_STATUS_ROUTE_GUARD=PASS")
PY

echo "RADAR_V61911_GAME_SCAN_EXECUTED=NO"
echo "RADAR_V61911_COLLECTOR_MUTATION=NO"
echo "RADAR_V61911_LASTWAR_MODE=READ_ONLY"
echo "RADAR_V61911_TOKEN_READ=NO"
echo "RADAR_V61911_TOKEN_PERSISTENCE=NO"
echo "RADAR_V61911_PRODUCTION_DEPLOYMENT=NO"
echo "RADAR_V61911_GUARD_PROBE=PASS"
