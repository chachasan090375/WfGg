#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector"
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

curl -fsSL "$RAW/install-from-termux.sh" -o "$TMP/install-from-termux.sh"
bash "$TMP/install-from-termux.sh"

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  printf '%s\n' 'ASYNC_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || { printf '%s\n' 'ERROR=VPS_UNREACHABLE' >&2; exit 1; }
  printf '%s\n' 'ASYNC_SSH_ROUTE=PUBLIC_IPV4'
fi

ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'python3 - <<'"'"'PY'"'"'
import json, urllib.request
base="http://127.0.0.1:8790"

def get(path):
    with urllib.request.urlopen(base+path, timeout=15) as r:
        return json.load(r)

h=get("/health")
assert h.get("ok") is True
print("ASYNC_COLLECTOR_HEALTH=OK")

cy=get("/cycle/latest").get("cycle") or {}
cid=cy.get("id")
print("ASYNC_COLLECTOR_LATEST_CYCLE="+str(cid or "NONE"))
print("ASYNC_COLLECTOR_LATEST_STATUS="+str(cy.get("status") or "NONE"))

if cid:
    first=get(f"/cycle/changes?id={cid}&limit=1&offset=0").get("changes", [])
    far=get(f"/cycle/changes?id={cid}&limit=1&offset=999999").get("changes", [])
    if first:
        assert far == [], "OFFSET_NOT_APPLIED"
        print("ASYNC_COLLECTOR_CHANGES_OFFSET=OK")
    else:
        print("ASYNC_COLLECTOR_CHANGES_OFFSET=NO_CHANGES_TO_PROBE")
else:
    print("ASYNC_COLLECTOR_CHANGES_OFFSET=NO_CYCLE_TO_PROBE")
PY
systemctl is-active --quiet wfgg-radar-connector
systemctl is-active --quiet wfgg-collector
printf "ASYNC_RADAR_CONNECTOR_SERVICE=active\n"
printf "ASYNC_COLLECTOR_SERVICE=active\n"
sha256sum /opt/wfgg-radar/bin/radar-connector | awk '"'"'{print "ASYNC_RADAR_CONNECTOR_SHA="$1}'"'"'
sha256sum /opt/wfgg-radar/bin/radar-native-template | awk '"'"'{print "ASYNC_RADAR_NATIVE_SHA="$1}'"'"'
'

printf '%s\n' 'ASYNC_RADAR_ACTIVATION=OK'
