#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/radar-production-v1/radar-vps/release"
COLLECTOR_ENGINE="/opt/wfgg-collector/bin/incremental_engine.py"
RADAR_BIN="/opt/wfgg-radar/bin/radar-connector"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh scp sha256sum grep; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'PLAYER_COMPLETENESS_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'PLAYER_COMPLETENESS_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Radar · Complétude fiche joueur v1 ==='
say '1/4 Vérification de la release connecteur'
TS="$(date +%s)"
curl -fsSL "$RAW/SHA256SUMS?ts=$TS" -o "$TMP/SHA256SUMS"
curl -fsSL "$RAW/radar-connector?ts=$TS" -o "$TMP/radar-connector"
grep -E '  radar-connector$' "$TMP/SHA256SUMS" > "$TMP/CONNECTOR_SHA256SUMS"
[[ "$(wc -l < "$TMP/CONNECTOR_SHA256SUMS" | tr -d ' ')" = "1" ]] || die CONNECTOR_CHECKSUM_MISSING
(cd "$TMP" && sha256sum -c CONNECTOR_SHA256SUMS >/dev/null)
chmod 0755 "$TMP/radar-connector"
grep -aFq 'PROFILE_TARGET_NOT_RETURNED' "$TMP/radar-connector" || die PROFILE_RETRY_RELEASE_NOT_READY
say 'PLAYER_COMPLETENESS_CONNECTOR_RELEASE=OK'

say '2/4 Préservation des coordonnées lors des enrichissements profil'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "TARGET='$COLLECTOR_ENGINE' python3 -" <<'PY'
from pathlib import Path
import os, py_compile, shutil
p=Path(os.environ['TARGET'])
s=p.read_text(encoding='utf-8')
marker='# WFGG_PROFILE_SPARSE_MERGE_V1'
if marker not in s:
    old="""    if effective.get('power') is None and old:\n        effective['power']=old['power']\n"""
    new="""    # WFGG_PROFILE_SPARSE_MERGE_V1\n    # A direct profile reply has no world-map coordinates. Missing X/Y are\n    # therefore sparse fields, not instructions to erase the last map state.\n    if old:\n        if effective.get('x') is None:\n            effective['x']=old['x']\n        if effective.get('y') is None:\n            effective['y']=old['y']\n        if effective.get('power') is None:\n            effective['power']=old['power']\n"""
    if s.count(old) != 1:
        raise SystemExit('PROFILE_MERGE_PATCH_ANCHOR_MISSING')
    backup=p.with_suffix('.py.before-profile-merge-v1')
    if not backup.exists(): shutil.copy2(p, backup)
    p.write_text(s.replace(old,new,1),encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('PLAYER_COMPLETENESS_SPARSE_MERGE=OK')
PY

say '3/4 Installation atomique du connecteur avec retry cible'
TAG="$$"
RCON="/tmp/wfgg-radar-connector-completeness-$TAG"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-connector" "$REMOTE:$RCON"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -o root -g root -m 0755 '$RCON' '$RADAR_BIN'
rm -f '$RCON'
systemctl restart wfgg-collector.service
systemctl restart wfgg-radar-connector.service
sleep 2
systemctl is-active --quiet wfgg-collector.service
systemctl is-active --quiet wfgg-radar-connector.service
grep -q 'WFGG_PROFILE_SPARSE_MERGE_V1' '$COLLECTOR_ENGINE'
grep -aFq 'PROFILE_TARGET_NOT_RETURNED' '$RADAR_BIN'
"

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8790/health',timeout=10) as r:
    d=json.load(r)
assert d.get('ok') is True
print('PLAYER_COMPLETENESS_COLLECTOR_HEALTH=OK')
PY
echo PLAYER_COMPLETENESS_COLLECTOR_SERVICE=\$(systemctl is-active wfgg-collector.service)
echo PLAYER_COMPLETENESS_CONNECTOR_SERVICE=\$(systemctl is-active wfgg-radar-connector.service)
" </dev/null

say 'PLAYER_COMPLETENESS_TARGET_RETRY=3'
say 'PLAYER_COMPLETENESS_FIX=OK'
