#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_AUTOPILOT_DIAG_REV:-}"
PROJECT="wfgg-radar"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-autopilot.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
GRAPH="$RUNTIME/plans/$PROJECT/radar-autopilot-progress-diagnostic.task-graph.json"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT
die(){ echo "RADAR_AUTOPILOT_PROGRESS_E2E=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for cmd in curl tar python3 systemctl grep; do command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"; done

echo "=== CHACHA DEV RADAR AUTOPILOT PROGRESS DIAGNOSTIC ==="
echo "SOURCE_REV=$REV"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile dev-hub/adapters/radar-runtime-adapter.py dev-hub/bin/project-control-cli.py dev-hub/bin/project-control.py dev-hub/bin/execution-scheduler.py dev-hub/bin/run-controller.py dev-hub/bin/external-runtime-dispatch.py
python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "RADAR_AUTOPILOT_PROGRESS_CONTRACT_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh
echo "RADAR_AUTOPILOT_PROGRESS_ADAPTER_PROVISIONING=PASS"

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
 'schema':'chacha.dev/task-graph/v1','project':'wfgg-radar',
 'transition':f'{stage}->CONTROL_DIAGNOSTIC','generated_at':datetime.now(timezone.utc).isoformat(),
 'tasks':[{
   'id':'radar-runtime:autopilot-progress-diagnostic',
   'kind':'runtime-diagnostic',
   'description':'Read-only inference of current Radar Autopilot activity from Collector targeted-cycle evidence. Does not start/stop Autopilot or contact Last War.',
   'owner_role':'sre-observability',
   'capabilities':['radar-runtime-inspect'],'permission':'read','depends_on':[],
   'outputs':[{'type':'artifact','id':'radar-autopilot-progress-diagnostic'}],
   'verification':{'mode':'machine','self_certification_allowed':False,'required_evidence':['source','timestamp','digest']},
   'blocking':True,'parallel_group':'radar-runtime-diagnostic',
   'metadata':{'radar_runtime':{'action':'autopilot-progress-diagnostic'}}
 }],
 'summary':{'task_count':1,'artifact_tasks':1,'gate_tasks':0,'approval_tasks':0,'blocking_tasks':1}
}
open(graph_path,'w',encoding='utf-8').write(json.dumps(graph,indent=2)+'\n')
print('RADAR_AUTOPILOT_PROGRESS_GRAPH='+graph_path)
print('RADAR_AUTOPILOT_PROGRESS_PROJECT_STAGE='+stage)
PY

PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify.json"
python3 - "$WORK/verify.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY=PASS')
PY

"${PC[@]}" schedule --project "$PROJECT" --graph "$GRAPH" > "$WORK/schedule.json"
PLAN="$(python3 - "$WORK/schedule.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
echo "PROJECT_CONTROL_SCHEDULER=PASS"
echo "EXECUTION_PLAN=$PLAN"

"${PC[@]}" prepare-run --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" > "$WORK/prepare.json"
python3 - "$WORK/prepare.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print('RUN_CONTROLLER_PREPARE=PASS')
PY

"${PC[@]}" dispatch --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" --execute > "$WORK/dispatch.json"
RUN_RECORD="$(python3 - "$WORK/dispatch.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
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
print(tasks[0]['task_result'])
PY
)"
echo "TASK_RESULT=$RESULT"

python3 - "$RESULT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
d=(x.get('evidence') or [])[0].get('details') or {}
second=d.get('second') or {}
print('RADAR_AUTOPILOT_PROGRESS_DIAGNOSTIC=PASS')
print('RADAR_SERVICE='+str(second.get('radar_service')))
print('CONNECTOR_SHA256='+str(second.get('connector_sha256')))
print('AUTOPILOT_ACTIVITY_EVIDENCE='+str(d.get('autopilot_activity_evidence')))
print('NEW_TARGETED_CYCLE_OBSERVED='+('YES' if d.get('new_targeted_cycle_observed') else 'NO'))
print('LATEST_CYCLE_ID='+str(second.get('latest_cycle_id') or 'NONE'))
print('LATEST_QUERY='+str(second.get('latest_query') or 'NONE'))
print('LATEST_STATUS='+str(second.get('latest_status') or 'NONE'))
print('LATEST_STARTED_AT='+str(second.get('latest_started_at') or 'NONE'))
print('LATEST_FINISHED_AT='+str(second.get('latest_finished_at') or 'NONE'))
print('LATEST_ERROR='+str(second.get('latest_error') or 'NONE'))
active=second.get('active_targeted_cycles') or []
print('ACTIVE_TARGETED_CYCLE_COUNT='+str(len(active)))
for i,item in enumerate(active[:3],1):
    print(f'ACTIVE_{i}_ID='+str(item.get('id')))
    print(f'ACTIVE_{i}_QUERY='+str(item.get('query')))
    print(f'ACTIVE_{i}_STATUS='+str(item.get('status')))
recent=second.get('latest_targeted_cycles') or []
print('RECENT_TARGETED_CYCLE_COUNT='+str(len(recent)))
for i,item in enumerate(recent[:8],1):
    print(f'RECENT_{i}_ID='+str(item.get('id')))
    print(f'RECENT_{i}_QUERY='+str(item.get('query') or 'NONE'))
    print(f'RECENT_{i}_STATUS='+str(item.get('status') or 'NONE'))
    print(f'RECENT_{i}_ERROR='+str(item.get('error') or 'NONE'))
    print(f'RECENT_{i}_STARTED_AT='+str(item.get('started_at') or 'NONE'))
    print(f'RECENT_{i}_FINISHED_AT='+str(item.get('finished_at') or 'NONE'))
print('EXACT_JOB_STATUS_AVAILABLE='+('YES' if d.get('definitive_job_status_available') else 'NO'))
print('JOB_STATUS_NOTE='+str(d.get('job_status_note') or ''))
print('RADAR_ADAPTER_SELF_VERIFIED=NO')
PY

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/post.json"
python3 - "$WORK/post.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print('PROJECT_CONTROL_POST_RUN_INTEGRITY=PASS')
PY

echo "LASTWAR_CONTACT=NO"
echo "RADAR_PRODUCTION_MUTATION=NO"
echo "COLLECTOR_DATA_MUTATION=NO"
echo "RADAR_AUTOPILOT_PROGRESS_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_AUTOPILOT_PROGRESS_E2E=PASS"
