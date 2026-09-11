#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

QUERY="${1:-}"
[[ -n "${QUERY//[[:space:]]/}" ]] || { echo 'ERROR=QUERY_REQUIRED'; exit 2; }
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ! ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
fi
ENCODED="$(python3 - "$QUERY" <<'PY'
import sys,urllib.parse
print(urllib.parse.quote(sys.argv[1],safe=''),end='')
PY
)"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "python3 - <<'PY'
import urllib.request
u='http://127.0.0.1:8790/player?q=$ENCODED'
try:
    with urllib.request.urlopen(u,timeout=5) as r:
        print(r.read().decode())
except Exception as e:
    if hasattr(e,'read'):
        print(e.read().decode())
    else:
        print('{\"ok\":false,\"error\":\"COLLECTOR_UNREACHABLE\"}')
PY"
