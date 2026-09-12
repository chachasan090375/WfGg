#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RELEASE_COMMIT="d997357f111c95a1f74ecdd93ae3761343e5812e"
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
  say 'FEDERATED_V63_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'FEDERATED_V63_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Federated Collector V6.3 · canary ==='
say '1/4 Téléchargement et vérification de la release'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
curl -fsSL "$RAW/radar-native-template?ts=$TS" -o "$TMP/radar-native-template"
(cd "$TMP" && sha256sum -c SHA256SUMS >/dev/null)
chmod 0755 "$TMP/radar-connector" "$TMP/radar-native-template"
grep -aFq 'FEDERATED_COLLECTOR_V63_SENTINEL' "$TMP/radar-connector" || die FEDERATED_V63_CONNECTOR_MARKER_MISSING
grep -aFq 'FEDERATED_COLLECTOR_V63_CANARY' "$TMP/radar-connector" || die FEDERATED_V63_CANARY_MARKER_MISSING
grep -aFq '@federated:' "$TMP/radar-connector" || die FEDERATED_V63_ROUTE_MISSING
grep -aFq 'WFGG_FEDERATED_MAP_ONLY' "$TMP/radar-native-template" || die FEDERATED_V63_NATIVE_MAP_ONLY_MISSING
grep -aFq 'WFGG_FEDERATED_ORIGIN_INDEX' "$TMP/radar-native-template" || die FEDERATED_V63_NATIVE_REGION_MISSING
grep -aFq 'world.get.block(batch-v6)' "$TMP/radar-native-template" || die SERVER_EXPLORER_V6_NATIVE_MISSING
say 'FEDERATED_V63_RELEASE=OK'

say '2/4 Sauvegarde atomique des binaires actuels'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_CONNECTOR="$BACKUP_DIR/radar-connector-before-federated-v63-$STAMP"
BACKUP_NATIVE="$BACKUP_DIR/radar-native-template-before-federated-v63-$STAMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o root -g root -m 0700 '$BACKUP_DIR'
test -x '$RADAR_CONNECTOR'
test -x '$RADAR_NATIVE'
cp -a '$RADAR_CONNECTOR' '$BACKUP_CONNECTOR'
cp -a '$RADAR_NATIVE' '$BACKUP_NATIVE'
chmod 0700 '$BACKUP_CONNECTOR' '$BACKUP_NATIVE'
echo FEDERATED_V63_BACKUP_CONNECTOR='$BACKUP_CONNECTOR'
echo FEDERATED_V63_BACKUP_NATIVE='$BACKUP_NATIVE'
" </dev/null

say '3/4 Transfert SSH direct puis installation avec rollback automatique'
RCON="/tmp/wfgg-federated-v63-connector-$$"
RNAT="/tmp/wfgg-federated-v63-native-$$"
cat "$TMP/radar-connector" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" "cat > '$RCON'"
cat "$TMP/radar-native-template" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" "cat > '$RNAT'"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
rollback(){
  echo FEDERATED_V63_ROLLBACK=START
  install -o root -g root -m 0755 '$BACKUP_CONNECTOR' '$RADAR_CONNECTOR'
  install -o root -g root -m 0755 '$BACKUP_NATIVE' '$RADAR_NATIVE'
  systemctl restart wfgg-radar-connector.service || true
  echo FEDERATED_V63_ROLLBACK=DONE
}
trap rollback HUP INT TERM ERR
install -o root -g root -m 0755 '$RCON' '$RADAR_CONNECTOR'
install -o root -g root -m 0755 '$RNAT' '$RADAR_NATIVE'
rm -f '$RCON' '$RNAT'
systemctl restart wfgg-radar-connector.service
sleep 2
systemctl is-active --quiet wfgg-radar-connector.service
grep -aFq 'FEDERATED_COLLECTOR_V63_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'WFGG_FEDERATED_MAP_ONLY' '$RADAR_NATIVE'
trap - HUP INT TERM ERR
echo FEDERATED_V63_SERVICE=\$(systemctl is-active wfgg-radar-connector.service)
" </dev/null

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
grep -aFq 'FEDERATED_COLLECTOR_V63_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V63_CANARY' '$RADAR_CONNECTOR'
grep -aFq '@federated:' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_DISCOVERY_V62_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_EXPLORER_V6_SINGLE_SESSION' '$RADAR_CONNECTOR'
grep -aFq 'WFGG_FEDERATED_MAP_ONLY' '$RADAR_NATIVE'
grep -aFq 'WFGG_FEDERATED_ORIGIN_INDEX' '$RADAR_NATIVE'
grep -aFq 'world.get.block(batch-v6)' '$RADAR_NATIVE'
echo FEDERATED_V63_CANARY=READY
echo FEDERATED_V63_QUERY=@federated:991
echo SERVER_EXPLORER_V62=PRESERVED
echo SERVER_EXPLORER_V6=PRESERVED
echo BROAD_SCAN_V4=PRESERVED
" </dev/null

say 'FEDERATED_V63=OK'
