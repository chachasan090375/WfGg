#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RELEASE_COMMIT="be11ee4af4d66b0305932a69d7230a5f51ec61ab"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/$RELEASE_COMMIT/radar-vps/oracle-release"
RADAR_BIN="/opt/wfgg-radar/bin/radar-connector"
BACKUP_DIR="/opt/wfgg-radar/backups"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh scp sha256sum grep; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'PLAYER_ORACLE_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'PLAYER_ORACLE_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Player Oracle v1 + Sentinel ==='
say '1/4 Téléchargement et vérification de la release isolée'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
grep -E '  radar-connector$' "$TMP/SHA256SUMS" > "$TMP/CONNECTOR_SHA256SUMS"
[[ "$(wc -l < "$TMP/CONNECTOR_SHA256SUMS" | tr -d ' ')" = "1" ]] || die CONNECTOR_CHECKSUM_MISSING
(cd "$TMP" && sha256sum -c CONNECTOR_SHA256SUMS >/dev/null)
chmod 0755 "$TMP/radar-connector"
grep -aFq 'TARGETED_UID_PROFILE' "$TMP/radar-connector" || die PLAYER_ORACLE_RELEASE_NOT_READY
grep -aFq 'BROAD_SCAN_V4' "$TMP/radar-connector" || die BROAD_SCAN_FALLBACK_MISSING
grep -aFq 'PLAYER_ORACLE_SENTINEL' "$TMP/radar-connector" || die PLAYER_ORACLE_SENTINEL_MISSING
say 'PLAYER_ORACLE_RELEASE=OK'
say 'PLAYER_ORACLE_SENTINEL_RELEASE=OK'

say '2/4 Sauvegarde atomique du connecteur actuellement installé'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_DIR/radar-connector-before-player-oracle-sentinel-$STAMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o root -g root -m 0700 '$BACKUP_DIR'
test -x '$RADAR_BIN'
cp -a '$RADAR_BIN' '$BACKUP'
chmod 0700 '$BACKUP'
echo PLAYER_ORACLE_BACKUP='$BACKUP'
" </dev/null

say '3/4 Installation du connecteur Oracle/Sentinel avec rollback automatique'
REMOTE_TMP="/tmp/wfgg-radar-player-oracle-sentinel-$$"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-connector" "$REMOTE:$REMOTE_TMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
rollback(){
  echo PLAYER_ORACLE_ROLLBACK=START
  install -o root -g root -m 0755 '$BACKUP' '$RADAR_BIN'
  systemctl restart wfgg-radar-connector.service || true
  echo PLAYER_ORACLE_ROLLBACK=DONE
}
trap rollback HUP INT TERM ERR
install -o root -g root -m 0755 '$REMOTE_TMP' '$RADAR_BIN'
rm -f '$REMOTE_TMP'
systemctl restart wfgg-radar-connector.service
sleep 2
systemctl is-active --quiet wfgg-radar-connector.service
grep -aFq 'TARGETED_UID_PROFILE' '$RADAR_BIN'
grep -aFq 'BROAD_SCAN_V4' '$RADAR_BIN'
grep -aFq 'PLAYER_ORACLE_SENTINEL' '$RADAR_BIN'
trap - HUP INT TERM ERR
echo PLAYER_ORACLE_CONNECTOR_SERVICE=\$(systemctl is-active wfgg-radar-connector.service)
" </dev/null

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
grep -aFq 'TARGETED_UID_PROFILE' '$RADAR_BIN'
grep -aFq 'BROAD_SCAN_V4' '$RADAR_BIN'
grep -aFq 'PLAYER_ORACLE_SENTINEL' '$RADAR_BIN'
echo PLAYER_ORACLE_TARGETED_UID=READY
echo PLAYER_ORACLE_BROADSCAN_FALLBACK=READY
echo PLAYER_ORACLE_SENTINEL=READY
echo PLAYER_ORACLE_PRIORITY_ORDER=P1_UID_INDEX_P2_DIRECT_PROFILE_P3_BROAD_SCAN_V4
echo PLAYER_ORACLE_BACKUP='$BACKUP'
" </dev/null

say 'PLAYER_ORACLE_V1=OK'
say 'PLAYER_ORACLE_SENTINEL_V1=OK'
