#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

FILE="${1:-}"
[[ -n "$FILE" && -s "$FILE" ]] || { echo 'ERROR=JSON_FILE_REQUIRED'; exit 2; }
python3 - "$FILE" <<'PY' >/dev/null
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    json.load(f)
PY

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ! ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
fi

cat "$FILE" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" python3 -c '
import sys,urllib.request
body=sys.stdin.buffer.read()
req=urllib.request.Request("http://127.0.0.1:8790/ingest",data=body,method="POST",headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=10) as r:
    print(r.read().decode())
'
