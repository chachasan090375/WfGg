#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  echo FEDERATED_V631_INSPECT_SSH_ROUTE=ChaChaVPS
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  echo FEDERATED_V631_INSPECT_SSH_ROUTE=PUBLIC_IPV4
fi

ssh "${SSH_OPTS[@]}" -T "$REMOTE" '
echo "=== FEDERATED V6.3.1 TOPOLOGY ==="
journalctl -u wfgg-radar-connector --since "-15 min" --no-pager -o cat |
  grep -E "FEDERATED_COLLECTOR_V631_TOPOLOGY|FEDERATED_COLLECTOR_V63_SENTINEL" |
  tail -n 180 || true

echo
echo "=== CONNECTOR HEALTH ==="
systemctl is-active wfgg-radar-connector || true
grep -aFq "FEDERATED_COLLECTOR_V631_TOPOLOGY" /opt/wfgg-radar/bin/radar-connector && echo FEDERATED_V631_CONNECTOR=READY || true
grep -aFq "WFGG_FEDERATED_MAP_ONLY" /opt/wfgg-radar/bin/radar-native-template && echo FEDERATED_V63_NATIVE=READY || true

echo
echo "=== COLLECTOR HEALTH ==="
curl -fsS http://127.0.0.1:8790/health 2>/dev/null || true
echo
'
