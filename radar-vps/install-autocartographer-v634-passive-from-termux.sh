#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RELEASE_COMMIT="b2a29a62c36b0b3f6c4a828dd3ccc07bbc86a2d5"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/$RELEASE_COMMIT/radar-vps/autocartographer-v634-passive-release"
RADAR_BIN_DIR="/opt/wfgg-radar/bin"
RADAR_CONNECTOR="$RADAR_BIN_DIR/radar-connector"
BACKUP_DIR="/opt/wfgg-radar/backups"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh sha256sum grep cat; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'AUTO_CARTOGRAPHER_V634_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'AUTO_CARTOGRAPHER_V634_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Auto-Cartographer V6.3.4 PASSIVE ==='
say '1/4 Téléchargement et vérification de la release'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
grep '  radar-connector$' "$TMP/SHA256SUMS" > "$TMP/SHA256SUMS.connector"
(cd "$TMP" && sha256sum -c SHA256SUMS.connector >/dev/null)
chmod 0755 "$TMP/radar-connector"

grep -aFq 'AUTO_CARTOGRAPHER_V634_PASSIVE' "$TMP/radar-connector" || die V634_PASSIVE_MARKER_MISSING
grep -aFq '/v1/cartographer/status' "$TMP/radar-connector" || die V634_STATUS_ROUTE_MISSING
grep -aFq 'PASSIVE_ONLY' "$TMP/radar-connector" || die V634_PASSIVE_MODE_MISSING
grep -aFq 'EXISTING_COLLECTOR_SCAN' "$TMP/radar-connector" || die V634_PASSIVE_SOURCE_MISSING
if grep -aFq 'POST /v1/cartographer/tick' "$TMP/radar-connector"; then die V633_ACTIVE_TICK_ROUTE_STILL_PRESENT; fi
grep -aFq 'FEDERATED_COLLECTOR_V631_TOPOLOGY' "$TMP/radar-connector" || die FEDERATED_V631_TOPOLOGY_MISSING
grep -aFq 'SERVER_DISCOVERY_V62_SENTINEL' "$TMP/radar-connector" || die SERVER_EXPLORER_V62_MISSING
say 'AUTO_CARTOGRAPHER_V634_RELEASE=OK'
say 'AUTO_CARTOGRAPHER_V634_ACTIVE_PROBES=NO'
say 'AUTO_CARTOGRAPHER_V634_GAME_TOKEN_RETENTION=NO'
say 'AUTO_CARTOGRAPHER_V634_BACKGROUND_GAME_CALLS=NO'

say '2/4 Sauvegarde atomique du connecteur actuel'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_CONNECTOR="$BACKUP_DIR/radar-connector-before-autocart-v634-passive-$STAMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o root -g root -m 0700 '$BACKUP_DIR'
test -x '$RADAR_CONNECTOR'
cp -a '$RADAR_CONNECTOR' '$BACKUP_CONNECTOR'
chmod 0700 '$BACKUP_CONNECTOR'
echo AUTO_CARTOGRAPHER_V634_BACKUP_CONNECTOR='$BACKUP_CONNECTOR'
" </dev/null

say '3/4 Transfert SSH et installation avec rollback automatique'
RCON="/tmp/wfgg-autocart-v634-passive-connector-$$"
cat "$TMP/radar-connector" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" "cat > '$RCON'"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
rollback(){
  echo AUTO_CARTOGRAPHER_V634_ROLLBACK=START
  install -o root -g root -m 0755 '$BACKUP_CONNECTOR' '$RADAR_CONNECTOR'
  systemctl restart wfgg-radar-connector.service || true
  echo AUTO_CARTOGRAPHER_V634_ROLLBACK=DONE
}
trap rollback HUP INT TERM ERR
install -o root -g root -m 0755 '$RCON' '$RADAR_CONNECTOR'
rm -f '$RCON'
systemctl restart wfgg-radar-connector.service
sleep 2
systemctl is-active --quiet wfgg-radar-connector.service
grep -aFq 'AUTO_CARTOGRAPHER_V634_PASSIVE' '$RADAR_CONNECTOR'
grep -aFq '/v1/cartographer/status' '$RADAR_CONNECTOR'
! grep -aFq 'POST /v1/cartographer/tick' '$RADAR_CONNECTOR'
trap - HUP INT TERM ERR
echo AUTO_CARTOGRAPHER_V634_SERVICE=\$(systemctl is-active wfgg-radar-connector.service)
" </dev/null

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
grep -aFq 'AUTO_CARTOGRAPHER_V634_PASSIVE' '$RADAR_CONNECTOR'
grep -aFq '/v1/cartographer/status' '$RADAR_CONNECTOR'
grep -aFq 'PASSIVE_ONLY' '$RADAR_CONNECTOR'
grep -aFq 'EXISTING_COLLECTOR_SCAN' '$RADAR_CONNECTOR'
! grep -aFq 'POST /v1/cartographer/tick' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V63_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V631_TOPOLOGY' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_DISCOVERY_V62_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_EXPLORER_V6_SINGLE_SESSION' '$RADAR_CONNECTOR'
echo AUTO_CARTOGRAPHER_V634_MODE=PASSIVE_ONLY
echo AUTO_CARTOGRAPHER_V634_ENDPOINT=/v1/cartographer/status
echo AUTO_CARTOGRAPHER_V634_ACTIVE_PROBES=NO
echo AUTO_CARTOGRAPHER_V634_GAME_TOKEN_RETENTION=NO
echo AUTO_CARTOGRAPHER_V634_BACKGROUND_GAME_CALLS=NO
echo SERVER_EXPLORER_V62=PRESERVED
echo FEDERATED_V632=PRESERVED
" </dev/null

say 'AUTO_CARTOGRAPHER_V634_PASSIVE=OK'
