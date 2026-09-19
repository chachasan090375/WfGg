#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="wfgg-radar-connector"
BIN="/opt/wfgg-radar/bin/radar-connector"

fail(){ printf 'RADAR_V6192_RUNTIME_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE

echo "RADAR_V6192_CONNECTOR_SHA=$(sha256sum "$BIN" | awk '{print $1}')"
grep -aFq 'WFGG_RADAR_CLUSTER_CATALOG_BUDGET_V6192' "$BIN" || fail CATALOG_BUDGET_MARKER_MISSING

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
import hashlib,hmac,json,os,secrets,time,urllib.request,urllib.error

path="/v1/collector/server-cluster-catalog"
ts=str(int(time.time()))
nonce=secrets.token_hex(16)
body=b""
canonical="\n".join(["GET",path,ts,nonce,hashlib.sha256(body).hexdigest()])
sig=hmac.new(os.environ["KEY"].encode(),canonical.encode(),hashlib.sha256).hexdigest()
req=urllib.request.Request(
    "http://127.0.0.1:8788"+path,
    method="GET",
    headers={
        "Accept":"application/json",
        "X-Radar-Timestamp":ts,
        "X-Radar-Nonce":nonce,
        "X-Radar-Signature":sig,
    },
)
started=time.monotonic()
try:
    with urllib.request.urlopen(req,timeout=90) as r:
        status=r.status
        d=json.load(r)
except urllib.error.HTTPError as e:
    status=e.code
    payload=e.read().decode("utf-8","replace")
    print("RADAR_V6192_CATALOG_HTTP="+str(status))
    print("RADAR_V6192_CATALOG_ERROR_BODY="+payload[:500].replace("\n"," "))
    raise
elapsed=int(round((time.monotonic()-started)*1000))
assert status==200,status
assert d.get("ok") is True,d
assert d.get("readonly") is True,d
assert d.get("catalogVersion")=="v6.17",d
seed=d.get("recommendedSeed") or {}
print("RADAR_V6192_CATALOG_HTTP=200")
print("RADAR_V6192_CATALOG_ELAPSED_MS="+str(elapsed))
print("RADAR_V6192_CONFIRMED_CLUSTERS="+str(d.get("confirmedClusterCount")))
print("RADAR_V6192_CONFIRMED_SERVERS="+str(d.get("confirmedServerCount")))
print("RADAR_V6192_FRONTIER_COUNT="+str(d.get("frontierCount")))
print("RADAR_V6192_RECOMMENDED_SERVER="+str(seed.get("serverId") or "NONE"))
print("RADAR_V6192_RECOMMENDED_COMMAND="+str(seed.get("command") or "NONE"))
print("RADAR_V6192_RECOMMENDED_PLAYERS="+str(seed.get("players") or "NONE"))
PY

echo "RADAR_V6192_READONLY=PASS"
echo "RADAR_V6192_RUNTIME_PROBE=PASS"
