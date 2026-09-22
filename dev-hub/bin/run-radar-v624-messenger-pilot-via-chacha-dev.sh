#!/usr/bin/env bash
# V6.24 isolated Last War Messenger Outbox PILOT through ChaCha DEV.
# No Radar production deployment, no Sentinel pause, no Last War connection.
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V624_MESSENGER_DEPLOY_REV:-}"
PROJECT="wfgg-radar"
PILOT_REV="e8af95cf05be2446836226628a5facb9887f9509"
MESSENGER_SHA="3cf5d175325a319d601667e50388e8472057bcc152df7a618938daf357a3dfa1"
INSTALLER="radar-vps/install-v624-messenger-pilot.sh"
PROBE="radar-vps/probe-v624-messenger-pilot-runtime.sh"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v624-messenger.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
REPO=""

cleanup(){ rm -rf "$WORK"; }
die(){ echo "RADAR_V624_MESSENGER_CHACHA_DEPLOY=BLOCKED reason=$1"; exit 2; }
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required

for cmd in curl tar python3 sha256sum grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR V6.24 MESSENGER PILOT ==="
echo "DEV_HUB_REV=$REV"
echo "PILOT_REV=$PILOT_REV"
echo "EXPECTED_MESSENGER_SHA256=$MESSENGER_SHA"
echo "PRODUCTION_DEPLOYMENT=NO"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile   dev-hub/adapters/radar-runtime-adapter.py   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py   dev-hub/bin/verification-broker.py   dev-hub/bin/evidence-collector.py

python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "CHACHA_DEV_RADAR_ADAPTER_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh
echo "CHACHA_DEV_RADAR_ADAPTER_PROVISIONING=PASS"

mkdir -p "$PLAN_DIR"
STATE="$RUNTIME/state/$PROJECT/state.json"
LEDGER="$RUNTIME/evidence/$PROJECT/ledger.json"
[ -f "$STATE" ] || die project_state_missing
[ -f "$LEDGER" ] || die evidence_ledger_missing

PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-before.json"
python3 - "$WORK/verify-before.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_BEFORE=PASS')
PY

GRAPH="$PLAN_DIR/radar-v624-messenger-pilot.task-graph.json"
python3 - "$GRAPH" "$PILOT_REV" "$MESSENGER_SHA" "$INSTALLER" "$PROBE" <<'PY'
import json,sys
from datetime import datetime,timezone
p,rev,msha,installer,probe=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
g={
  "schema":"chacha.dev/task-graph/v1",
  "project":"wfgg-radar",
  "transition":"OPERATE->OPERATE",
  "generated_at":now,
  "tasks":[
    {
      "id":"radar-runtime:messenger-pilot-install-v624",
      "kind":"runtime-deploy",
      "description":"Install the isolated V6.24 dry-run Messenger Outbox under /opt/wfgg-messenger-pilot without touching Radar production.",
      "owner_role":"release",
      "capabilities":["radar-pilot-control"],
      "permission":"workspace-write",
      "depends_on":[],
      "outputs":[{"type":"artifact","id":"wfgg-messenger-outbox-v624-pilot"}],
      "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
      "blocking":True,
      "metadata":{"radar_runtime":{
        "action":"messenger-pilot-install",
        "revision":rev,
        "installer":installer,
        "expected_messenger_sha256":msha
      }}
    },
    {
      "id":"radar-runtime:messenger-pilot-probe-v624",
      "kind":"runtime-diagnostic",
      "description":"Probe the isolated V6.24 Messenger Outbox locally: DRAFT to QUEUED to HISTORY, cross-server guard and zero Last War network send.",
      "owner_role":"sre-observability",
      "capabilities":["radar-runtime-inspect"],
      "permission":"read",
      "depends_on":["radar-runtime:messenger-pilot-install-v624"],
      "outputs":[{"type":"gate","id":"radar-messenger-v624-runtime-pilot"}],
      "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
      "blocking":True,
      "metadata":{"radar_runtime":{
        "action":"messenger-pilot-probe",
        "revision":rev,
        "installer":installer,
        "probe":probe,
        "expected_messenger_sha256":msha
      }}
    }
  ],
  "summary":{"task_count":2,"artifact_tasks":1,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":2}
}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

SCHEDULE="$WORK/schedule.json"
PREPARE="$WORK/prepare.json"
DISPATCH="$WORK/dispatch.json"

"${PC[@]}" schedule --project "$PROJECT" --graph "$GRAPH" > "$SCHEDULE"
PLAN="$(python3 - "$SCHEDULE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
echo "RADAR_V624_MESSENGER_SCHEDULE=PASS"
echo "RADAR_V624_MESSENGER_PLAN=$PLAN"

"${PC[@]}" prepare-run --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" > "$PREPARE"
python3 - "$PREPARE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('RADAR_V624_MESSENGER_PREPARE=PASS')
PY

set +e
"${PC[@]}" dispatch --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" --execute > "$DISPATCH"
RC=$?
set -e
echo "RADAR_V624_MESSENGER_DISPATCH_RC=$RC"

RUN_RECORD="$(python3 - "$DISPATCH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
print((x.get('details') or {}).get('RUN_RECORD') or '')
PY
)"
[ -n "$RUN_RECORD" ] || die run_record_missing
echo "RADAR_V624_MESSENGER_RUN_RECORD=$RUN_RECORD"

python3 - "$RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
by={t.get('task_id'):t for t in tasks}
required=(
  'radar-runtime:messenger-pilot-install-v624',
  'radar-runtime:messenger-pilot-probe-v624',
)
for tid in required:
    t=by.get(tid) or {}
    print(tid.replace('radar-runtime:','').upper().replace('-','_')+'_STATUS='+str(t.get('status')))
    if t.get('status')!='SUCCEEDED':
        raise SystemExit('PILOT_TASK_NOT_SUCCEEDED:'+tid)
probe=by['radar-runtime:messenger-pilot-probe-v624']
rp=probe.get('task_result')
if not rp:
    raise SystemExit('MESSENGER_PROBE_TASK_RESULT_MISSING')
r=json.load(open(rp,encoding='utf-8'))
assert r.get('status')=='OK',r
assert r.get('summary')=='RADAR_MESSENGER_PILOT_PROBE_OK',r
print('RADAR_V624_MESSENGER_RUNTIME_PROBE=PASS')
print('RADAR_V624_GAME_CONNECTION=NONE')
print('RADAR_V624_GAME_SCAN_EXECUTED=NO')
print('RADAR_V624_MAIL_SEND_EXECUTED=NO')
print('RADAR_V624_LASTWAR_MUTATION=NO')
print('RADAR_V624_PRODUCTION_CONNECTOR_TOUCHED=NO')
PY

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "RADAR_V624_MESSENGER_CHACHA_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_V624_MESSENGER_PRODUCTION_APPROVAL_REQUIRED=NO"
echo "RADAR_V624_MESSENGER_PRODUCTION_DEPLOYMENT=NO"
echo "RADAR_V624_MESSENGER_CHACHA_DEPLOY=PASS"

trap - EXIT
cleanup
