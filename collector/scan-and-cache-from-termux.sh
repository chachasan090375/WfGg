#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

QUERY="${1:-zazavibes}"
[[ -n "${QUERY//[[:space:]]/}" ]] || { echo 'ERROR=QUERY_REQUIRED'; exit 2; }

SCAN_URL="https://raw.githubusercontent.com/chachasan090375/WfGg/radar-production-v1/radar-vps/test-player-scan-direct-vps-from-termux.sh"
OUT="$(curl -fsSL "$SCAN_URL" | bash -s -- "$QUERY")"
printf '%s\n' "$OUT"

FIRST="$(printf '%s\n' "$OUT" | sed -n 's/^DIRECT_FIRST_PLAYER=//p' | head -n1)"
[[ -n "$FIRST" ]] || { echo 'COLLECTOR_CACHE=NO_PLAYER'; exit 0; }

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ! ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
fi

printf '%s' "$FIRST" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" python3 -c '
import sys,urllib.request
body=sys.stdin.buffer.read()
req=urllib.request.Request("http://127.0.0.1:8790/ingest",data=body,method="POST",headers={"Content-Type":"application/json"})
try:
    with urllib.request.urlopen(req,timeout=5) as r:
        print("COLLECTOR_CACHE="+r.read().decode())
except Exception:
    print("COLLECTOR_CACHE=UNAVAILABLE")
'
