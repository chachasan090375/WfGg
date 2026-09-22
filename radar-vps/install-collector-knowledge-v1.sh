#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/opt/wfgg-radar
APP="$ROOT/collector-knowledge"
DATA="$ROOT/data/collector-knowledge"
SOURCES="$ROOT/knowledge/sources"
REPO_RAW="${WFGG_COLLECTOR_KNOWLEDGE_RAW_BASE:-}"
REV="${WFGG_COLLECTOR_KNOWLEDGE_REV:-}"

fail(){ echo "COLLECTOR_KNOWLEDGE_INSTALL=FAIL reason=$1"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail ROOT_REQUIRED
command -v python3 >/dev/null 2>&1 || fail PYTHON3_REQUIRED
command -v systemctl >/dev/null 2>&1 || fail SYSTEMD_REQUIRED

install -d -m 0755 "$APP" "$SOURCES" "$SOURCES/wfgg" "$SOURCES/lastwar" "$SOURCES/assets"
install -d -m 0750 "$DATA"

if [ -n "$REPO_RAW" ]; then
  curl -fsSL "$REPO_RAW/collector-knowledge/knowledge_engine.py" -o "$APP/knowledge_engine.py"
  curl -fsSL "$REPO_RAW/collector-knowledge/source_refresh.py" -o "$APP/source_refresh.py"
  curl -fsSL "$REPO_RAW/collector-knowledge/config.example.json" -o "$APP/config.json"
  curl -fsSL "$REPO_RAW/radar-vps/wfgg-collector-knowledge-worker.service" -o /etc/systemd/system/wfgg-collector-knowledge-worker.service
  curl -fsSL "$REPO_RAW/radar-vps/wfgg-collector-knowledge-api.service" -o /etc/systemd/system/wfgg-collector-knowledge-api.service
else
  [ -n "$REV" ] || fail REV_OR_RAW_BASE_REQUIRED
  BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/$REV"
  curl -fsSL "$BASE/collector-knowledge/knowledge_engine.py" -o "$APP/knowledge_engine.py"
  curl -fsSL "$BASE/collector-knowledge/source_refresh.py" -o "$APP/source_refresh.py"
  curl -fsSL "$BASE/collector-knowledge/config.example.json" -o "$APP/config.json"
  curl -fsSL "$BASE/radar-vps/wfgg-collector-knowledge-worker.service" -o /etc/systemd/system/wfgg-collector-knowledge-worker.service
  curl -fsSL "$BASE/radar-vps/wfgg-collector-knowledge-api.service" -o /etc/systemd/system/wfgg-collector-knowledge-api.service
fi

chmod 0755 "$APP/knowledge_engine.py" "$APP/source_refresh.py"
python3 -m py_compile "$APP/knowledge_engine.py" "$APP/source_refresh.py"
python3 "$APP/knowledge_engine.py" --db "$DATA/knowledge.db" stats >/dev/null

systemctl daemon-reload
systemctl enable --now wfgg-collector-knowledge-worker.service
systemctl enable --now wfgg-collector-knowledge-api.service

sleep 1
systemctl is-active --quiet wfgg-collector-knowledge-worker.service || fail WORKER_NOT_ACTIVE
systemctl is-active --quiet wfgg-collector-knowledge-api.service || fail API_NOT_ACTIVE

python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8791/knowledge/health',timeout=5) as r:
    data=json.load(r)
assert data['ok'] is True
assert data['readonly'] is True
print('COLLECTOR_KNOWLEDGE_API=PASS')
PY

echo "COLLECTOR_KNOWLEDGE_WORKER=ACTIVE"
echo "COLLECTOR_KNOWLEDGE_DATABASE=$DATA/knowledge.db"
echo "COLLECTOR_KNOWLEDGE_LASTWAR_MODE=READ_ONLY"
echo "COLLECTOR_KNOWLEDGE_INSTALL=PASS"
