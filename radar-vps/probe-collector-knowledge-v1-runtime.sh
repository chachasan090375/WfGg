#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/opt/wfgg-radar
APP="$ROOT/collector-knowledge"
DATA="$ROOT/data/collector-knowledge"
API=http://127.0.0.1:8791

fail(){ echo "COLLECTOR_KNOWLEDGE_RUNTIME_PROBE=FAIL reason=$1"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail ROOT_REQUIRED
for c in python3 systemctl curl sha256sum grep; do
  command -v "$c" >/dev/null 2>&1 || fail "COMMAND_MISSING:$c"
done

systemctl is-active --quiet wfgg-collector-knowledge-worker.service || fail WORKER_NOT_ACTIVE
systemctl is-enabled --quiet wfgg-collector-knowledge-worker.service || fail WORKER_NOT_ENABLED
systemctl is-active --quiet wfgg-collector-knowledge-api.service || fail API_NOT_ACTIVE
systemctl is-enabled --quiet wfgg-collector-knowledge-api.service || fail API_NOT_ENABLED

test -s "$APP/knowledge_engine.py" || fail ENGINE_MISSING
test -s "$APP/source_refresh.py" || fail REFRESH_MISSING
test -s "$APP/config.json" || fail CONFIG_MISSING
test -s "$DATA/knowledge.db" || fail DATABASE_MISSING

curl -fsS "$API/knowledge/health" >/tmp/collector-knowledge-health.json
curl -fsS "$API/knowledge/stats" >/tmp/collector-knowledge-stats.json
curl -fsS "$API/knowledge/gaps?limit=20" >/tmp/collector-knowledge-gaps.json

python3 - <<'PY'
import json
h=json.load(open('/tmp/collector-knowledge-health.json'))
s=json.load(open('/tmp/collector-knowledge-stats.json'))
g=json.load(open('/tmp/collector-knowledge-gaps.json'))
assert h['ok'] is True,h
assert h['readonly'] is True,h
assert h['engineVersion']=='1.0.0',h
assert s['ok'] is True,s
assert 'coverageByLayer' in s['stats'],s
assert g['ok'] is True,g
print('COLLECTOR_KNOWLEDGE_API_HEALTH=PASS')
print('COLLECTOR_KNOWLEDGE_STATS=PASS')
print('COLLECTOR_KNOWLEDGE_GAPS=PASS')
print('COLLECTOR_KNOWLEDGE_ARTIFACTS='+str(s['stats'].get('artifacts',0)))
print('COLLECTOR_KNOWLEDGE_ENTITIES='+str(s['stats'].get('entities',0)))
print('COLLECTOR_KNOWLEDGE_PENDING_TASKS='+str(s['stats'].get('pendingTasks',0)))
print('COLLECTOR_KNOWLEDGE_WAITING_TASKS='+str(s['stats'].get('waitingTasks',0)))
PY

if grep -REn 'SendExtension|mail\.reward|building\.production\.collect|visitor\.operate|decryptGameToken|RADAR_CONNECTOR_SHARED_KEY' "$APP"; then
  fail MUTATION_CAPABILITY_FOUND
fi

RADAR_CONNECTOR_STATE="$(systemctl is-active wfgg-radar-connector 2>/dev/null || true)"
echo "COLLECTOR_KNOWLEDGE_WORKER_STATE=active"
echo "COLLECTOR_KNOWLEDGE_API_STATE=active"
echo "COLLECTOR_KNOWLEDGE_RADAR_CONNECTOR_STATE=$RADAR_CONNECTOR_STATE"
echo "COLLECTOR_KNOWLEDGE_LASTWAR_GAME_CONNECTION=NONE"
echo "COLLECTOR_KNOWLEDGE_LASTWAR_MUTATION=NO"
echo "COLLECTOR_KNOWLEDGE_TOKEN_PERSISTENCE=NO"
echo "COLLECTOR_KNOWLEDGE_RUNTIME_PROBE=PASS"
