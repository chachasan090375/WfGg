#!/usr/bin/env bash
set -Eeuo pipefail

AGENT="/opt/wfgg-collector/bin/collector_agent.py"
DB="/opt/wfgg-collector/data/collector.db"
SERVICE="wfgg-collector"
REV="${WFGG_RADAR_V6191_REV:-radar-v6191-rich-profile-e2e}"
PATCH_URL="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}/radar-vps/collector-rich-profile-v6191.py"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/opt/wfgg-collector/data/v6191-backups/$STAMP"
TMP="$(mktemp -d /tmp/wfgg-collector-v6191.XXXXXX)"
PROMOTED=0

fail(){ echo "COLLECTOR_V6191_INSTALL=FAIL reason=$*"; exit 1; }
cleanup(){ rm -rf "$TMP"; }
rollback(){
  rc=$?
  if [[ "$rc" -ne 0 && "$PROMOTED" -eq 1 ]]; then
    echo "COLLECTOR_V6191_ROLLBACK=START"
    cp -a "$BACKUP/collector_agent.py" "$AGENT"
    systemctl restart "$SERVICE" || true
    sleep 2
    systemctl is-active --quiet "$SERVICE" && echo "COLLECTOR_V6191_ROLLBACK=PASS" || echo "COLLECTOR_V6191_ROLLBACK=FAIL"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
test -f "$AGENT" || fail AGENT_MISSING
test -f "$DB" || fail DB_MISSING
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE

mkdir -p "$BACKUP"
cp -a "$AGENT" "$BACKUP/collector_agent.py"
PID_BEFORE="$(systemctl show -p MainPID --value "$SERVICE")"
TABLES_BEFORE="$(python3 - "$DB" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
print(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0])
PY
)"

curl -fsSL "$PATCH_URL" -o "$TMP/patch.py"
python3 -m py_compile "$TMP/patch.py"
python3 "$TMP/patch.py" --agent "$AGENT" --db "$DB"
python3 -m py_compile "$AGENT"
grep -Fq 'WFGG_COLLECTOR_RICH_PROFILE_V6191' "$AGENT"

TABLES_AFTER="$(python3 - "$DB" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
print(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0])
PY
)"
[[ "$TABLES_BEFORE" = "$TABLES_AFTER" ]] || fail TABLE_COUNT_CHANGED
echo "COLLECTOR_V6191_TABLE_COUNT=$TABLES_AFTER"

PROMOTED=1
systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || fail SERVICE_RESTART
PID_AFTER="$(systemctl show -p MainPID --value "$SERVICE")"

python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8790/health',timeout=10) as r:
    d=json.load(r)
assert d.get('ok') is True
print('COLLECTOR_V6191_HEALTH=PASS')
PY

echo "COLLECTOR_PID_BEFORE=$PID_BEFORE"
echo "COLLECTOR_PID_AFTER=$PID_AFTER"
echo "COLLECTOR_V6191_BACKUP=$BACKUP"
echo "COLLECTOR_V6191_STORAGE_TABLES_UNCHANGED=PASS"
echo "COLLECTOR_V6191_INSTALL=PASS"

PROMOTED=0
trap - EXIT
cleanup
