#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)

if ssh "${SSH_OPTS[@]}" "$REMOTE" true </dev/null >/dev/null 2>&1; then
  echo "SSH_ROUTE=ChaChaVPS"
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" true </dev/null >/dev/null 2>&1 || {
    echo "ERROR=VPS_UNREACHABLE"
    exit 2
  }
  echo "SSH_ROUTE=PUBLIC_IPV4"
fi

ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'bash -s' </dev/null <<'REMOTE_SCRIPT'
set -Eeuo pipefail
SERVICE="wfgg-radar-connector"
ROOT="/opt/wfgg-radar"

echo "=== RADAR AUTH 500 DIAGNOSTIC ==="
printf 'RADAR_CONNECTOR_SERVICE='; systemctl is-active "$SERVICE" 2>/dev/null || true
printf 'RADAR_CONNECTOR_ENABLED='; systemctl is-enabled "$SERVICE" 2>/dev/null || true

if [[ -f "$ROOT/data/sentinel-vps-state.env" ]]; then
  grep -E '^SENTINEL_VPS_(STATUS|LAST_CHECK|CONNECTOR_SHA|NATIVE_SHA)=' "$ROOT/data/sentinel-vps-state.env" || true
fi

for f in "$ROOT/bin/radar-connector" "$ROOT/bin/radar-native-template"; do
  if [[ -f "$f" ]]; then
    name="$(basename "$f" | tr '[:lower:]-' '[:upper:]_')"
    sha="$(sha256sum "$f" | awk '{print $1}')"
    echo "${name}_SHA=$sha"
  fi
done

echo "=== SERVICE CONFIG SAFE ==="
systemctl show "$SERVICE" -p MainPID -p ExecMainStatus -p ActiveEnterTimestamp -p NRestarts --no-pager 2>/dev/null || true

echo "=== RECENT CONNECTOR EVENTS (REDACTED) ==="
journalctl -u "$SERVICE" --since '-15 min' --no-pager -o cat 2>/dev/null \
  | tail -n 160 \
  | sed -E \
      -e 's/(accessToken|token|authorization|bearer)[=:" ]+[A-Za-z0-9._~+\/-]+/\1=<REDACTED>/Ig' \
      -e 's/[A-Za-z0-9_-]{80,}/<REDACTED_LONG_VALUE>/g' \
  | grep -Ei 'auth|native|error|failed|panic|exit|status|http|login|session|template|timeout|reject|500|502|503' \
  | tail -n 80 || true

echo "=== END DIAGNOSTIC ==="
REMOTE_SCRIPT
