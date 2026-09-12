#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=12 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  echo SERVER_EXPLORER_SENTINEL_V2_SSH_ROUTE=ChaChaVPS
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || { echo ERROR=VPS_UNREACHABLE; exit 1; }
  echo SERVER_EXPLORER_SENTINEL_V2_SSH_ROUTE=PUBLIC_IPV4
fi

ssh "${SSH_OPTS[@]}" -T "$REMOTE" '
echo "=== SERVER EXPLORER ROUTE ==="
journalctl -u wfgg-radar-connector --since "-10 min" --no-pager -o cat | grep "SERVER_EXPLORER_SENTINEL" | tail -n 30 || true
echo
echo "=== PROTOCOL SENTINEL ==="
journalctl -u wfgg-radar-connector --since "-10 min" --no-pager -o cat | grep "SERVER_EXPLORER_PROTOCOL_SENTINEL" | tail -n 30 || true
LAST=$(journalctl -u wfgg-radar-connector --since "-10 min" --no-pager -o cat | grep "SERVER_EXPLORER_PROTOCOL_SENTINEL" | tail -n 1 || true)
echo
echo "=== VERDICT ==="
case "$LAST" in
  *nativeStage=MAP_PACKET_RX*) echo SERVER_EXPLORER_SENTINEL_VERDICT=MAP_RESPONSE_RECEIVED ;;
  *nativeStage=MAP_WRITE_OK*) echo SERVER_EXPLORER_SENTINEL_VERDICT=MAP_SENT_NO_RESPONSE_BEFORE_BUDGET ;;
  *nativeStage=SYNTHETIC_START*|*nativeStage=MAP_DISPATCH*) echo SERVER_EXPLORER_SENTINEL_VERDICT=MAP_PHASE_REACHED ;;
  *nativeStage=INIT_OK*) echo SERVER_EXPLORER_SENTINEL_VERDICT=INIT_OK_MAP_NOT_REACHED_BEFORE_BUDGET ;;
  *nativeStage=LOGIN_OK*) echo SERVER_EXPLORER_SENTINEL_VERDICT=LOGIN_OK_WAITING_INIT ;;
  *nativeStage=LOGIN_SENT*) echo SERVER_EXPLORER_SENTINEL_VERDICT=LOGIN_SENT_WAITING_RESPONSE ;;
  *nativeStage=DIAL_OK*) echo SERVER_EXPLORER_SENTINEL_VERDICT=DIAL_OK_LOGIN_NOT_SENT ;;
  *nativeStage=DIAL_START*) echo SERVER_EXPLORER_SENTINEL_VERDICT=DIAL_IN_PROGRESS ;;
  *nativeStage=PCAP_READY*) echo SERVER_EXPLORER_SENTINEL_VERDICT=PCAP_READY_BEFORE_DIAL ;;
  *) echo SERVER_EXPLORER_SENTINEL_VERDICT=NO_PROTOCOL_TRACE ;;
esac
' </dev/null
