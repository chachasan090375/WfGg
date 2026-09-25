#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/opt/wfgg-radar
APP="$ROOT/collector-knowledge"
DATA="$ROOT/data/collector-knowledge"
SOURCES="$ROOT/knowledge/sources"
REPO_RAW="${WFGG_COLLECTOR_KNOWLEDGE_RAW_BASE:-}"
REV="${WFGG_COLLECTOR_KNOWLEDGE_REV:-}"
PORT="${WFGG_COLLECTOR_KNOWLEDGE_PORT:-8793}"
API="http://127.0.0.1:$PORT"

fail(){ echo "COLLECTOR_KNOWLEDGE_INSTALL=FAIL reason=$1"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail ROOT_REQUIRED
command -v python3 >/dev/null 2>&1 || fail PYTHON3_REQUIRED
command -v systemctl >/dev/null 2>&1 || fail SYSTEMD_REQUIRED
command -v curl >/dev/null 2>&1 || fail CURL_REQUIRED
command -v ss >/dev/null 2>&1 || fail SS_REQUIRED
printf '%s' "$PORT" | grep -Eq '^[0-9]{2,5}$' || fail PORT_INVALID
[ "$PORT" != "8791" ] || fail CENTRAL_LEARNING_INGRESS_PORT_RESERVED

# Stop only Collector Knowledge services before replacing their files.
systemctl stop wfgg-collector-knowledge-api.service 2>/dev/null || true
systemctl stop wfgg-collector-knowledge-worker.service 2>/dev/null || true
if ss -ltn "( sport = :$PORT )" | grep -q LISTEN; then
  fail "PORT_ALREADY_IN_USE:$PORT"
fi

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

python3 - "$APP/config.json" "$PORT" <<'PY'
import json,sys
p,port=sys.argv[1],int(sys.argv[2])
x=json.load(open(p,encoding='utf-8'))
x['listenHost']='127.0.0.1'
x['listenPort']=port
open(p,'w',encoding='utf-8').write(json.dumps(x,indent=2)+'\n')
PY

chmod 0755 "$APP/knowledge_engine.py" "$APP/source_refresh.py"
python3 -m py_compile "$APP/knowledge_engine.py" "$APP/source_refresh.py"
python3 "$APP/knowledge_engine.py" --db "$DATA/knowledge.db" stats >/dev/null

systemctl daemon-reload
systemctl enable wfgg-collector-knowledge-worker.service wfgg-collector-knowledge-api.service >/dev/null
systemctl restart wfgg-collector-knowledge-worker.service
systemctl restart wfgg-collector-knowledge-api.service

READY=0
for _ in $(seq 1 30); do
  if curl -fsS "$API/knowledge/health" >/tmp/collector-knowledge-install-health.json 2>/dev/null; then
    READY=1
    break
  fi
  sleep 1
done
[ "$READY" -eq 1 ] || fail API_HEALTH_TIMEOUT
systemctl is-active --quiet wfgg-collector-knowledge-worker.service || fail WORKER_NOT_ACTIVE
systemctl is-active --quiet wfgg-collector-knowledge-api.service || fail API_NOT_ACTIVE

python3 - "$PORT" <<'PY'
import json,sys,urllib.request
port=int(sys.argv[1])
with urllib.request.urlopen(f'http://127.0.0.1:{port}/knowledge/health',timeout=5) as r:
    data=json.load(r)
assert data['ok'] is True
assert data['readonly'] is True
with urllib.request.urlopen('http://127.0.0.1:8791/healthz',timeout=5) as r:
    central=json.load(r)
assert central.get('status')=='ok'
assert central.get('service')=='chacha-central-learning-ingress'
print('COLLECTOR_KNOWLEDGE_API=PASS')
print('COLLECTOR_KNOWLEDGE_PORT_ISOLATION=PASS')
print('CHACHA_CENTRAL_LEARNING_INGRESS_UNCHANGED=PASS')
PY

echo "COLLECTOR_KNOWLEDGE_PORT=$PORT"
echo "COLLECTOR_KNOWLEDGE_WORKER=ACTIVE"
echo "COLLECTOR_KNOWLEDGE_DATABASE=$DATA/knowledge.db"
echo "COLLECTOR_KNOWLEDGE_LASTWAR_MODE=READ_ONLY"
echo "COLLECTOR_KNOWLEDGE_INSTALL=PASS"
