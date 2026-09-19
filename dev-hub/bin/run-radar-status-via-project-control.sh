#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_OPERATE_REV:-}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}"
ROOT="/opt/chacha-dev"
STATE_ROOT="$ROOT/runtime/state"
EVIDENCE_ROOT="$ROOT/runtime/evidence"
HEALTH_FILE="$ROOT/runtime/health/wfgg-radar/providers.json"
ADAPTER="$ROOT/adapters/radar-runtime/current/radar-runtime-adapter"
EXPECTED_ADAPTER_SHA="a2bbfa66d16d75858940b621690e9001de8cbb69e4debd0dad284034eb52b332"
WORK="$(mktemp -d /tmp/chacha-project-control-radar-status.XXXXXX)"
REPO="$WORK/repo"
RESULT="$WORK/project-control-result.json"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

die(){ echo "CHACHA_DEV_RADAR_STATUS=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required

for cmd in curl python3 sha256sum systemctl grep mkdir; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV PROJECT CONTROL -> RADAR STATUS ==="

[ -x "$ADAPTER" ] || die radar_runtime_adapter_missing
ACTUAL_ADAPTER_SHA="$(sha256sum "$ADAPTER" | awk '{print $1}')"
echo "RADAR_RUNTIME_ADAPTER_SHA256=$ACTUAL_ADAPTER_SHA"
[ "$ACTUAL_ADAPTER_SHA" = "$EXPECTED_ADAPTER_SHA" ] || die radar_runtime_adapter_digest_mismatch

RADAR_SENTINEL="$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
RADAR_SENTINEL_ENABLED="$(systemctl is-enabled wfgg-radar-sentinel.timer 2>/dev/null || true)"
COLLECTOR_SENTINEL="$(systemctl is-active wfgg-collector-sentinel.timer 2>/dev/null || true)"
echo "RADAR_SENTINEL_TIMER=$RADAR_SENTINEL"
echo "RADAR_SENTINEL_ENABLED=$RADAR_SENTINEL_ENABLED"
echo "COLLECTOR_SENTINEL_TIMER=$COLLECTOR_SENTINEL"
[ "$RADAR_SENTINEL" = "active" ] || die radar_sentinel_not_active
[ "$RADAR_SENTINEL_ENABLED" = "enabled" ] || die radar_sentinel_not_enabled
[ "$COLLECTOR_SENTINEL" = "active" ] || die collector_sentinel_not_active

FILES=(
  dev-hub/bin/project-control-cli.py
  dev-hub/bin/project-control.py
  dev-hub/bin/external-runtime-dispatch.py
  dev-hub/bin/run-controller.py
  dev-hub/bin/execution-scheduler.py
  dev-hub/bin/control-plane-store.py
  dev-hub/bin/evidence-collector.py
  dev-hub/config/project-control.v1.json
  dev-hub/config/control-plane-state.v1.json
  dev-hub/config/orchestration-policy.v1.json
  dev-hub/config/capability-registry.v1.json
  dev-hub/config/execution-scheduler.v1.json
  dev-hub/config/run-controller.v1.json
  dev-hub/config/run-controller.operate.v1.json
  dev-hub/config/provider-adapters.v1.json
  dev-hub/operations/wfgg-radar/runtime-status.task-graph.json
)

for path in "${FILES[@]}"; do
  mkdir -p "$REPO/$(dirname "$path")"
  curl -fsSL "$RAW/$path" -o "$REPO/$path" || die "download_failed:$path"
done

python3 -m py_compile   "$REPO/dev-hub/bin/project-control-cli.py"   "$REPO/dev-hub/bin/project-control.py"   "$REPO/dev-hub/bin/external-runtime-dispatch.py"   "$REPO/dev-hub/bin/run-controller.py"   "$REPO/dev-hub/bin/execution-scheduler.py"   "$REPO/dev-hub/bin/control-plane-store.py"   "$REPO/dev-hub/bin/evidence-collector.py"

python3 - "$REPO" "$ADAPTER" <<'PY'
import json,sys
from pathlib import Path
repo=Path(sys.argv[1]); adapter=sys.argv[2]
pc=json.load(open(repo/'dev-hub/config/project-control.v1.json',encoding='utf-8'))
normal=json.load(open(repo/'dev-hub/config/run-controller.v1.json',encoding='utf-8'))
operate=json.load(open(repo/'dev-hub/config/run-controller.operate.v1.json',encoding='utf-8'))
reg=json.load(open(repo/'dev-hub/config/provider-adapters.v1.json',encoding='utf-8'))
graph=json.load(open(repo/'dev-hub/operations/wfgg-radar/runtime-status.task-graph.json',encoding='utf-8'))
a=reg['adapters']['radar-runtime-adapter']
assert normal['mode']=='dispatch-only',normal
assert operate['mode']=='execute-enabled',operate
assert pc['repository_paths']['run_controller_operate']=='dev-hub/config/run-controller.operate.v1.json',pc
assert a['status']=='ENABLED',a
assert a['executable']==adapter,a
assert graph['transition']=='OPERATE->OPERATE',graph
assert graph['tasks'][0]['permission']=='read',graph
assert graph['tasks'][0]['metadata']['radar_runtime']['action']=='status',graph
print('CHACHA_DEV_OPERATE_POLICY=PASS')
print('RADAR_RUNTIME_ADAPTER_REGISTRY=ENABLED')
PY

STATE="$STATE_ROOT/wfgg-radar/state.json"
JOURNAL="$STATE_ROOT/wfgg-radar/audit.jsonl"
LEDGER="$EVIDENCE_ROOT/wfgg-radar/ledger.json"

if [ ! -e "$STATE" ] && [ ! -e "$JOURNAL" ]; then
  cat > "$WORK/initial.json" <<'JSON'
{
  "identity": {
    "slug": "wfgg-radar",
    "control_plane_onboarded": true
  },
  "lifecycle": {
    "stage": "OPERATE"
  },
  "architecture": {
    "manifest": "dev-hub/projects/wfgg-radar/manifest.v3.json"
  },
  "operations": {
    "runtime_provider": "radar-vps-runtime",
    "runtime_adapter": "radar-runtime-adapter"
  }
}
JSON
  python3 "$REPO/dev-hub/bin/control-plane-store.py"     --policy "$REPO/dev-hub/config/control-plane-state.v1.json"     --root "$STATE_ROOT"     init --project wfgg-radar --actor chacha-dev-project-control-bootstrap     --initial "$WORK/initial.json"
  echo "CONTROL_PLANE_STATE_INITIALIZED=YES"
elif [ -f "$STATE" ] && [ -f "$JOURNAL" ]; then
  echo "CONTROL_PLANE_STATE_INITIALIZED=ALREADY"
else
  die control_plane_partial_state
fi

python3 "$REPO/dev-hub/bin/control-plane-store.py"   --policy "$REPO/dev-hub/config/control-plane-state.v1.json"   --root "$STATE_ROOT"   verify --project wfgg-radar

python3 - "$STATE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
stage=((x.get('state') or {}).get('lifecycle') or {}).get('stage')
assert stage=='OPERATE',stage
print('CONTROL_PLANE_STAGE=OPERATE')
print('CONTROL_PLANE_INTEGRITY=PASS')
PY

if [ ! -e "$LEDGER" ]; then
  python3 "$REPO/dev-hub/bin/evidence-collector.py" init     --project wfgg-radar     --ledger "$LEDGER"
  echo "EVIDENCE_LEDGER_INITIALIZED=YES"
else
  python3 - "$LEDGER" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x.get('schema')=='chacha.dev/evidence-ledger/v1',x
assert x.get('project')=='wfgg-radar',x
print('EVIDENCE_LEDGER_INITIALIZED=ALREADY')
PY
fi

[ -f "$HEALTH_FILE" ] || die provider_health_missing
python3 - "$HEALTH_FILE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
p=(x.get('providers') or {}).get('radar-vps-runtime') or {}
assert p.get('state')=='HEALTHY',p
print('RADAR_RUNTIME_PROVIDER_HEALTH=HEALTHY')
PY

(
  cd "$REPO"
  python3 dev-hub/bin/project-control-cli.py     --repo-root "$REPO"     --policy dev-hub/config/project-control.v1.json     --json operate     --project wfgg-radar     --graph "$REPO/dev-hub/operations/wfgg-radar/runtime-status.task-graph.json"     --execute > "$RESULT"
)

python3 - "$RESULT" <<'PY'
import json,sys
from pathlib import Path
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x.get('schema')=='chacha.dev/project-control-response/v1',x
assert x.get('project')=='wfgg-radar',x
assert x.get('operation')=='operate',x
assert x.get('status')=='OK',x
d=x.get('details') or {}
assert d.get('current_stage')=='OPERATE',d
assert d.get('execution_mode')=='execute',d
run_path=d.get('RUN_RECORD')
assert run_path, d
run=Path(run_path)
assert run.is_file(),run
record=json.load(open(run,encoding='utf-8'))
assert record.get('project')=='wfgg-radar',record
assert record.get('mode')=='execute',record
assert (record.get('summary') or {}).get('succeeded')==1,record
tasks=[t for w in record.get('waves') or [] for t in w.get('tasks') or []]
assert len(tasks)==1,tasks
t=tasks[0]
assert t.get('task_id')=='radar-runtime:status',t
assert t.get('status')=='SUCCEEDED',t
result_path=t.get('task_result')
assert result_path,result_path
r=json.load(open(result_path,encoding='utf-8'))
assert r.get('schema')=='chacha.dev/task-result/v1',r
assert r.get('producer')=='radar-runtime-adapter',r
assert r.get('status')=='OK',r
assert (r.get('verification') or {}).get('status')=='UNVERIFIED',r
details=((r.get('evidence') or [{}])[0].get('details') or {})
assert details.get('radar_service')=='active',details
assert details.get('radar_sentinel_timer')=='active',details
assert details.get('radar_sentinel_enabled')=='enabled',details
assert details.get('collector_sentinel_timer')=='active',details
print('PROJECT_CONTROL_STATUS=OK')
print('PROJECT_CONTROL_TO_SCHEDULER=PASS')
print('SCHEDULER_TO_RUN_CONTROLLER=PASS')
print('RUN_CONTROLLER_TO_RADAR_ADAPTER=PASS')
print('RADAR_RUNTIME_STATUS_ACTION=PASS')
print('RADAR_SERVICE='+str(details.get('radar_service')))
print('RADAR_SENTINEL_TIMER='+str(details.get('radar_sentinel_timer')))
print('COLLECTOR_SENTINEL_TIMER='+str(details.get('collector_sentinel_timer')))
print('TASK_RESULT_VERIFICATION='+str((r.get('verification') or {}).get('status')))
print('RUN_RECORD='+str(run))
print('TASK_RESULT='+str(result_path))
print('CHACHA_DEV_RADAR_STATUS=PASS')
PY
