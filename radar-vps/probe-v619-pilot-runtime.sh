#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="wfgg-radar-connector"
ROOT="/opt/wfgg-radar"
BIN="$ROOT/bin"
EXPECTED_CONNECTOR="54146e098cb0cabc80b06f3a15e6da38acfbe0da19fbbafbab3cd5b66057d573"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"

fail() { printf 'RADAR_V619_RUNTIME_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE

CONNECTOR_SHA="$(sha256sum "$BIN/radar-connector" | awk '{print $1}')"
NATIVE_SHA="$(sha256sum "$BIN/radar-native-template" | awk '{print $1}')"
printf 'RADAR_V619_CONNECTOR_SHA=%s\n' "$CONNECTOR_SHA"
printf 'RADAR_V619_NATIVE_SHA=%s\n' "$NATIVE_SHA"
[[ "$CONNECTOR_SHA" == "$EXPECTED_CONNECTOR" ]] || fail CONNECTOR_SHA_MISMATCH
[[ "$NATIVE_SHA" == "$EXPECTED_NATIVE" ]] || fail NATIVE_SHA_MISMATCH

CAPS="$("$BIN/radar-native-template" --capabilities)"
python3 - "$CAPS" <<'PY'
import json, sys
d=json.loads(sys.argv[1])
assert d.get("ok") is True
assert d.get("readonly") is True
assert d.get("profileCLI") is True
assert d.get("profileCommand") == "get.user.info.multi"
assert d.get("profileHandshake") == "v6.9.1"
print("RADAR_V619_HELPER_CAPABILITIES=PASS")
print("RADAR_V619_PROFILE_COMMAND="+str(d.get("profileCommand")))
print("RADAR_V619_PROFILE_HANDSHAKE="+str(d.get("profileHandshake")))
PY

PID="$(systemctl show -p MainPID --value "$SERVICE")"
[[ "$PID" =~ ^[0-9]+$ && "$PID" -gt 1 ]] || fail MAINPID_INVALID

KEY="$(
python3 - "$PID" <<'PY'
import sys
p=f"/proc/{sys.argv[1]}/environ"
raw=open(p,"rb").read().split(b"\0")
for item in raw:
    if item.startswith(b"RADAR_CONNECTOR_SHARED_KEY="):
        print(item.split(b"=",1)[1].decode())
        break
PY
)"
[[ "${#KEY}" -ge 32 ]] || fail SHARED_KEY_UNAVAILABLE
export KEY EXPECTED_CONNECTOR EXPECTED_NATIVE

python3 - <<'PY'
import hashlib, hmac, json, os, secrets, time, urllib.request
path="/v1/health"
ts=str(int(time.time()))
nonce=secrets.token_hex(16)
body=b""
canonical="\n".join(["GET",path,ts,nonce,hashlib.sha256(body).hexdigest()])
sig=hmac.new(os.environ["KEY"].encode(),canonical.encode(),hashlib.sha256).hexdigest()
req=urllib.request.Request(
    "http://127.0.0.1:8788"+path,
    method="GET",
    headers={
        "X-Radar-Timestamp": ts,
        "X-Radar-Nonce": nonce,
        "X-Radar-Signature": sig,
    },
)
with urllib.request.urlopen(req, timeout=15) as r:
    d=json.load(r)

assert d.get("ok") is True
assert d.get("readonly") is True

runtime=d.get("connectorRuntime") or {}
helper=d.get("nativeHelper") or {}

assert runtime.get("state") == "CONNECTOR_READY", runtime
assert runtime.get("profileExecDiagnostics") == "v6.9.2", runtime
assert runtime.get("sha256") == os.environ["EXPECTED_CONNECTOR"], runtime
assert helper.get("helperState") == "PROFILE_READY", helper
assert helper.get("profileCLI") is True, helper
assert helper.get("profileCommand") is True, helper
assert helper.get("helperSha256") == os.environ["EXPECTED_NATIVE"], helper

print("RADAR_V619_SIGNED_HEALTH=PASS")
print("RADAR_V619_CONNECTOR_STATE="+str(runtime.get("state")))
print("RADAR_V619_PROFILE_EXEC="+str(runtime.get("profileExecDiagnostics")))
print("RADAR_V619_HELPER_STATE="+str(helper.get("helperState")))
PY

printf 'RADAR_V619_SERVICE=active\n'
printf 'RADAR_V619_READONLY=PASS\n'
printf 'RADAR_V619_RUNTIME_PROBE=PASS\n'
