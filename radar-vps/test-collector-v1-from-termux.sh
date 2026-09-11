#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

QUERY="${1:-zazavibes}"
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)

if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  echo 'SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || {
    echo 'ERROR=VPS_UNREACHABLE'
    exit 2
  }
  echo 'SSH_ROUTE=PUBLIC_IPV4'
fi

ENCODED="$(python3 - "$QUERY" <<'PY'
import sys,urllib.parse
print(urllib.parse.quote(sys.argv[1],safe=''),end='')
PY
)"

ssh "${SSH_OPTS[@]}" -T "$REMOTE" "set -e
printf '%s\\n' '=== HEALTH ==='
curl -fsS http://127.0.0.1:8791/health
printf '\\n%s\\n' '=== STATS ==='
curl -fsS http://127.0.0.1:8791/stats
printf '\\n%s\\n' '=== PLAYER ==='
curl -fsS 'http://127.0.0.1:8791/player?q=$ENCODED'
printf '\\n'
"
