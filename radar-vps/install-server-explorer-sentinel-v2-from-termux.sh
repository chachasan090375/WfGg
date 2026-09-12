#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RELEASE_COMMIT="4ffb189e12dd24f6f25c93224213130282e24a04"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/$RELEASE_COMMIT/radar-vps/server-explorer-sentinel-v2-release"
RADAR_BIN_DIR="/opt/wfgg-radar/bin"
RADAR_CONNECTOR="$RADAR_BIN_DIR/radar-connector"
RADAR_NATIVE="$RADAR_BIN_DIR/radar-native-template"
BACKUP_DIR="/opt/wfgg-radar/backups"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh scp sha256sum grep; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'SERVER_EXPLORER_V2_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'SERVER_EXPLORER_V2_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Server Explorer Sentinel v2 · control budget 15s ==='
say '1/4 Téléchargement et vérification de la release'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
curl -fsSL "$RAW/radar-native-template?ts=$TS" -o "$TMP/radar-native-template"
(cd "$TMP" && sha256sum -c SHA256SUMS >/dev/null)
chmod 0755 "$TMP/radar-connector" "$TMP/radar-native-template"
grep -aFq 'SERVER_EXPLORER_PROTOCOL_SENTINEL' "$TMP/radar-connector" || die PROTOCOL_SENTINEL_MARKER_MISSING
grep -aFq 'SERVER_EXPLORER_V1' "$TMP/radar-connector" || die SERVER_EXPLORER_MARKER_MISSING
grep -aFq 'SERVER_EXPLORER_NATIVE_SENTINEL' "$TMP/radar-native-template" || die NATIVE_SENTINEL_MARKER_MISSING
grep -aFq 'native-template-readonly-v4' "$TMP/radar-native-template" || die BROAD_SCAN_V4_MARKER_MISSING
grep -aFq 'WFGG_SERVER_ID_OVERRIDE' "$TMP/radar-native-template" || die SERVER_OVERRIDE_MARKER_MISSING
say 'SERVER_EXPLORER_SENTINEL_V2_RELEASE=OK'
say 'SERVER_EXPLORER_CONTROL_BUDGET=15S'

say '2/4 Sauvegarde atomique des binaires actuels'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_CONNECTOR="$BACKUP_DIR/radar-connector-before-server-explorer-sentinel-v2-$STAMP"
BACKUP_NATIVE="$BACKUP_DIR/radar-native-template-before-server-explorer-sentinel-v2-$STAMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o root -g root -m 0700 '$BACKUP_DIR'
test -x '$RADAR_CONNECTOR'
test -x '$RADAR_NATIVE'
cp -a '$RADAR_CONNECTOR' '$BACKUP_CONNECTOR'
cp -a '$RADAR_NATIVE' '$BACKUP_NATIVE'
chmod 0700 '$BACKUP_CONNECTOR' '$BACKUP_NATIVE'
echo SERVER_EXPLORER_SENTINEL_V2_BACKUP_CONNECTOR='$BACKUP_CONNECTOR'
echo SERVER_EXPLORER_SENTINEL_V2_BACKUP_NATIVE='$BACKUP_NATIVE'
" </dev/null

say '3/4 Installation avec rollback automatique'
RCON="/tmp/wfgg-server-explorer-v2-connector-$$"
RNAT="/tmp/wfgg-server-explorer-v2-native-$$"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-connector" "$REMOTE:$RCON"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-native-template" "$REMOTE:$RNAT"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
rollback(){
  echo SERVER_EXPLORER_SENTINEL_V2_ROLLBACK=START
  install -o root -g root -m 0755 '$BACKUP_CONNECTOR' '$RADAR_CONNECTOR'
  install -o root -g root -m 0755 '$BACKUP_NATIVE' '$RADAR_NATIVE'
  systemctl restart wfgg-radar-connector.service || true
  echo SERVER_EXPLORER_SENTINEL_V2_ROLLBACK=DONE
}
trap rollback HUP INT TERM ERR
install -o root -g root -m 0755 '$RCON' '$RADAR_CONNECTOR'
install -o root -g root -m 0755 '$RNAT' '$RADAR_NATIVE'
rm -f '$RCON' '$RNAT'
systemctl restart wfgg-radar-connector.service
sleep 2
systemctl is-active --quiet wfgg-radar-connector.service
grep -aFq 'SERVER_EXPLORER_PROTOCOL_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_EXPLORER_NATIVE_SENTINEL' '$RADAR_NATIVE'
trap - HUP INT TERM ERR
echo SERVER_EXPLORER_SENTINEL_V2_SERVICE=\$(systemctl is-active wfgg-radar-connector.service)
" </dev/null

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
grep -aFq 'SERVER_EXPLORER_PROTOCOL_SENTINEL' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_EXPLORER_NATIVE_SENTINEL' '$RADAR_NATIVE'
grep -aFq 'SERVER_EXPLORER_V1' '$RADAR_CONNECTOR'
grep -aFq 'native-template-readonly-v4' '$RADAR_NATIVE'
grep -aFq 'WFGG_SERVER_ID_OVERRIDE' '$RADAR_NATIVE'
echo SERVER_EXPLORER_PROTOCOL_SENTINEL=READY
echo SERVER_EXPLORER_NATIVE_SENTINEL=READY
echo SERVER_EXPLORER_CONTROL_SERVER=992
echo SERVER_EXPLORER_CONTROL_BUDGET=15S
echo BROAD_SCAN_V4_FALLBACK=PRESERVED
echo RADAR_PRODUCTION_CHANGED=NO
" </dev/null

say 'SERVER_EXPLORER_SENTINEL_V2=OK'
