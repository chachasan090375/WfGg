#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)

if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  echo SERVER_EXPLORER_SSH_ROUTE=ChaChaVPS
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || { echo ERROR=VPS_UNREACHABLE; exit 1; }
  echo SERVER_EXPLORER_SSH_ROUTE=PUBLIC_IPV4
fi

echo '=== WfGg Radar · Server Explorer Sentinel ==='
TRACE="$(ssh "${SSH_OPTS[@]}" -T "$REMOTE" "journalctl -u wfgg-radar-connector.service --since '-15 min' --no-pager -o cat | grep 'SERVER_EXPLORER_SENTINEL' | tail -n 80 || true" </dev/null)"
if [[ -z "$TRACE" ]]; then
  echo SERVER_EXPLORER_TRACE=EMPTY
  echo SERVER_EXPLORER_HINT='Lancer une recherche Radar @servers:989-995 puis relancer cet inspecteur.'
  exit 0
fi

echo SERVER_EXPLORER_TRACE=FOUND
printf '%s\n' '--- TRACE ---'
printf '%s\n' "$TRACE"
printf '%s\n' '--- SUMMARY ---'
printf '%s\n' "$TRACE" | sed -nE 's/.*serverId=([^ ]+).*status=([^ ]+).*players=([^ ]+).*/SERVER_EXPLORER_SERVER=\1 STATUS=\2 PLAYERS=\3/p'
LAST="$(printf '%s\n' "$TRACE" | grep 'stage=DONE' | tail -n 1 || true)"
if [[ -n "$LAST" ]]; then
  TESTED="$(printf '%s\n' "$LAST" | sed -nE 's/.*tested=([^ ]+).*/\1/p')"
  ACCESSIBLE="$(printf '%s\n' "$LAST" | sed -nE 's/.*accessible=([^ ]+).*/\1/p')"
  [[ -n "$TESTED" ]] && echo SERVER_EXPLORER_TESTED="$TESTED"
  [[ -n "$ACCESSIBLE" ]] && echo SERVER_EXPLORER_ACCESSIBLE="$ACCESSIBLE"
  echo SERVER_EXPLORER_PROBE=COMPLETE
else
  echo SERVER_EXPLORER_PROBE=INCOMPLETE
fi
