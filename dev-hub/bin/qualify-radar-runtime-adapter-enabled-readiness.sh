#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_ENABLE_REV:-}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}"
ADAPTER="/opt/chacha-dev/adapters/radar-runtime/current/radar-runtime-adapter"
OUT_ROOT="/opt/chacha-dev/runtime/adapter-promotions/radar-runtime-adapter"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_ROOT/$STAMP"
WORK="$(mktemp -d /tmp/chacha-radar-enable-readiness.XXXXXX)"
REPO="$WORK/repo"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

die(){ echo "RADAR_ENABLE_READINESS=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
[ -x "$ADAPTER" ] || die adapter_executable_missing

for cmd in curl python3 sha256sum systemctl grep mkdir sleep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

mkdir -p "$REPO/dev-hub/bin" "$REPO/dev-hub/config" "$OUT"

for path in   dev-hub/bin/adapter-enable-readiness.py   dev-hub/bin/adapter-enablement-evidence.py   dev-hub/bin/adapter-promotion.py   dev-hub/config/provider-adapters.v1.json   dev-hub/config/adapter-enablement.v1.json   dev-hub/config/adapter-rollbacks.v1.json   dev-hub/config/adapter-contract.v1.json   dev-hub/config/adapter-promotion.v1.json
do
  mkdir -p "$REPO/$(dirname "$path")"
  curl -fsSL "$RAW/$path" -o "$REPO/$path"
done

python3 -m py_compile   "$REPO/dev-hub/bin/adapter-enable-readiness.py"   "$REPO/dev-hub/bin/adapter-enablement-evidence.py"   "$REPO/dev-hub/bin/adapter-promotion.py"

python3 - "$REPO/dev-hub/config/provider-adapters.v1.json" "$ADAPTER" <<'PY'
import hashlib,json,os,sys
registry_path,adapter_path=sys.argv[1:3]
r=json.load(open(registry_path,encoding='utf-8'))
a=r['adapters']['radar-runtime-adapter']
assert a['status']=='PILOT',a
assert a['executable']==adapter_path,a
h=hashlib.sha256(open(adapter_path,'rb').read()).hexdigest()
assert h=='a2bbfa66d16d75858940b621690e9001de8cbb69e4debd0dad284034eb52b332',h
print('RADAR_ENABLE_PRESTATE=PILOT')
print('RADAR_ENABLE_EXECUTABLE_DIGEST=sha256:'+h)
PY

RADAR_SENTINEL_STATE="$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
RADAR_SENTINEL_ENABLED="$(systemctl is-enabled wfgg-radar-sentinel.timer 2>/dev/null || true)"
COLLECTOR_SENTINEL_STATE="$(systemctl is-active wfgg-collector-sentinel.timer 2>/dev/null || true)"
RADAR_SERVICE_STATE="$(systemctl is-active wfgg-radar-connector 2>/dev/null || true)"

echo "=== CHACHA DEV RADAR ENABLEMENT READINESS ==="
echo "RADAR_SERVICE=$RADAR_SERVICE_STATE"
echo "RADAR_SENTINEL_TIMER=$RADAR_SENTINEL_STATE"
echo "RADAR_SENTINEL_ENABLED=$RADAR_SENTINEL_ENABLED"
echo "COLLECTOR_SENTINEL_TIMER=$COLLECTOR_SENTINEL_STATE"

[ "$RADAR_SERVICE_STATE" = "active" ] || die radar_service_not_active
[ "$RADAR_SENTINEL_STATE" = "active" ] || die radar_sentinel_not_active
[ "$RADAR_SENTINEL_ENABLED" = "enabled" ] || die radar_sentinel_not_enabled
[ "$COLLECTOR_SENTINEL_STATE" = "active" ] || die collector_sentinel_not_active

for i in 1 2 3; do
  cat > "$OUT/envelope-$i.json" <<JSON
{
  "schema": "chacha.dev/dispatch-envelope/v1",
  "project": "wfgg-radar",
  "transition": "OPERATE->OPERATE",
  "run_id": "radar-enable-readiness-$STAMP-$i",
  "wave": 1,
  "task": {
    "id": "radar-runtime:status",
    "kind": "runtime-status",
    "description": "PILOT repeatability probe for WfGg Radar runtime adapter.",
    "owner_role": "sre-observability",
    "permission": "read",
    "outputs": [{"type":"artifact","id":"radar-runtime-status"}],
    "verification": {
      "mode": "machine",
      "self_certification_allowed": false,
      "required_evidence": ["source","timestamp","digest"]
    }
  },
  "bindings": [{
    "capability": "radar-runtime-inspect",
    "provider": "radar-vps-runtime",
    "adapter": "radar-runtime-adapter",
    "fallback_used": false,
    "health_state": "HEALTHY"
  }],
  "policy_context": {
    "resource_class": "light",
    "requires_storage_preflight": false,
    "human_approval_required": false,
    "approval_id": null,
    "timeout_seconds": 30
  },
  "workspace": null,
  "metadata": {"radar_runtime":{"action":"status"}}
}
JSON
  "$ADAPTER" < "$OUT/envelope-$i.json" > "$OUT/task-result-$i.json"
  sleep 1
done

python3 - "$OUT" <<'PY'
import json,sys
from pathlib import Path
from datetime import datetime,timezone
root=Path(sys.argv[1])
results=[json.load(open(root/f'task-result-{i}.json',encoding='utf-8')) for i in (1,2,3)]
for x in results:
    assert x['schema']=='chacha.dev/task-result/v1',x
    assert x['project']=='wfgg-radar',x
    assert x['task_id']=='radar-runtime:status',x
    assert x['producer']=='radar-runtime-adapter',x
    assert x['status']=='OK',x
    assert x['verification']['status']=='UNVERIFIED',x
    details=(x.get('evidence') or [{}])[0].get('details') or {}
    assert details.get('radar_service')=='active',details
    assert details.get('radar_sentinel_timer')=='active',details
    assert details.get('radar_sentinel_enabled')=='enabled',details
    assert details.get('collector_sentinel_timer')=='active',details
assert len({x['observed_at'] for x in results})==3
assert len({(x['project'],x['task_id']) for x in results})==1
latest=results[-1]
details=(latest.get('evidence') or [{}])[0].get('details') or {}
health={
  'schema':'chacha.dev/provider-health-snapshot/v1',
  'observed_at':datetime.now(timezone.utc).isoformat(),
  'providers':{
    'radar-vps-runtime':{
      'state':'HEALTHY',
      'source':'radar-runtime-adapter:repeatability-readiness',
      'checked_at':datetime.now(timezone.utc).isoformat(),
      'details':{
        'radar_service':details.get('radar_service'),
        'radar_sentinel_timer':details.get('radar_sentinel_timer'),
        'radar_sentinel_enabled':details.get('radar_sentinel_enabled'),
        'collector_sentinel_timer':details.get('collector_sentinel_timer'),
        'connector_sha256':details.get('connector_sha256'),
        'native_sha256':details.get('native_sha256')
      }
    }
  }
}
open(root/'provider-health.json','w',encoding='utf-8').write(json.dumps(health,indent=2)+'\n')
print('RADAR_REPEATABILITY_PROBES=PASS')
print('RADAR_PROVIDER_HEALTH_SNAPSHOT=HEALTHY')
PY

cd "$REPO"
set +e
python3 dev-hub/bin/adapter-enable-readiness.py   --registry dev-hub/config/provider-adapters.v1.json   --adapter radar-runtime-adapter   --provider radar-vps-runtime   --result "$OUT/task-result-1.json"   --result "$OUT/task-result-2.json"   --result "$OUT/task-result-3.json"   --health "$OUT/provider-health.json"   --rollbacks dev-hub/config/adapter-rollbacks.v1.json   --work-dir "$OUT/readiness"   --json > "$OUT/readiness-stdout.json"
RC=$?
set -e

python3 - "$OUT" "$RC" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); rc=int(sys.argv[2])
receipt=json.load(open(root/'readiness'/'enablement-readiness.json',encoding='utf-8'))
evidence=json.load(open(root/'readiness'/'enablement-evidence.json',encoding='utf-8'))
plan=json.load(open(root/'readiness'/'enablement-promotion-plan.json',encoding='utf-8'))
results=[json.load(open(root/f'task-result-{i}.json',encoding='utf-8')) for i in (1,2,3)]

for gate in ('repeatable-pass','provider-health-pass','rollback-defined'):
    assert evidence['evidence'][gate]['status']=='PASS',(gate,evidence)

assert len(receipt['repeatability_results'])==3,receipt
assert all(x['valid'] for x in receipt['repeatability_results']),receipt
assert len({x['observed_at'] for x in receipt['repeatability_results']})==3,receipt
assert len({(x['project'],x['task_id']) for x in receipt['repeatability_results']})==1,receipt

assert plan['current_status']=='PILOT',plan
assert plan['target_status']=='ENABLED',plan
assert plan['production_capable'] is True,plan
assert plan['approval_required'] is True,plan
assert plan['eligible'] is False,plan
assert plan['blockers']==['EXPLICIT_PRODUCTION_APPROVAL_ID_REQUIRED'],plan
assert rc==2,rc
assert receipt['registry_mutated'] is False,receipt
assert receipt['blockers']==['PROMOTION:EXPLICIT_PRODUCTION_APPROVAL_ID_REQUIRED'],receipt

print('RADAR_ENABLE_TECHNICAL_GATES=PASS')
print('REPEATABLE_PASS=PASS')
print('PROVIDER_HEALTH_PASS=PASS')
print('ROLLBACK_DEFINED=PASS')
print('CURRENT_STATUS=PILOT')
print('TARGET_STATUS=ENABLED')
print('PRODUCTION_CAPABLE=YES')
print('APPROVAL_REQUIRED=YES')
print('PROMOTION_ELIGIBLE_WITHOUT_APPROVAL=NO')
print('ONLY_BLOCKER=EXPLICIT_PRODUCTION_APPROVAL_ID_REQUIRED')
print('REGISTRY_MUTATION=NO')
print('RADAR_PRODUCTION_MUTATION=NO')
print('READINESS_RECEIPT='+str(root/'readiness'/'enablement-readiness.json'))
print('ENABLEMENT_EVIDENCE='+str(root/'readiness'/'enablement-evidence.json'))
print('PROMOTION_PLAN='+str(root/'readiness'/'enablement-promotion-plan.json'))
PY

echo "RADAR_ENABLE_READINESS=WAITING_FOR_HUMAN_APPROVAL"
