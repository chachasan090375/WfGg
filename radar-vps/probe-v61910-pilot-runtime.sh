#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="wfgg-radar-connector"
BIN="/opt/wfgg-radar/bin/radar-connector"
NATIVE="/opt/wfgg-radar/bin/radar-native-template"
EXPECTED_CONNECTOR="18b972ebd63ea34de6e67c432c863598da1769fa33559115728a2e20d5015863"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"

fail(){ printf 'RADAR_V61910_RUNTIME_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE
command -v python3 >/dev/null 2>&1 || fail PYTHON3_MISSING

ACTUAL_CONNECTOR="$(sha256sum "$BIN" | awk '{print $1}')"
ACTUAL_NATIVE="$(sha256sum "$NATIVE" | awk '{print $1}')"
echo "RADAR_V61910_CONNECTOR_SHA=$ACTUAL_CONNECTOR"
echo "RADAR_V61910_NATIVE_SHA=$ACTUAL_NATIVE"
[[ "$ACTUAL_CONNECTOR" == "$EXPECTED_CONNECTOR" ]] || fail CONNECTOR_SHA_MISMATCH
[[ "$ACTUAL_NATIVE" == "$EXPECTED_NATIVE" ]] || fail NATIVE_SHA_MISMATCH

grep -aFq 'v6.19.10' "$BIN" || fail VERSION_MARKER_MISSING
grep -aFq 'SEED_SKIPPED_PARTIAL' "$BIN" || fail PARTIAL_SKIP_MARKER_MISSING
grep -aFq 'PARTIAL_AFTER_RETRIES' "$BIN" || fail PARTIAL_REASON_MARKER_MISSING
grep -aFq 'AUTOPILOT_PARTIAL_SKIP_INVARIANT' "$BIN" || fail PARTIAL_INVARIANT_MARKER_MISSING
grep -aFq 'AUTOPILOT_TARGET_HISTORY_TIMEOUT_V6199' "$BIN" || fail V6199_TARGETED_HISTORY_MARKER_MISSING
grep -aFq 'COLLECTOR_CYCLE_TERMINALIZATION_FAILED' "$BIN" || fail V6198_TERMINALIZATION_MARKER_MISSING
grep -aFq 'STALE_RUNNING_CYCLE_RECOVERED_V6197' "$BIN" || fail V6197_STALE_RECOVERY_MARKER_MISSING
grep -aFq 'SEED_SKIPPED_NO_DATA' "$BIN" || fail V6196_SKIP_MARKER_MISSING
grep -aFq 'AUTOPILOT_NO_DATA' "$BIN" || fail V6196_NO_DATA_MARKER_MISSING
echo "RADAR_V61910_CONTINUE_PARTIAL_MARKERS=PASS"

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
            return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: payload=json.loads(raw)
        except Exception: payload={"raw":raw[:300]}
        return e.code,payload

status,payload=request("POST","/v1/collector/autopilot/start",{})
assert status==400,(status,payload)
assert payload.get("error")=="GAME_TOKEN_REQUIRED",payload
print("RADAR_V61910_START_ROUTE_GUARD=PASS")

status,payload=request("GET","/v1/collector/autopilot/status?id=does-not-exist")
assert status==404,(status,payload)
assert payload.get("error")=="AUTOPILOT_JOB_NOT_FOUND",payload
print("RADAR_V61910_STATUS_ROUTE_GUARD=PASS")

status,payload=request("POST","/v1/collector/autopilot/stop",{"id":"does-not-exist"})
assert status==404,(status,payload)
assert payload.get("error")=="AUTOPILOT_JOB_NOT_FOUND",payload
print("RADAR_V61910_STOP_ROUTE_GUARD=PASS")
PY

echo "RADAR_V61910_GAME_SCAN_EXECUTED=NO"
echo "RADAR_V61910_COLLECTOR_MUTATION=NO"
echo "RADAR_V61910_RUNTIME_PROBE=PASS"
