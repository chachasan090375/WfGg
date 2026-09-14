#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  echo SERVER_EXPLORER_V61_SSH_ROUTE=ChaChaVPS
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || { echo ERROR=VPS_UNREACHABLE; exit 1; }
  echo SERVER_EXPLORER_V61_SSH_ROUTE=PUBLIC_IPV4
fi

ssh "${SSH_OPTS[@]}" -T "$REMOTE" '
echo "=== V6.1 DISCOVERY ==="
journalctl -u wfgg-radar-connector --since "-10 min" --no-pager -o cat |
grep "SERVER_DISCOVERY_V61_SENTINEL\|SERVER_EXPLORER_V6_SENTINEL" |
tail -n 60

echo
echo "=== V5 FALLBACK / ROUTE ==="
journalctl -u wfgg-radar-connector --since "-10 min" --no-pager -o cat |
grep "SERVER_EXPLORER_SENTINEL" |
tail -n 30 || true

echo
echo "=== PROTOCOL ==="
journalctl -u wfgg-radar-connector --since "-10 min" --no-pager -o cat |
grep "SERVER_EXPLORER_PROTOCOL_SENTINEL" |
tail -n 20 || true
'
