#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RELEASE_COMMIT="17d43566ab797207b4eda3ff70a399cffc546a6f"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/$RELEASE_COMMIT/radar-vps/autocartographer-v636-cluster-release"
RADAR_CONNECTOR="/opt/wfgg-radar/bin/radar-connector"
BACKUP_DIR="/opt/wfgg-radar/backups"
STATE="/opt/wfgg-radar/state/auto-cartographer-v635-passive-change.json"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh sha256sum grep cat; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'AUTO_CARTOGRAPHER_V636_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'AUTO_CARTOGRAPHER_V636_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Auto-Cartographer V6.3.6 CLUSTER GUARD ==='
say '1/4 Téléchargement et vérification de la release'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
(cd "$TMP" && sha256sum -c SHA256SUMS >/dev/null)
chmod 0755 "$TMP/radar-connector"
grep -aFq 'AUTO_CARTOGRAPHER_V636_CLUSTER' "$TMP/radar-connector" || die V636_MARKER_MISSING
grep -aFq 'IGNORED_INCOMPLETE' "$TMP/radar-connector" || die V636_GUARD_MISSING
grep -aFq 'PASSIVE_CLUSTER_CHANGE_DETECTOR' "$TMP/radar-connector" || die V636_MODE_MISSING
if grep -aFq 'POST /v1/cartographer/tick' "$TMP/radar-connector"; then die ACTIVE_TICK_ROUTE_PRESENT; fi
say 'AUTO_CARTOGRAPHER_V636_RELEASE=OK'
say 'AUTO_CARTOGRAPHER_V636_ACTIVE_PROBES=NO'
say 'AUTO_CARTOGRAPHER_V636_BACKGROUND_GAME_CALLS=NO'
say 'AUTO_CARTOGRAPHER_V636_PARTITIONS_ARE_ZONES=NO'

say '2/4 Sauvegarde du connecteur et nettoyage ciblé de la fausse baseline vide'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_CONNECTOR="$BACKUP_DIR/radar-connector-before-autocart-v636-$STAMP"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o root -g root -m 0700 '$BACKUP_DIR'
test -x '$RADAR_CONNECTOR'
cp -a '$RADAR_CONNECTOR' '$BACKUP_CONNECTOR'
chmod 0700 '$BACKUP_CONNECTOR'
echo AUTO_CARTOGRAPHER_V636_BACKUP_CONNECTOR='$BACKUP_CONNECTOR'
if test -s '$STATE' && grep -Fq '\"currentFingerprint\": \"r0:|r1:|r2:|r3:|r4:|r5:|r6:|r7:|r8:\"' '$STATE'; then
  cp -a '$STATE' '$BACKUP_DIR/autocart-v635-invalid-empty-$STAMP.json'
  rm -f '$STATE'
  echo AUTO_CARTOGRAPHER_V636_INVALID_EMPTY_BASELINE=REMOVED
else
  echo AUTO_CARTOGRAPHER_V636_INVALID_EMPTY_BASELINE=NOT_PRESENT
fi
" </dev/null

say '3/4 Transfert SSH et installation avec rollback automatique'
RCON="/tmp/wfgg-autocart-v636-connector-$$"
cat "$TMP/radar-connector" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" "cat > '$RCON'"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
rollback(){
  echo AUTO_CARTOGRAPHER_V636_ROLLBACK=START
  install -o root -g root -m 0755 '$BACKUP_CONNECTOR' '$RADAR_CONNECTOR'
  systemctl restart wfgg-radar-connector.service || true
  echo AUTO_CARTOGRAPHER_V636_ROLLBACK=DONE
}
trap rollback HUP INT TERM ERR
install -o root -g root -m 0755 '$RCON' '$RADAR_CONNECTOR'
rm -f '$RCON'
systemctl restart wfgg-radar-connector.service
sleep 2
systemctl is-active --quiet wfgg-radar-connector.service
grep -aFq 'AUTO_CARTOGRAPHER_V636_CLUSTER' '$RADAR_CONNECTOR'
grep -aFq 'IGNORED_INCOMPLETE' '$RADAR_CONNECTOR'
! grep -aFq 'POST /v1/cartographer/tick' '$RADAR_CONNECTOR'
trap - HUP INT TERM ERR
echo AUTO_CARTOGRAPHER_V636_SERVICE=\$(systemctl is-active wfgg-radar-connector.service)
" </dev/null

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
grep -aFq 'AUTO_CARTOGRAPHER_V636_CLUSTER' '$RADAR_CONNECTOR'
grep -aFq 'PASSIVE_CLUSTER_CHANGE_DETECTOR' '$RADAR_CONNECTOR'
grep -aFq 'EXISTING_COLLECTOR_SCAN_CLUSTER_SIGNATURE' '$RADAR_CONNECTOR'
! grep -aFq 'POST /v1/cartographer/tick' '$RADAR_CONNECTOR'
grep -aFq 'FEDERATED_COLLECTOR_V631_TOPOLOGY' '$RADAR_CONNECTOR'
grep -aFq 'SERVER_DISCOVERY_V62_SENTINEL' '$RADAR_CONNECTOR'
echo AUTO_CARTOGRAPHER_V636_MODE=PASSIVE_CLUSTER_CHANGE_DETECTOR
echo AUTO_CARTOGRAPHER_V636_SOURCE=EXISTING_COLLECTOR_SCAN_CLUSTER_SIGNATURE
echo AUTO_CARTOGRAPHER_V636_EMPTY_SCAN_BASELINE=REJECTED
echo AUTO_CARTOGRAPHER_V636_ACTIVE_PROBES=NO
echo AUTO_CARTOGRAPHER_V636_BACKGROUND_GAME_CALLS=NO
echo SERVER_EXPLORER_V62=PRESERVED
echo FEDERATED_V632=PRESERVED
" </dev/null

say 'AUTO_CARTOGRAPHER_V636_CLUSTER_GUARD=OK'
