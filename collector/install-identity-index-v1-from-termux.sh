#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
PAYLOAD_COMMIT="d10e1e21f189af13a26a08c6e1fe70fe5e1f1296"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/$PAYLOAD_COMMIT/collector"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh scp python3; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
curl -fsSL "$RAW/collector_agent.py" -o "$TMP/collector_agent.py"
curl -fsSL "$RAW/identity_index_v1.sql" -o "$TMP/identity_index_v1.sql"
python3 -m py_compile "$TMP/collector_agent.py"
grep -q 'identity_resolve' "$TMP/collector_agent.py" || die IDENTITY_RESOLVER_MISSING
grep -q 'CREATE TABLE IF NOT EXISTS player_identity' "$TMP/identity_index_v1.sql" || die IDENTITY_SCHEMA_MISSING
say 'IDENTITY_INDEX_PAYLOAD_RELEASE=OK'

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'IDENTITY_INDEX_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'IDENTITY_INDEX_SSH_ROUTE=PUBLIC_IPV4'
fi

TAG="$$"
RAGENT="/tmp/wfgg-collector-identity-agent-$TAG.py"
RSCHEMA="/tmp/wfgg-collector-identity-schema-$TAG.sql"
scp "${SSH_OPTS[@]}" -q "$TMP/collector_agent.py" "$REMOTE:$RAGENT"
scp "${SSH_OPTS[@]}" -q "$TMP/identity_index_v1.sql" "$REMOTE:$RSCHEMA"

say '=== WfGg Collector · Identity Index V1 ==='
say '1/4 Sauvegarde atomique de la base et du Collector courant'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'bash -s' <<'REMOTE'
set -eu
ROOT=/opt/wfgg-collector
DB="$ROOT/data/collector.db"
BACKUPS="$ROOT/backups"
AGENT="$ROOT/bin/collector_agent.py"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DB_BACKUP="$BACKUPS/collector-before-identity-$STAMP.db"
AGENT_BACKUP="$BACKUPS/collector_agent-before-identity-$STAMP.py"
install -d -o root -g root -m 0700 "$BACKUPS"
test -f "$DB"
python3 - "$DB" "$DB_BACKUP" <<'PY'
import sqlite3,sys
src=sqlite3.connect(sys.argv[1],timeout=30)
dst=sqlite3.connect(sys.argv[2])
try:
    src.backup(dst)
finally:
    dst.close(); src.close()
print('IDENTITY_INDEX_DB_BACKUP='+sys.argv[2])
PY
if test -f "$AGENT"; then
  cp -a "$AGENT" "$AGENT_BACKUP"
  echo "IDENTITY_INDEX_AGENT_BACKUP=$AGENT_BACKUP"
fi
REMOTE

say '2/4 Installation du schéma et du résolveur d’identité'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -o root -g root -m 0755 '$RAGENT' /opt/wfgg-collector/bin/collector_agent.py
install -o root -g root -m 0644 '$RSCHEMA' /opt/wfgg-collector/bin/identity_index_v1.sql
rm -f '$RAGENT' '$RSCHEMA'
python3 -m py_compile /opt/wfgg-collector/bin/collector_agent.py
grep -q 'identity_resolve' /opt/wfgg-collector/bin/collector_agent.py
grep -q 'CREATE TABLE IF NOT EXISTS player_identity' /opt/wfgg-collector/bin/identity_index_v1.sql
systemctl restart wfgg-collector.service
sleep 3
systemctl is-active --quiet wfgg-collector.service
" </dev/null

say '3/4 Rétro-indexation de tous les joueurs déjà connus'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'python3 -' <<'PY'
import json,urllib.request
base='http://127.0.0.1:8790'
with urllib.request.urlopen(base+'/identity/stats',timeout=20) as r:
    s=json.load(r)
assert s.get('ok') is True and s.get('ready') is True, s
print('IDENTITY_INDEX_READY=YES')
print('IDENTITY_INDEX_IDENTITIES='+str(s.get('identities',0)))
print('IDENTITY_INDEX_ALIASES='+str(s.get('aliases',0)))
print('IDENTITY_INDEX_PSEUDO_COLLISIONS='+str(s.get('pseudoCollisions',0)))
with urllib.request.urlopen(base+'/stats',timeout=20) as r:
    c=json.load(r)
players=int(c.get('players',0)); identities=int(s.get('identities',0))
print('IDENTITY_INDEX_COLLECTOR_PLAYERS='+str(players))
print('IDENTITY_INDEX_BACKFILL_DELTA='+str(players-identities))
assert identities == players, (players,identities)
PY

say '4/4 Contrôle final'
ssh "${SSH_OPTS[@]}" -T "$REMOTE" 'python3 -' <<'PY'
import json,urllib.request
base='http://127.0.0.1:8790'
with urllib.request.urlopen(base+'/health',timeout=20) as r:
    h=json.load(r)
assert h.get('ok') is True
idx=h.get('identityIndex') or {}
assert idx.get('ready') is True
print('IDENTITY_INDEX_COLLECTOR_HEALTH=OK')
print('IDENTITY_INDEX_SERVICE=active')
print('IDENTITY_INDEX_RESOLVER=/identity/resolve')
print('IDENTITY_INDEX_ALIASES_API=/identity/aliases')
print('IDENTITY_INDEX_STATS_API=/identity/stats')
PY

say 'COLLECTOR_IDENTITY_INDEX_V1=OK'
say 'RADAR_PRODUCTION_CHANGED=NO'
say 'BROAD_SCAN_V4_CHANGED=NO'
