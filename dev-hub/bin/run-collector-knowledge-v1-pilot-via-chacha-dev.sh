#!/usr/bin/env bash
# WfGg Collector Knowledge Engine V1 PILOT through ChaCha DEV.
# Background knowledge services only. No Radar production deploy and no Last War game connection.
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_COLLECTOR_KNOWLEDGE_DEPLOY_REV:-}"
PROJECT="wfgg-radar"
KNOWLEDGE_REV="6ddbc5d848cf2aebc2c6175b2aa9ba1645c2e2ae"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-collector-knowledge-v1.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
REPO=""

cleanup(){ rm -rf "$WORK"; }
die(){ echo "COLLECTOR_KNOWLEDGE_CHACHA_PILOT=BLOCKED reason=$1"; exit 2; }
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required

for cmd in curl tar python3 grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV COLLECTOR KNOWLEDGE ENGINE V1 PILOT ==="
echo "DEV_HUB_REV=$REV"
echo "KNOWLEDGE_REV=$KNOWLEDGE_REV"
echo "PRODUCTION_DEPLOYMENT=NO"
echo "LASTWAR_GAME_CONNECTION=NONE"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile   dev-hub/adapters/collector-knowledge-adapter.py   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py   dev-hub/bin/verification-broker.py   dev-hub/bin/evidence-collector.py

python3 dev-hub/tests/test_collector_knowledge_adapter_contract.py >/dev/null
echo "COLLECTOR_KNOWLEDGE_ADAPTER_TESTS=PASS"

WFGG_DEV_HUB_COLLECTOR_KNOWLEDGE_ADAPTER_REV="$REV"   bash dev-hub/bin/install-collector-knowledge-adapter-pilot.sh
echo "COLLECTOR_KNOWLEDGE_ADAPTER_PROVISIONING=PASS"

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

GRAPH="$PLAN_DIR/collector-knowledge-v1-pilot.task-graph.json"
python3 - "$GRAPH" "$KNOWLEDGE_REV" <<'PY'
import json,sys
from datetime import datetime,timezone
path,rev=sys.argv[1:]
g={
  "schema":"chacha.dev/task-graph/v1",
  "project":"wfgg-radar",
  "transition":"OPERATE->OPERATE",
  "generated_at":datetime.now(timezone.utc).isoformat(),
  "tasks":[
    {
      "id":"collector-knowledge:pilot-install-v1",
      "kind":"runtime-deploy",
      "description":"Install the permanent Collector Knowledge Engine worker and localhost read-only API without changing Radar production binaries.",
      "owner_role":"collector-runtime",
      "capabilities":["collector-knowledge-control"],
      "permission":"workspace-write",
      "depends_on":[],
      "outputs":[{"type":"artifact","id":"collector-knowledge-engine-v1-pilot"}],
      "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
      "blocking":True,
      "metadata":{"collector_knowledge":{"action":"pilot-install","revision":rev}}
    },
    {
      "id":"collector-knowledge:pilot-probe-v1",
      "kind":"runtime-diagnostic",
      "description":"Probe the permanent Collector Knowledge Engine worker, API, persistent database and production-isolation invariants.",
      "owner_role":"sre-observability",
      "capabilities":["collector-knowledge-inspect"],
      "permission":"read",
      "depends_on":["collector-knowledge:pilot-install-v1"],
      "outputs":[{"type":"gate","id":"collector-knowledge-v1-runtime-pilot"}],
      "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
      "blocking":True,
      "metadata":{"collector_knowledge":{"action":"pilot-probe","revision":rev}}
    },
    {
      "id":"collector-knowledge:query-v1",
      "kind":"knowledge-query",
      "description":"Exercise the governed localhost query path after the runtime probe.",
      "owner_role":"collector-intelligence",
      "capabilities":["collector-knowledge-inspect"],
      "permission":"read",
      "depends_on":["collector-knowledge:pilot-probe-v1"],
      "outputs":[{"type":"artifact","id":"collector-knowledge-query-result"}],
      "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
      "blocking":True,
      "metadata":{"collector_knowledge":{"action":"query","q":"totalNum","limit":10}}
    }
  ],
  "summary":{"task_count":3,"artifact_tasks":2,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":3}
}
open(path,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
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
echo "COLLECTOR_KNOWLEDGE_SCHEDULE=PASS"
echo "COLLECTOR_KNOWLEDGE_PLAN=$PLAN"

"${PC[@]}" prepare-run --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" > "$PREPARE"
python3 - "$PREPARE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('COLLECTOR_KNOWLEDGE_PREPARE=PASS')
PY

set +e
"${PC[@]}" dispatch --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" --execute > "$DISPATCH"
RC=$?
set -e
echo "COLLECTOR_KNOWLEDGE_DISPATCH_RC=$RC"

RUN_RECORD="$(python3 - "$DISPATCH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
print((x.get('details') or {}).get('RUN_RECORD') or '')
PY
)"
[ -n "$RUN_RECORD" ] || die run_record_missing
echo "COLLECTOR_KNOWLEDGE_RUN_RECORD=$RUN_RECORD"

python3 - "$RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
by={t.get('task_id'):t for t in tasks}
required=(
  'collector-knowledge:pilot-install-v1',
  'collector-knowledge:pilot-probe-v1',
  'collector-knowledge:query-v1',
)
for tid in required:
    t=by.get(tid) or {}
    label=tid.replace('collector-knowledge:','').upper().replace('-','_')
    print(label+'_STATUS='+str(t.get('status')))
    blockers=t.get('blockers') or []
    if blockers:
        print(label+'_BLOCKERS='+','.join(map(str,blockers)))
    rp=t.get('task_result')
    if rp:
        tr=json.load(open(rp,encoding='utf-8'))
        print(label+'_RESULT_STATUS='+str(tr.get('status')))
        print(label+'_RESULT_SUMMARY='+str(tr.get('summary')))
    if t.get('status')!='SUCCEEDED':
        raise SystemExit('COLLECTOR_KNOWLEDGE_TASK_NOT_SUCCEEDED:'+tid)

probe=by['collector-knowledge:pilot-probe-v1']
pr=json.load(open(probe['task_result'],encoding='utf-8'))
assert pr.get('status')=='OK',pr
assert pr.get('summary')=='COLLECTOR_KNOWLEDGE_PILOT_PROBE_OK',pr
query=by['collector-knowledge:query-v1']
qr=json.load(open(query['task_result'],encoding='utf-8'))
assert qr.get('status')=='OK',qr
assert qr.get('summary')=='COLLECTOR_KNOWLEDGE_QUERY_OK',qr
print('COLLECTOR_KNOWLEDGE_RUNTIME_PROBE=PASS')
print('COLLECTOR_KNOWLEDGE_QUERY_PATH=PASS')
print('COLLECTOR_KNOWLEDGE_LASTWAR_GAME_CONNECTION=NONE')
print('COLLECTOR_KNOWLEDGE_LASTWAR_MUTATION=NO')
print('COLLECTOR_KNOWLEDGE_PRODUCTION_CONNECTOR_TOUCHED=NO')
PY

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "COLLECTOR_KNOWLEDGE_CHACHA_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>COLLECTOR_KNOWLEDGE_ADAPTER"
echo "COLLECTOR_KNOWLEDGE_PRODUCTION_APPROVAL_REQUIRED=NO"
echo "COLLECTOR_KNOWLEDGE_PRODUCTION_DEPLOYMENT=NO"
echo "COLLECTOR_KNOWLEDGE_CHACHA_PILOT=PASS"

trap - EXIT
cleanup
