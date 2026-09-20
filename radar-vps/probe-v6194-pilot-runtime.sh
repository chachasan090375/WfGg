#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="wfgg-radar-connector"
BIN="/opt/wfgg-radar/bin/radar-connector"
EXPECTED_CONNECTOR="48dc8e85825d71ae2cda8e23b6f92ce0a2f1a5756336fbfcf232b27d728df096"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"

fail(){ printf 'RADAR_V6194_RUNTIME_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE
command -v python3 >/dev/null 2>&1 || fail PYTHON3_MISSING

ACTUAL_CONNECTOR="$(sha256sum "$BIN" | awk '{print $1}')"
ACTUAL_NATIVE="$(sha256sum /opt/wfgg-radar/bin/radar-native-template | awk '{print $1}')"
echo "RADAR_V6194_CONNECTOR_SHA=$ACTUAL_CONNECTOR"
echo "RADAR_V6194_NATIVE_SHA=$ACTUAL_NATIVE"
[[ "$ACTUAL_CONNECTOR" == "$EXPECTED_CONNECTOR" ]] || fail CONNECTOR_SHA_MISMATCH
[[ "$ACTUAL_NATIVE" == "$EXPECTED_NATIVE" ]] || fail NATIVE_SHA_MISMATCH

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
        headers={
            "Content-Type":"application/json",
            "X-Radar-Timestamp":ts,
            "X-Radar-Nonce":nonce,
            "X-Radar-Signature":sig,
        },
    )
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: payload=json.loads(raw)
        except Exception: payload={"raw":raw[:300]}
        return e.code,payload

# Start guard: no token means no game operation can execute.
status,payload=request("POST","/v1/collector/autopilot/start",{})
assert status==400,(status,payload)
assert payload.get("error")=="GAME_TOKEN_REQUIRED",payload
print("RADAR_V6194_START_ROUTE=PASS")
print("RADAR_V6194_START_ROUTE_GUARD=GAME_TOKEN_REQUIRED")

# Status and stop guards prove both control routes are loaded without starting a job.
status,payload=request("GET","/v1/collector/autopilot/status?id=does-not-exist")
assert status==404,(status,payload)
assert payload.get("error")=="AUTOPILOT_JOB_NOT_FOUND",payload
print("RADAR_V6194_STATUS_ROUTE=PASS")

status,payload=request("POST","/v1/collector/autopilot/stop",{"id":"does-not-exist"})
assert status==404,(status,payload)
assert payload.get("error")=="AUTOPILOT_JOB_NOT_FOUND",payload
print("RADAR_V6194_STOP_ROUTE=PASS")
PY

echo "RADAR_V6194_NO_GAME_SCAN_EXECUTED=YES"
echo "RADAR_V6194_COLLECTOR_MUTATION=NO"
echo "RADAR_V6194_RUNTIME_PROBE=PASS"
