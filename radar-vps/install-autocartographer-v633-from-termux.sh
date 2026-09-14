#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RELEASE_COMMIT="ec429bf5daa60599d9227e773aceaf3f52d73567"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/$RELEASE_COMMIT/radar-vps/federated-collector-v63-release"
RADAR_BIN_DIR="/opt/wfgg-radar/bin"
RADAR_CONNECTOR="$RADAR_BIN_DIR/radar-connector"
RADAR_NATIVE="$RADAR_BIN_DIR/radar-native-template"
BACKUP_DIR="/opt/wfgg-radar/backups"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh sha256sum grep cat; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'AUTO_CARTOGRAPHER_V633_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'AUTO_CARTOGRAPHER_V633_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Auto-Cartographer V6.3.3 ==='
say '1/4 Téléchargement et vérification de la release'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
curl -fsSL "$RAW/radar-native-template?ts=$TS" -o "$TMP/radar-native-template"
(cd "$TMP" && sha256sum -c SHA256SUMS >/dev/null)
chmod 0755 "$TMP/radar-connector" "$TMP/radar-native-template"
grep -aFq 'AUTO_CARTOGRAPHER_V633_SENTINEL' "$TMP/radar-connector" || die AUTO_CARTOGRAPHER_V633_MARKER_MISSING
grep -aFq '/v1/cartographer/tick' "$TMP/radar-connector" || die AUTO_CARTOGRAPHER_V633_ROUTE_MISSING
grep -aFq 'FEDERATED_COLLECTOR_V631_TOPOLOGY' "$TMP/radar-connector" || die FEDERATED_V631_TOPOLOGY_MISSING
grep -aFq 'SERVER_DISCOVERY_V62_SENTINEL' "$TMP/radar-connector" || die SERVER_EXPLORER_V62_MISSING
grep -aFq 'world.get.block(batch-v6)' "$TMP/radar-native-template" || die NATIVE_V6_MISSING
say 'AUTO_CARTOGRAPHER_V633_RELEASE=OK'

say '2/4 Sauvegarde atomique des binaires actuels'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_CONNECTOR="$BACKUP_DIR/radar-connector-before-autocart-v633-$STAMP"
BACKUP_NATIVE="$BACKUP_DIR/radar-native-template-before-autocart-v633-$STAMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o root -g root -m 0700 '$BACKUP_DIR'
test -x '$RADAR_CONNECTOR'
test -x '$RADAR_NATIVE'
cp -a '$RADAR_CONNECTOR' '$BACKUP_CONNECTOR'
cp -a '$RADAR_NATIVE' '$BACKUP_NATIVE'
chmod 0700 '$BACKUP_CONNECTOR' '$BACKUP_NATIVE'
echo AUTO_CARTOGRAPHER_V633_BACKUP_CONNECTOR='$BACKUP_CONNECTOR'
echo AUTO_CARTOGRAPHER_V633_BACKUP_NATIVE='$BACKUP_NATIVE'
" </dev/null

say '3/4 Transfert SSH et installation avec rollback automatique'
RCON="/tmp/wfgg-autocart-v633-connector-$$"
RNAT="/tmp/wfgg-autocart-v633-native-$$"
cat "$TMP/radar-connector" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" "cat > '$RCON'"
cat "$TMP/radar-native-template" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" "cat > '$RNAT'"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
rollback(){
  echo AUTO_CARTOGRAPHER_V633_ROLLBACK=START
  install -o root -g root -m 0755 '$BACKUP_CONNECTOR' '$RADAR_CONNECTOR'
  install -o root -g root -m 0755 '$BACKUP_NATIVE' '$RADAR_NATIVE'
  systemctl restart wfgg-radar-connector.service || true
  echo AUTO_CARTOGRAPHER_V633_ROLLBACK=DONE
}
trap rollback HUP INT TERM ERR
install -o root -g root -m 0755 '$RCON' '$RADAR_CONNECTOR'
install -o root -g root -m 0755 '$RNAT' '$RADAR_NATIVE'
rm -f '$RCON' '$RNAT'
systemctl restart wfgg-radar-connector.service
sleep 2
systemctl is-active --quiet wfgg-radar-connector.service
grep -aFq 'AUTO_CARTOGRAPHER_V633_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq '/v1/cartographer/tick' '$RADAR_CONNECTOR'
trap - HUP INT TERM ERR
echo AUTO_CARTOGRAPHER_V633_SERVICE=\$(systemctl is-active wfgg-radar-connector.service)
" </dev/null

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
grep -aFq 'AUTO_CARTOGRAPHER_V633_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq '/v1/cartographer/tick' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V63_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V631_TOPOLOGY' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_DISCOVERY_V62_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_EXPLORER_V6_SINGLE_SESSION' '$RADAR_CONNECTOR'
grep -aFq 'world.get.block(batch-v6)' '$RADAR_NATIVE'
echo AUTO_CARTOGRAPHER_V633_ENDPOINT=/v1/cartographer/tick
echo AUTO_CARTOGRAPHER_V633_PROBE_REGION=2
echo AUTO_CARTOGRAPHER_V633_CONFIRMATIONS=2
echo SERVER_EXPLORER_V62=PRESERVED
echo FEDERATED_V632=PRESERVED
" </dev/null

say 'AUTO_CARTOGRAPHER_V633=OK'
