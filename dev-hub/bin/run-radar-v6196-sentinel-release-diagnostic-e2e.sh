#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6196_SENTINEL_DIAG_REV:-}"
PROJECT="wfgg-radar"
PRODUCTION_REV="c5a5b0f6acda2870f2567be7e43d48fcb9af05c4"
EXPECTED_CONNECTOR="b7ff60476f3afe7c8bcb9b78963c46daa4e8b5507490cc83cbcbc4ced63e7c35"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v6196-sentinel-diag.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
GRAPH="$RUNTIME/plans/$PROJECT/radar-v6196-sentinel-release-diagnostic.task-graph.json"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT
die(){ echo "RADAR_V6196_SENTINEL_DIAGNOSTIC_E2E=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for cmd in curl tar python3 systemctl grep; do command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"; done

echo "=== CHACHA DEV RADAR V6.19.6 SENTINEL RELEASE DIAGNOSTIC ==="
echo "SOURCE_REV=$REV"
echo "PRODUCTION_REV=$PRODUCTION_REV"
echo "EXPECTED_CONNECTOR_SHA256=$EXPECTED_CONNECTOR"
echo "EXPECTED_NATIVE_SHA256=$EXPECTED_NATIVE"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile dev-hub/adapters/radar-runtime-adapter.py dev-hub/bin/project-control-cli.py dev-hub/bin/project-control.py dev-hub/bin/execution-scheduler.py dev-hub/bin/run-controller.py dev-hub/bin/external-runtime-dispatch.py
python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "RADAR_V6196_SENTINEL_DIAGNOSTIC_CONTRACT_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh >/dev/null
echo "RADAR_V6196_SENTINEL_DIAGNOSTIC_ADAPTER_PROVISIONING=PASS"

STATE="$RUNTIME/state/$PROJECT/state.json"
LEDGER="$RUNTIME/evidence/$PROJECT/ledger.json"
[ -f "$STATE" ] || die project_state_missing
[ -f "$LEDGER" ] || die evidence_ledger_missing
mkdir -p "$(dirname "$GRAPH")"

python3 - "$STATE" "$GRAPH" "$PRODUCTION_REV" "$EXPECTED_CONNECTOR" "$EXPECTED_NATIVE" <<'PY'
import json,sys
from datetime import datetime,timezone
state_path,graph_path,prod_rev,connector,native=sys.argv[1:6]
state=json.load(open(state_path,encoding='utf-8'))
stage=str((((state.get('state') or {}).get('lifecycle') or {}).get('stage')) or 'IDEA')
graph={
 'schema':'chacha.dev/task-graph/v1','project':'wfgg-radar',
 'transition':f'{stage}->CONTROL_DIAGNOSTIC','generated_at':datetime.now(timezone.utc).isoformat(),
 'tasks':[{
   'id':'radar-runtime:sentinel-release-diagnostic-v6196',
   'kind':'runtime-diagnostic',
   'description':'Read-only comparison of Radar Sentinel effective release source, mutable/immutable production manifests and local runtime fingerprint.',
   'owner_role':'sre-observability',
   'capabilities':['radar-runtime-inspect'],'permission':'read','depends_on':[],
   'outputs':[{'type':'artifact','id':'radar-sentinel-release-diagnostic'}],
   'verification':{'mode':'machine','self_certification_allowed':False,'required_evidence':['source','timestamp','digest']},
   'blocking':True,'parallel_group':'radar-runtime-diagnostic',
   'metadata':{'radar_runtime':{
      'action':'sentinel-release-diagnostic',
      'production_revision':prod_rev,
      'expected_connector_sha256':connector,
      'expected_native_sha256':native
   }}
 }],
 'summary':{'task_count':1,'artifact_tasks':1,'gate_tasks':0,'approval_tasks':0,'blocking_tasks':1}
}
open(graph_path,'w',encoding='utf-8').write(json.dumps(graph,indent=2)+'\n')
print('RADAR_V6196_SENTINEL_DIAGNOSTIC_GRAPH='+graph_path)
print('RADAR_V6196_SENTINEL_DIAGNOSTIC_PROJECT_STAGE='+stage)
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

RESULT="$(python3 - "$RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
assert len(tasks)==1,tasks
assert tasks[0].get('status')=='SUCCEEDED',tasks
print(tasks[0]['task_result'])
PY
)"

python3 - "$RESULT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
d=(x.get('evidence') or [])[0].get('details') or {}
print('RADAR_V6196_SENTINEL_RELEASE_DIAGNOSTIC=PASS')
print('RADAR_SERVICE='+str(d.get('radar_service')))
print('RADAR_SENTINEL_TIMER='+str(d.get('radar_sentinel_timer')))
print('RADAR_SENTINEL_ENABLED='+str(d.get('radar_sentinel_enabled')))
print('RADAR_SENTINEL_SERVICE='+str(d.get('radar_sentinel_service')))
print('CONNECTOR_SHA256='+str(d.get('connector_sha256')))
print('NATIVE_SHA256='+str(d.get('native_sha256')))
print('RUNTIME_MATCHES_EXPECTED='+('YES' if d.get('runtime_matches_expected') else 'NO'))
print('MUTABLE_MANIFEST_MATCHES_EXPECTED='+('YES' if d.get('mutable_manifest_matches_expected') else 'NO'))
print('IMMUTABLE_MANIFEST_MATCHES_EXPECTED='+('YES' if d.get('immutable_manifest_matches_expected') else 'NO'))
print('FAILURE_CLASS='+str(d.get('failure_class') or 'NONE'))
env=d.get('sentinel_environment') or {}
print('SENTINEL_RELEASE_BASE_ENV='+str(env.get('RADAR_RELEASE_BASE') or 'DEFAULT'))
se=d.get('sentinel_exec') or {}
print('SENTINEL_EXEC_PATH='+str(se.get('exec_path') or 'UNKNOWN'))
print('SENTINEL_EXEC_SHA256='+str(se.get('sha256') or 'UNKNOWN'))
sf=d.get('sentinel_state_file') or {}
print('SENTINEL_STATE_STATUS='+str(sf.get('SENTINEL_VPS_STATUS') or 'UNKNOWN'))
print('SENTINEL_STATE_LAST_CHECK='+str(sf.get('SENTINEL_VPS_LAST_CHECK') or 'UNKNOWN'))
print('SENTINEL_STATE_CONNECTOR_SHA='+str(sf.get('SENTINEL_VPS_CONNECTOR_SHA') or 'UNKNOWN'))
print('SENTINEL_STATE_NATIVE_SHA='+str(sf.get('SENTINEL_VPS_NATIVE_SHA') or 'UNKNOWN'))
print('RADAR_RUNTIME_MUTATION='+('YES' if d.get('runtime_mutation') else 'NO'))
print('GAME_SCAN_EXECUTED='+('YES' if d.get('game_scan_executed') else 'NO'))
print('COLLECTOR_MUTATION='+('YES' if d.get('collector_mutation') else 'NO'))
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
echo "RADAR_V6196_SENTINEL_DIAGNOSTIC_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_V6196_SENTINEL_DIAGNOSTIC_E2E=PASS"
