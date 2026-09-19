#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_CP_REV:-}"
PROJECT="wfgg-radar"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
WORK="$(mktemp -d /tmp/chacha-radar-control-plane.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
RUNTIME="/opt/chacha-dev/runtime"
GRAPH="$RUNTIME/plans/$PROJECT/radar-runtime-status.task-graph.json"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

die(){ echo "RADAR_CONTROL_PLANE_E2E=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required

for cmd in curl tar python3 systemctl grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR CONTROL-PLANE E2E ==="
echo "SOURCE_REV=$REV"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed

cd "$REPO"

python3 -m py_compile   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py

python3 - <<'PY'
import json
x=json.load(open('dev-hub/config/provider-adapters.v1.json',encoding='utf-8'))
a=x['adapters']['radar-runtime-adapter']
assert a['status']=='ENABLED',a
assert a['executable']=='/opt/chacha-dev/adapters/radar-runtime/current/radar-runtime-adapter',a
print('RADAR_CONTROL_PLANE_REGISTRY=ENABLED')
PY

[ -x /opt/chacha-dev/adapters/radar-runtime/current/radar-runtime-adapter ] || die adapter_runtime_missing

RADAR_SENTINEL_STATE="$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
RADAR_SENTINEL_ENABLED="$(systemctl is-enabled wfgg-radar-sentinel.timer 2>/dev/null || true)"
COLLECTOR_SENTINEL_STATE="$(systemctl is-active wfgg-collector-sentinel.timer 2>/dev/null || true)"
[ "$RADAR_SENTINEL_STATE" = "active" ] || die radar_sentinel_not_active
[ "$RADAR_SENTINEL_ENABLED" = "enabled" ] || die radar_sentinel_not_enabled
[ "$COLLECTOR_SENTINEL_STATE" = "active" ] || die collector_sentinel_not_active

STATE="$RUNTIME/state/$PROJECT/state.json"
LEDGER="$RUNTIME/evidence/$PROJECT/ledger.json"
if [ ! -f "$STATE" ]; then
  python3 dev-hub/bin/control-plane-store.py     --policy dev-hub/config/control-plane-state.v1.json     --root "$RUNTIME/state"     init --project "$PROJECT" --actor chacha-dev-radar-onboarding
  echo "RADAR_CONTROL_PLANE_STATE_BOOTSTRAPPED=YES"
else
  echo "RADAR_CONTROL_PLANE_STATE_BOOTSTRAPPED=NO"
fi
if [ ! -f "$LEDGER" ]; then
  python3 dev-hub/bin/evidence-collector.py init     --project "$PROJECT" --ledger "$LEDGER"
  echo "RADAR_EVIDENCE_LEDGER_BOOTSTRAPPED=YES"
else
  echo "RADAR_EVIDENCE_LEDGER_BOOTSTRAPPED=NO"
fi

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
    'id':'radar-runtime:status',
    'kind':'health',
    'description':'Read WfGg Radar runtime status through the ENABLED ChaCha DEV runtime adapter.',
    'owner_role':'sre-observability',
    'capabilities':['radar-runtime-inspect'],
    'permission':'read',
    'depends_on':[],
    'outputs':[{'type':'artifact','id':'radar-runtime-status'}],
    'verification':{
      'mode':'machine',
      'self_certification_allowed':False,
      'required_evidence':['source','timestamp','digest']
    },
    'blocking':True,
    'parallel_group':'radar-runtime-diagnostic',
    'metadata':{'radar_runtime':{'action':'status'}}
  }],
  'summary':{
    'task_count':1,'artifact_tasks':0,'gate_tasks':0,'approval_tasks':0,'blocking_tasks':1
  }
}
open(graph_path,'w',encoding='utf-8').write(json.dumps(graph,indent=2)+'\n')
print('RADAR_CONTROL_PLANE_GRAPH='+graph_path)
print('RADAR_CONTROL_PLANE_PROJECT_STAGE='+stage)
PY

PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

"${PC[@]}" status --project "$PROJECT" > "$WORK/status.json"
python3 - "$WORK/status.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['project']=='wfgg-radar',x
assert x['status'] in {'READY','OK','COMPLETE','BLOCKED','AWAITING_APPROVAL','DEGRADED','UNKNOWN'},x
print('PROJECT_CONTROL_STATUS=PASS')
print('PROJECT_CONTROL_STATUS_VALUE='+str(x['status']))
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
d=x.get('details') or {}
print(d['execution_plan'])
PY
)"
echo "PROJECT_CONTROL_SCHEDULER=PASS"
echo "EXECUTION_PLAN=$PLAN"

python3 - "$PLAN" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['schema']=='chacha.dev/execution-plan/v1',x
assert x['project']=='wfgg-radar',x
assert x['summary']['task_count']==1,x
assert x['summary']['scheduled_count']==1,x
assert x['summary']['blocked_count']==0,x
tasks=[t for w in x['waves'] for t in w['tasks']]
t=tasks[0]
assert t['task_id']=='radar-runtime:status',t
b=t['provider_bindings'][0]
assert b['capability']=='radar-runtime-inspect',b
assert b['provider']=='radar-vps-runtime',b
assert b['health_state']=='HEALTHY',b
assert b['state'] in {'READY','DEGRADED'},b
print('SCHEDULER_BINDING=radar-vps-runtime')
print('SCHEDULER_HEALTH=HEALTHY')
PY

"${PC[@]}" prepare-run   --project "$PROJECT"   --plan "$PLAN"   --graph "$GRAPH" > "$WORK/prepare.json"
python3 - "$WORK/prepare.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('RUN_CONTROLLER_PREPARE=PASS')
PY

"${PC[@]}" dispatch   --project "$PROJECT"   --plan "$PLAN"   --graph "$GRAPH"   --execute > "$WORK/dispatch.json"

RUN_RECORD="$(python3 - "$WORK/dispatch.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
d=x.get('details') or {}
print(d['RUN_RECORD'])
PY
)"
echo "PROJECT_CONTROL_DISPATCH=PASS"
echo "RUN_RECORD=$RUN_RECORD"

RESULT="$(python3 - "$RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['schema']=='chacha.dev/run-record/v1',x
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
assert len(tasks)==1,tasks
t=tasks[0]
assert t['task_id']=='radar-runtime:status',t
print(t['task_result'])
PY
)"
echo "TASK_RESULT=$RESULT"

python3 - "$RESULT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['schema']=='chacha.dev/task-result/v1',x
assert x['project']=='wfgg-radar',x
assert x['task_id']=='radar-runtime:status',x
assert x['status']=='OK',x
assert x['producer']=='radar-runtime-adapter',x
assert x['verification']['status']=='UNVERIFIED',x
ev=x.get('evidence') or []
assert ev, x
d=ev[0].get('details') or {}
assert d.get('radar_service')=='active',d
assert d.get('radar_sentinel_timer')=='active',d
assert d.get('radar_sentinel_enabled')=='enabled',d
assert d.get('collector_sentinel_timer')=='active',d
print('RADAR_ADAPTER_EXECUTION=PASS')
print('RADAR_ADAPTER_RESULT=OK')
print('RADAR_ADAPTER_SELF_VERIFIED=NO')
print('RADAR_SERVICE='+str(d.get('radar_service')))
print('RADAR_SENTINEL_TIMER='+str(d.get('radar_sentinel_timer')))
print('COLLECTOR_SENTINEL_TIMER='+str(d.get('collector_sentinel_timer')))
PY

set +e
"${PC[@]}" verify-result   --project "$PROJECT"   --result "$RESULT"   --graph "$GRAPH"   --method machine   --verifier verification-broker > "$WORK/verification.json"
VERIFY_RC=$?
set -e

python3 - "$WORK/verification.json" "$VERIFY_RC" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
rc=int(sys.argv[2])
assert x['status']=='BLOCKED',x
blockers=x.get('blockers') or []
assert any('NEEDS_INDEPENDENT_CHECK' in b for b in blockers),blockers
assert rc==2,rc
print('VERIFICATION_BROKER=PASS')
print('VERIFICATION_STATUS=NEEDS_INDEPENDENT_CHECK')
print('VERIFICATION_FAIL_CLOSED=PASS')
PY

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/post-verify-state.json"
python3 - "$WORK/post-verify-state.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_POST_RUN_INTEGRITY=PASS')
PY

echo "RADAR_PRODUCTION_MUTATION=NO"
echo "RADAR_CONTROL_PLANE_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_CONTROL_PLANE_E2E=PASS"
echo "RADAR_CONTROL_PLANE_NEXT=ADD_INDEPENDENT_RUNTIME_VERIFIER"
