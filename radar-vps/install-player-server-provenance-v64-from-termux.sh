#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RELEASE_COMMIT="ca836e2d3cc35814dcd05d6caba2863323ceafda"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/$RELEASE_COMMIT/radar-vps/player-server-provenance-v64-release"
RADAR_BIN_DIR="/opt/wfgg-radar/bin"
RADAR_CONNECTOR="$RADAR_BIN_DIR/radar-connector"
BACKUP_DIR="/opt/wfgg-radar/backups"
SERVICE="wfgg-radar-connector.service"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }

for cmd in curl ssh sha256sum grep cat; do
  command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'PROVENANCE_V64_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'PROVENANCE_V64_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Player Server Provenance V6.4 ==='
say '1/4 Téléchargement et vérification de la release isolée'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
(cd "$TMP" && sha256sum -c SHA256SUMS)
chmod 0755 "$TMP/radar-connector"
grep -aFq 'PLAYER_SERVER_PROVENANCE_V64' "$TMP/radar-connector" || die PROVENANCE_V64_MARKER_MISSING
grep -aFq 'WORLD_GET_BLOCK_TARGET' "$TMP/radar-connector" || die PROVENANCE_V64_SOURCE_MARKER_MISSING
grep -aFq 'rawServerId' "$TMP/radar-connector" || die PROVENANCE_V64_RAW_FIELD_MISSING
grep -aFq 'observedOnServerId' "$TMP/radar-connector" || die PROVENANCE_V64_OBSERVED_FIELD_MISSING
grep -aFq 'UNCLASSIFIED' "$TMP/radar-connector" || die PROVENANCE_V64_RAW_SEMANTICS_MISSING
say 'PROVENANCE_V64_RELEASE=OK'

say '2/4 Sauvegarde atomique du connecteur actuel'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_CONNECTOR="$BACKUP_DIR/radar-connector-before-provenance-v64-$STAMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o root -g root -m 0700 '$BACKUP_DIR'
test -x '$RADAR_CONNECTOR'
cp -a '$RADAR_CONNECTOR' '$BACKUP_CONNECTOR'
chmod 0700 '$BACKUP_CONNECTOR'
echo PROVENANCE_V64_BACKUP='$BACKUP_CONNECTOR'
sha256sum '$RADAR_CONNECTOR' | sed 's/^/PROVENANCE_V64_OLD_SHA256=/'
" </dev/null

say '3/4 Transfert puis installation avec rollback automatique'
RCON="/tmp/wfgg-provenance-v64-connector-$$"
cat "$TMP/radar-connector" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" "cat > '$RCON'"

ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
rollback(){
  echo PROVENANCE_V64_ROLLBACK=START
  install -o root -g root -m 0755 '$BACKUP_CONNECTOR' '$RADAR_CONNECTOR'
  systemctl restart '$SERVICE' || true
  echo PROVENANCE_V64_ROLLBACK=DONE
}
trap rollback HUP INT TERM ERR
install -o root -g root -m 0755 '$RCON' '$RADAR_CONNECTOR'
rm -f '$RCON'
systemctl restart '$SERVICE'
sleep 2
systemctl is-active --quiet '$SERVICE'
grep -aFq 'PLAYER_SERVER_PROVENANCE_V64' '$RADAR_CONNECTOR'
grep -aFq 'WORLD_GET_BLOCK_TARGET' '$RADAR_CONNECTOR'
grep -aFq 'rawServerId' '$RADAR_CONNECTOR'
grep -aFq 'observedOnServerId' '$RADAR_CONNECTOR'
trap - HUP INT TERM ERR
echo PROVENANCE_V64_SERVICE=\$(systemctl is-active '$SERVICE')
sha256sum '$RADAR_CONNECTOR' | sed 's/^/PROVENANCE_V64_NEW_SHA256=/'
" </dev/null

say '4/4 Contrôle final et invariants conservés'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
systemctl is-active --quiet '$SERVICE'
grep -aFq 'PLAYER_SERVER_PROVENANCE_V64' '$RADAR_CONNECTOR'
grep -aFq 'WORLD_GET_BLOCK_TARGET' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V63_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V631_TOPOLOGY' '$RADAR_CONNECTOR'
grep -aFq 'AUTO_CARTOGRAPHER_V633_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_EXPLORER_V6_SINGLE_SESSION' '$RADAR_CONNECTOR'
echo PROVENANCE_V64_CURRENT_SERVER=OBSERVED_MAP_TARGET
echo PROVENANCE_V64_RAW_SERVER=UNCLASSIFIED_EVIDENCE
echo PROVENANCE_V64_MANUAL_PLAYER_CHECK=NOT_REQUIRED
echo PROVENANCE_V64_SERVICE=active
" </dev/null

say 'PROVENANCE_V64_INSTALL=OK'
