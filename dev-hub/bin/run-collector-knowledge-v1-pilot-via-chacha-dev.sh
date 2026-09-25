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
HEALTH="$RUNTIME/health/$PROJECT/providers.json"
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

BOOTSTRAP_GRAPH_RAW="$WORK/collector-knowledge-v1-bootstrap.unbound.task-graph.json"
BOOTSTRAP_GRAPH="$PLAN_DIR/collector-knowledge-v1-bootstrap.task-graph.json"
python3 - "$BOOTSTRAP_GRAPH_RAW" "$KNOWLEDGE_REV" <<'PY'
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
      "owner_role":"collector-runtime-agent",
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
      "description":"Independently probe the installed Knowledge Engine and production-isolation invariants before declaring runtime health.",
      "owner_role":"sre-observability-agent",
      "capabilities":["collector-knowledge-control"],
      "permission":"read",
      "depends_on":["collector-knowledge:pilot-install-v1"],
      "outputs":[{"type":"gate","id":"collector-knowledge-v1-runtime-pilot"}],
      "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
      "blocking":True,
      "metadata":{"collector_knowledge":{"action":"pilot-probe","revision":rev}}
    }
  ],
  "summary":{"task_count":2,"artifact_tasks":1,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":2}
}
open(path,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

EMPTY_AGENT_CONTRACTS="$WORK/empty-agent-contracts.json"
EMPTY_COMPONENT_CONTRACTS="$WORK/empty-component-contracts.json"
printf '%s\n' '{"contracts":[]}' > "$EMPTY_AGENT_CONTRACTS"
printf '%s\n' '{"contracts":[]}' > "$EMPTY_COMPONENT_CONTRACTS"
python3 dev-hub/bin/task-contract-binder.py \
  --graph "$BOOTSTRAP_GRAPH_RAW" \
  --agent-contracts "$EMPTY_AGENT_CONTRACTS" \
  --component-contracts "$EMPTY_COMPONENT_CONTRACTS" \
  --role-contracts dev-hub/config/guardian-role-contracts.v1.json \
  --output "$BOOTSTRAP_GRAPH" > "$WORK/bootstrap-binding.txt"
python3 - "$BOOTSTRAP_GRAPH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
b=x.get('guardian_binding') or {}
assert x.get('dispatch_allowed') is True,x
assert b.get('all_tasks_bound') is True,b
assert b.get('blocked_task_count')==0,b
for task in x.get('tasks') or []:
    gb=task.get('guardian_binding') or {}
    assert gb.get('policy_contract_ref')=='role:__agent__',(task.get('id'),gb)
    assert gb.get('subject_role','').endswith('-agent'),(task.get('id'),gb)
print('COLLECTOR_KNOWLEDGE_BOOTSTRAP_GUARDIAN_BINDING=PASS')
PY

BOOTSTRAP_SCHEDULE="$WORK/bootstrap-schedule.json"
BOOTSTRAP_PREPARE="$WORK/bootstrap-prepare.json"
BOOTSTRAP_DISPATCH="$WORK/bootstrap-dispatch.json"

"${PC[@]}" schedule --project "$PROJECT" --graph "$BOOTSTRAP_GRAPH" > "$BOOTSTRAP_SCHEDULE"
BOOTSTRAP_PLAN="$(python3 - "$BOOTSTRAP_SCHEDULE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
echo "COLLECTOR_KNOWLEDGE_BOOTSTRAP_SCHEDULE=PASS"
echo "COLLECTOR_KNOWLEDGE_BOOTSTRAP_PLAN=$BOOTSTRAP_PLAN"

"${PC[@]}" prepare-run --project "$PROJECT" --plan "$BOOTSTRAP_PLAN" --graph "$BOOTSTRAP_GRAPH" > "$BOOTSTRAP_PREPARE"
python3 - "$BOOTSTRAP_PREPARE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('COLLECTOR_KNOWLEDGE_BOOTSTRAP_PREPARE=PASS')
PY

set +e
"${PC[@]}" dispatch --project "$PROJECT" --plan "$BOOTSTRAP_PLAN" --graph "$BOOTSTRAP_GRAPH" --execute > "$BOOTSTRAP_DISPATCH"
BOOTSTRAP_RC=$?
set -e
echo "COLLECTOR_KNOWLEDGE_BOOTSTRAP_DISPATCH_RC=$BOOTSTRAP_RC"

BOOTSTRAP_RUN_RECORD="$(python3 - "$BOOTSTRAP_DISPATCH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
print((x.get('details') or {}).get('RUN_RECORD') or '')
PY
)"
[ -n "$BOOTSTRAP_RUN_RECORD" ] || die bootstrap_run_record_missing
echo "COLLECTOR_KNOWLEDGE_BOOTSTRAP_RUN_RECORD=$BOOTSTRAP_RUN_RECORD"

python3 - "$BOOTSTRAP_RUN_RECORD" "$HEALTH" "$KNOWLEDGE_REV" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
run_record,health_path,revision=sys.argv[1:]
x=json.load(open(run_record,encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
by={t.get('task_id'):t for t in tasks}
for tid in ('collector-knowledge:pilot-install-v1','collector-knowledge:pilot-probe-v1'):
    t=by.get(tid) or {}
    if t.get('status')!='SUCCEEDED':
        raise SystemExit('COLLECTOR_KNOWLEDGE_BOOTSTRAP_TASK_NOT_SUCCEEDED:'+tid)
    rp=t.get('task_result')
    if not rp: raise SystemExit('COLLECTOR_KNOWLEDGE_TASK_RESULT_MISSING:'+tid)
    tr=json.load(open(rp,encoding='utf-8'))
    if tr.get('status')!='OK':
        raise SystemExit('COLLECTOR_KNOWLEDGE_TASK_RESULT_NOT_OK:'+tid+':'+str(tr.get('summary')))

probe=by['collector-knowledge:pilot-probe-v1']
pr=json.load(open(probe['task_result'],encoding='utf-8'))
assert pr.get('summary')=='COLLECTOR_KNOWLEDGE_PILOT_PROBE_OK',pr
evidence=pr.get('evidence') or []
details=(evidence[0].get('details') if evidence and isinstance(evidence[0],dict) else {}) or {}
assert details.get('production_runtime_unchanged') is True,details
assert details.get('lastwar_game_connection')=='NONE',details
assert details.get('lastwar_mutation') is False,details
assert details.get('token_persisted') is False,details

p=Path(health_path)
try:h=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
except Exception:h={}
if h.get('schema')!='chacha.dev/provider-health-snapshot/v1':
    h={'schema':'chacha.dev/provider-health-snapshot/v1','observed_at':'','providers':{}}
now=datetime.now(timezone.utc).isoformat()
h['observed_at']=now
h.setdefault('providers',{})['collector-knowledge-runtime']={
  'state':'HEALTHY',
  'source':'collector-knowledge-pilot-probe',
  'checked_at':now,
  'latency_ms':None,
  'reason':'COLLECTOR_KNOWLEDGE_PILOT_PROBE_OK',
  'details':{
    'revision':revision,
    'run_record':run_record,
    'task_result':probe['task_result'],
    'production_runtime_unchanged':True,
    'lastwar_game_connection':'NONE',
    'lastwar_mutation':False,
    'token_persisted':False
  }
}
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(h,indent=2)+'\n',encoding='utf-8')
print('COLLECTOR_KNOWLEDGE_RUNTIME_PROBE=PASS')
print('COLLECTOR_KNOWLEDGE_RUNTIME_HEALTH=HEALTHY')
PY

QUERY_GRAPH_RAW="$WORK/collector-knowledge-v1-query.unbound.task-graph.json"
QUERY_GRAPH="$PLAN_DIR/collector-knowledge-v1-query.task-graph.json"
python3 - "$QUERY_GRAPH_RAW" <<'PY'
import json,sys
from datetime import datetime,timezone
path=sys.argv[1]
g={
  "schema":"chacha.dev/task-graph/v1",
  "project":"wfgg-radar",
  "transition":"OPERATE->OPERATE",
  "generated_at":datetime.now(timezone.utc).isoformat(),
  "tasks":[{
    "id":"collector-knowledge:query-v1",
    "kind":"knowledge-query",
    "description":"Exercise the governed localhost query path after the verified runtime-health promotion.",
    "owner_role":"collector-intelligence-agent",
    "capabilities":["collector-knowledge-inspect"],
    "permission":"read",
    "depends_on":[],
    "outputs":[{"type":"artifact","id":"collector-knowledge-query-result"}],
    "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
    "blocking":True,
    "metadata":{"collector_knowledge":{"action":"query","q":"totalNum","limit":10}}
  }],
  "summary":{"task_count":1,"artifact_tasks":1,"gate_tasks":0,"approval_tasks":0,"blocking_tasks":1}
}
open(path,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY
python3 dev-hub/bin/task-contract-binder.py \
  --graph "$QUERY_GRAPH_RAW" \
  --agent-contracts "$EMPTY_AGENT_CONTRACTS" \
  --component-contracts "$EMPTY_COMPONENT_CONTRACTS" \
  --role-contracts dev-hub/config/guardian-role-contracts.v1.json \
  --output "$QUERY_GRAPH" > "$WORK/query-binding.txt"
python3 - "$QUERY_GRAPH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
b=x.get('guardian_binding') or {}
assert x.get('dispatch_allowed') is True,x
assert b.get('all_tasks_bound') is True,b
assert b.get('blocked_task_count')==0,b
for task in x.get('tasks') or []:
    gb=task.get('guardian_binding') or {}
    assert gb.get('policy_contract_ref')=='role:__agent__',(task.get('id'),gb)
print('COLLECTOR_KNOWLEDGE_QUERY_GUARDIAN_BINDING=PASS')
PY

QUERY_SCHEDULE="$WORK/query-schedule.json"
QUERY_PREPARE="$WORK/query-prepare.json"
QUERY_DISPATCH="$WORK/query-dispatch.json"
"${PC[@]}" schedule --project "$PROJECT" --graph "$QUERY_GRAPH" > "$QUERY_SCHEDULE"
QUERY_PLAN="$(python3 - "$QUERY_SCHEDULE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
echo "COLLECTOR_KNOWLEDGE_QUERY_SCHEDULE=PASS"
"${PC[@]}" prepare-run --project "$PROJECT" --plan "$QUERY_PLAN" --graph "$QUERY_GRAPH" > "$QUERY_PREPARE"
python3 - "$QUERY_PREPARE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('COLLECTOR_KNOWLEDGE_QUERY_PREPARE=PASS')
PY
set +e
"${PC[@]}" dispatch --project "$PROJECT" --plan "$QUERY_PLAN" --graph "$QUERY_GRAPH" --execute > "$QUERY_DISPATCH"
QUERY_RC=$?
set -e
echo "COLLECTOR_KNOWLEDGE_QUERY_DISPATCH_RC=$QUERY_RC"
QUERY_RUN_RECORD="$(python3 - "$QUERY_DISPATCH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
print((x.get('details') or {}).get('RUN_RECORD') or '')
PY
)"
[ -n "$QUERY_RUN_RECORD" ] || die query_run_record_missing
python3 - "$QUERY_RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
t=next((t for t in tasks if t.get('task_id')=='collector-knowledge:query-v1'),None) or {}
assert t.get('status')=='SUCCEEDED',t
tr=json.load(open(t['task_result'],encoding='utf-8'))
assert tr.get('status')=='OK',tr
assert tr.get('summary')=='COLLECTOR_KNOWLEDGE_QUERY_OK',tr
print('COLLECTOR_KNOWLEDGE_QUERY_PATH=PASS')
PY
echo "COLLECTOR_KNOWLEDGE_LASTWAR_GAME_CONNECTION=NONE"
echo "COLLECTOR_KNOWLEDGE_LASTWAR_MUTATION=NO"
echo "COLLECTOR_KNOWLEDGE_PRODUCTION_CONNECTOR_TOUCHED=NO"

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
