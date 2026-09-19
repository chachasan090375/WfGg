#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_HISTORY_REV:-}"
PROJECT="wfgg-radar"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
WORK="$(mktemp -d /tmp/chacha-radar-history.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
RUNTIME="/opt/chacha-dev/runtime"
GRAPH="$RUNTIME/plans/$PROJECT/radar-history-performance-diagnostic.task-graph.json"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT
die(){ echo "RADAR_HISTORY_PERFORMANCE_E2E=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for cmd in curl tar python3 systemctl grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR HISTORY PERFORMANCE DIAGNOSTIC ==="
echo "SOURCE_REV=$REV"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile \
  dev-hub/adapters/radar-runtime-adapter.py \
  dev-hub/bin/project-control-cli.py \
  dev-hub/bin/project-control.py \
  dev-hub/bin/execution-scheduler.py \
  dev-hub/bin/run-controller.py \
  dev-hub/bin/external-runtime-dispatch.py

python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "RADAR_HISTORY_PERFORMANCE_CONTRACT_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh
echo "RADAR_HISTORY_PERFORMANCE_ADAPTER_PROVISIONING=PASS"

STATE="$RUNTIME/state/$PROJECT/state.json"
LEDGER="$RUNTIME/evidence/$PROJECT/ledger.json"
[ -f "$STATE" ] || die project_state_missing
[ -f "$LEDGER" ] || die evidence_ledger_missing
mkdir -p "$(dirname "$GRAPH")"

python3 - "$STATE" "$GRAPH" <<'PY'
import json,sys
from datetime import datetime,timezone
state_path,graph_path=sys.argv[1:3]
state=json.load(open(state_path,encoding='utf-8'))
stage=str((((state.get('state') or {}).get('lifecycle') or {}).get('stage')) or 'IDEA')
graph={
  'schema':'chacha.dev/task-graph/v1',
  'project':'wfgg-radar',
  'transition':f'{stage}->CONTROL_DIAGNOSTIC',
  'generated_at':datetime.now(timezone.utc).isoformat(),
  'tasks':[{
    'id':'radar-runtime:history-performance-diagnostic',
    'kind':'runtime-diagnostic',
    'description':'Measure the V6.14 cycle-history reconstruction cost against the Collector SQLite database through the ENABLED ChaCha DEV Radar runtime adapter.',
    'owner_role':'sre-observability',
    'capabilities':['radar-runtime-inspect'],
    'permission':'read',
    'depends_on':[],
    'outputs':[{'type':'artifact','id':'radar-history-performance-diagnostic'}],
    'verification':{
      'mode':'machine',
      'self_certification_allowed':False,
      'required_evidence':['source','timestamp','digest']
    },
    'blocking':True,
    'parallel_group':'radar-runtime-diagnostic',
    'metadata':{'radar_runtime':{'action':'history-performance-diagnostic'}}
  }],
  'summary':{
    'task_count':1,'artifact_tasks':1,'gate_tasks':0,'approval_tasks':0,'blocking_tasks':1
  }
}
open(graph_path,'w',encoding='utf-8').write(json.dumps(graph,indent=2)+'\n')
print('RADAR_HISTORY_PERFORMANCE_GRAPH='+graph_path)
print('RADAR_HISTORY_PERFORMANCE_PROJECT_STAGE='+stage)
PY

PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

set +e
"${PC[@]}" status --project "$PROJECT" > "$WORK/status.json"
STATUS_RC=$?
set -e
python3 - "$WORK/status.json" "$STATUS_RC" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); rc=int(sys.argv[2])
print('PROJECT_CONTROL_STATUS_VALUE='+str(x.get('status')))
print('PROJECT_CONTROL_STATUS_RC='+str(rc))
print('PROJECT_CONTROL_STATUS_BLOCKERS='+','.join(x.get('blockers') or []))
print('PROJECT_CONTROL_NONREADY_ALLOWED_FOR_READONLY_DIAGNOSTIC=YES')
PY

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-state.json"
python3 - "$WORK/verify-state.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY=PASS')
PY

"${PC[@]}" schedule --project "$PROJECT" --graph "$GRAPH" > "$WORK/schedule.json"
PLAN="$(python3 - "$WORK/schedule.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
echo "PROJECT_CONTROL_SCHEDULER=PASS"
echo "EXECUTION_PLAN=$PLAN"

"${PC[@]}" prepare-run --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" > "$WORK/prepare.json"
python3 - "$WORK/prepare.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('RUN_CONTROLLER_PREPARE=PASS')
PY

"${PC[@]}" dispatch --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" --execute > "$WORK/dispatch.json"
RUN_RECORD="$(python3 - "$WORK/dispatch.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print((x.get('details') or {})['RUN_RECORD'])
PY
)"
echo "PROJECT_CONTROL_DISPATCH=PASS"
echo "RUN_RECORD=$RUN_RECORD"

RESULT="$(python3 - "$RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
assert len(tasks)==1,tasks
assert tasks[0]['task_id']=='radar-runtime:history-performance-diagnostic',tasks[0]
print(tasks[0]['task_result'])
PY
)"
echo "TASK_RESULT=$RESULT"

python3 - "$RESULT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['schema']=='chacha.dev/task-result/v1',x
assert x['project']=='wfgg-radar',x
assert x['task_id']=='radar-runtime:history-performance-diagnostic',x
assert x['status']=='OK',x
assert x['producer']=='radar-runtime-adapter',x
assert x['verification']['status']=='UNVERIFIED',x
ev=x.get('evidence') or []
assert ev,x
d=ev[0].get('details') or {}
print('RADAR_HISTORY_PERFORMANCE_DIAGNOSTIC=PASS')
print('DB_EXISTS='+('YES' if d.get('db_exists') else 'NO'))
print('DB_READABLE='+('YES' if d.get('db_readable') else 'NO'))
print('REQUIRED_TABLES_PRESENT='+('YES' if d.get('required_tables_present') else 'NO'))
print('CYCLE_COUNT='+str(d.get('cycle_count')))
print('SEEN_ROWS='+str(d.get('seen_rows')))
print('HASH_MATCHED='+str(d.get('hash_matched')))
print('HASH_MISMATCHED='+str(d.get('hash_mismatched')))
print('UNRESOLVED='+str(d.get('unresolved')))
print('ELAPSED_MS='+str(d.get('elapsed_ms')))
print('EXCEEDS_CATALOG_BUDGET_30S='+('YES' if d.get('exceeds_catalog_budget_30s') else 'NO'))
print('FAILURE_CLASS='+str(d.get('failure_class') or 'NONE'))
print('INDEXES='+json.dumps(d.get('indexes') or {},sort_keys=True,separators=(',',':')))
print('SLOWEST_CYCLES='+json.dumps(d.get('slowest_cycles') or [],sort_keys=True,separators=(',',':')))
print('RADAR_ADAPTER_SELF_VERIFIED=NO')
PY

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/post-verify-state.json"
python3 - "$WORK/post-verify-state.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_POST_RUN_INTEGRITY=PASS')
PY

echo "RADAR_PRODUCTION_MUTATION=NO"
echo "COLLECTOR_DATA_MUTATION=NO"
echo "RADAR_HISTORY_PERFORMANCE_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_HISTORY_PERFORMANCE_E2E=PASS"
