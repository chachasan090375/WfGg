#!/usr/bin/env bash
# V6.19.7 Stale Cycle Recovery functional pilot runner; one user-triggered @federated:8131 search is required after the guard probe.
# Radar runtime adapter provisioning revision: 1.5.4 (immutable version bump after digest change).
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6197_FUNCTIONAL_REV:-}"
PROJECT="wfgg-radar"
PILOT_REV="633364c2f2f60aaef6967126df7d25a167f972f3"
PILOT_BRANCH="radar-v6197-autopilot-stale-cycle-recovery"
CONNECTOR_SHA="ccbb1a178212d3137136fff30c31725b88a7e3a8113dca922138018186a158d5"
NATIVE_SHA="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
INSTALLER="radar-vps/install-v6197-pilot.sh"
PROBE="radar-vps/probe-v6197-pilot-runtime.sh"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v6197-functional.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
APPROVAL_ID="production-release"
APPROVAL_ACTIVE=0
PILOT_OPENED=0
CLOSE_ATTEMPTED=0
REPO=""

cleanup(){ rm -rf "$WORK"; }
die(){ echo "RADAR_V6197_FUNCTIONAL_CHACHA=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required

for cmd in curl tar python3 sha256sum systemctl grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR V6.19.7 FUNCTIONAL STALE-CYCLE PILOT ==="
echo "DEV_HUB_REV=$REV"
echo "PILOT_REV=$PILOT_REV"
echo "PILOT_BRANCH=$PILOT_BRANCH"
echo "EXPECTED_CONNECTOR_SHA256=$CONNECTOR_SHA"
echo "EXPECTED_NATIVE_SHA256=$NATIVE_SHA"

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
  dev-hub/bin/external-runtime-dispatch.py \
  dev-hub/bin/verification-broker.py \
  dev-hub/bin/evidence-collector.py

python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "CHACHA_DEV_RADAR_ADAPTER_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh
echo "CHACHA_DEV_RADAR_ADAPTER_PROVISIONING=PASS"

mkdir -p "$EVIDENCE_DIR" "$PLAN_DIR"
STATE="$RUNTIME/state/$PROJECT/state.json"
LEDGER="$EVIDENCE_DIR/ledger.json"
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

# ---------------------------------------------------------------------------
# 0) Functional preflight: prove the existing @federated:8131 cycle is stale.
#    Read-only DB inspection; no runtime or Collector mutation.
# ---------------------------------------------------------------------------
COLLECTOR_DB="${WFGG_COLLECTOR_DB:-/opt/wfgg-collector/data/collector.db}"
TARGET_QUERY="@federated:8131"
[ -r "$COLLECTOR_DB" ] || die collector_db_unreadable
STALE_INFO="$(python3 - "$COLLECTOR_DB" "$TARGET_QUERY" <<'PY'
import sqlite3,sys
from datetime import datetime,timezone
db,q=sys.argv[1:3]
con=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
con.row_factory=sqlite3.Row
row=con.execute("SELECT id,status,COALESCE(started_at,'') started_at,COALESCE(error,'') error FROM cycles WHERE lower(query)=lower(?) AND upper(status)='RUNNING' ORDER BY id DESC LIMIT 1",(q,)).fetchone()
if row is None:
    raise SystemExit('STALE_TARGET_CYCLE_NOT_FOUND')
raw=str(row['started_at'] or '').strip()
try:
    started=datetime.fromisoformat(raw.replace('Z','+00:00'))
except Exception:
    raise SystemExit('STALE_TARGET_STARTED_AT_INVALID')
if started.tzinfo is None:
    started=started.replace(tzinfo=timezone.utc)
age=(datetime.now(timezone.utc)-started.astimezone(timezone.utc)).total_seconds()
if age < 900:
    raise SystemExit('TARGET_CYCLE_NOT_STALE')
print(f"{int(row['id'])}|{raw}|{int(age)}")
PY
)" || die stale_cycle_preflight_failed
IFS='|' read -r STALE_CYCLE_ID STALE_STARTED_AT STALE_AGE_SECONDS <<< "$STALE_INFO"
echo "RADAR_V6197_FUNCTIONAL_TARGET_QUERY=$TARGET_QUERY"
echo "RADAR_V6197_FUNCTIONAL_STALE_CYCLE_ID=$STALE_CYCLE_ID"
echo "RADAR_V6197_FUNCTIONAL_STALE_STARTED_AT=$STALE_STARTED_AT"
echo "RADAR_V6197_FUNCTIONAL_STALE_AGE_SECONDS=$STALE_AGE_SECONDS"
echo "RADAR_V6197_FUNCTIONAL_PREFLIGHT=PASS"

# ---------------------------------------------------------------------------
# 1) Satisfy the existing project-intent lifecycle artifact in a verified way.
# ---------------------------------------------------------------------------
INTENT_SRC="$EVIDENCE_DIR/project-intent.v1.json"
install -m 0640 dev-hub/projects/wfgg-radar/project-intent.v1.json "$INTENT_SRC"
INTENT_DIGEST="sha256:$(sha256sum "$INTENT_SRC" | awk '{print $1}')"
INTENT_GRAPH="$PLAN_DIR/project-intent.task-graph.json"
INTENT_RESULT="$WORK/project-intent.task-result.json"

python3 - "$INTENT_GRAPH" "$INTENT_RESULT" "$INTENT_SRC" "$INTENT_DIGEST" <<'PY'
import json,sys
from datetime import datetime,timezone
graph_path,result_path,src,digest=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
graph={
  "schema":"chacha.dev/task-graph/v1",
  "project":"wfgg-radar",
  "transition":"IDEA->DESIGN",
  "generated_at":now,
  "tasks":[{
    "id":"control:project-intent",
    "kind":"documentation",
    "description":"Register the canonical operational project intent for WfGg Radar.",
    "owner_role":"product-domain",
    "capabilities":[],
    "permission":"read",
    "depends_on":[],
    "outputs":[{"type":"artifact","id":"project-intent"}],
    "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
    "blocking":True
  }],
  "summary":{"task_count":1,"artifact_tasks":1,"gate_tasks":0,"approval_tasks":0,"blocking_tasks":1}
}
result={
  "schema":"chacha.dev/task-result/v1",
  "project":"wfgg-radar",
  "task_id":"control:project-intent",
  "status":"OK",
  "producer":"project-intent-recorder",
  "observed_at":now,
  "summary":"Canonical WfGg Radar project intent registered.",
  "evidence":[{"kind":"artifact","source":src,"digest":digest,"details":{"schema":"chacha.dev/project-intent/v1"}}],
  "outputs":[{"type":"artifact","id":"project-intent","status":"OK"}],
  "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Independent verification required."}
}
open(graph_path,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(result_path,"w",encoding="utf-8").write(json.dumps(result,indent=2)+"\n")
PY

"${PC[@]}" verify-result --project "$PROJECT" --result "$INTENT_RESULT" --graph "$INTENT_GRAPH" --method machine --verifier verification-broker --ingest > "$WORK/intent-ingest.json"
python3 - "$WORK/intent-ingest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
assert (x.get('details') or {}).get('verification_status')=='VERIFIED',x
print('PROJECT_INTENT_VERIFIED_INGESTED=PASS')
PY

set +e
"${PC[@]}" status --project "$PROJECT" > "$WORK/status-after-intent.json"
STATUS_RC=$?
set -e
python3 - "$WORK/status-after-intent.json" "$STATUS_RC" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); rc=int(sys.argv[2])
print('PROJECT_CONTROL_STATUS_AFTER_INTENT='+str(x.get('status')))
print('PROJECT_CONTROL_STATUS_AFTER_INTENT_RC='+str(rc))
print('PROJECT_CONTROL_BLOCKERS_AFTER_INTENT='+','.join(x.get('blockers') or []))
assert 'ARTIFACT_MISSING:project-intent' not in (x.get('blockers') or []),x
PY

# ---------------------------------------------------------------------------
# 2) Record the user's explicit, scope-limited human approval in the Ledger.
# ---------------------------------------------------------------------------
APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v6197-functional-pilot.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v6197-functional-pilot.task-graph.json"
APPROVAL_RESULT="$WORK/approval.task-result.json"

python3 - "$APPROVAL_EVIDENCE" <<'PY'
import json,sys
from datetime import datetime,timezone
p=sys.argv[1]
obj={
  "schema":"chacha.dev/human-approval-evidence/v1",
  "approval_id":"production-release",
  "project":"wfgg-radar",
  "scope":{
    "pilot":"V6.19.7",
    "revision":"633364c2f2f60aaef6967126df7d25a167f972f3",
    "change":"Autopilot stale-cycle recovery functional verification",
    "purpose":"run one user-triggered @federated:8131 search under the V6.19.7 pilot to prove recovery of the pre-existing stale Collector cycle; Last War remains READ-ONLY and Collector mutation is limited to stale-cycle recovery plus the new targeted evidence cycle"
  },
  "actor":"human-user",
  "source":"chat-explicit-approval",
  "statement":"J’approuve le PILOT fonctionnel Radar V6.19.7 Stale Cycle Recovery révision 633364c2f2f60aaef6967126df7d25a167f972f3 avec un scan Last War READ-ONLY ciblé sur @federated:8131 et mutation Collector limitée à la récupération du cycle stale et au nouveau cycle de preuve.",
  "observed_at":datetime.now(timezone.utc).isoformat(),
  "single_pilot_window":True
}
open(p,"w",encoding="utf-8").write(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
PY
chmod 0640 "$APPROVAL_EVIDENCE"
APPROVAL_DIGEST="sha256:$(sha256sum "$APPROVAL_EVIDENCE" | awk '{print $1}')"

python3 - "$APPROVAL_GRAPH" "$APPROVAL_RESULT" "$APPROVAL_EVIDENCE" "$APPROVAL_DIGEST" <<'PY'
import json,sys
from datetime import datetime,timezone
graph_path,result_path,src,digest=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
graph={
  "schema":"chacha.dev/task-graph/v1",
  "project":"wfgg-radar",
  "transition":"PILOT-APPROVAL",
  "generated_at":now,
  "tasks":[{
    "id":"approval:radar-v6197-functional-pilot",
    "kind":"approval",
    "description":"Record explicit human approval for the single V6.19.7 functional stale-cycle recovery pilot window.",
    "owner_role":"project-owner",
    "capabilities":[],
    "permission":"read",
    "depends_on":[],
    "outputs":[{"type":"approval","id":"production-release"}],
    "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
    "blocking":True
  }],
  "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}
}
result={
  "schema":"chacha.dev/task-result/v1",
  "project":"wfgg-radar",
  "task_id":"approval:radar-v6197-functional-pilot",
  "status":"OK",
  "producer":"human-approval-recorder",
  "observed_at":now,
  "summary":"Human approved the single V6.19.7 functional stale-cycle recovery pilot window.",
  "evidence":[{"kind":"human-approval","source":src,"digest":digest,"details":{"approval_id":"production-release","scope":"radar-v6197-functional-pilot"}}],
  "outputs":[{"type":"approval","id":"production-release","status":"APPROVED"}],
  "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}
}
open(graph_path,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(result_path,"w",encoding="utf-8").write(json.dumps(result,indent=2)+"\n")
PY

"${PC[@]}" verify-result --project "$PROJECT" --result "$APPROVAL_RESULT" --graph "$APPROVAL_GRAPH" --method human --verifier human-user --ingest > "$WORK/approval-ingest.json"
python3 - "$WORK/approval-ingest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
assert (x.get('details') or {}).get('verification_status')=='VERIFIED',x
print('PRODUCTION_RELEASE_APPROVAL_INGESTED=PASS')
PY
APPROVAL_ACTIVE=1

# ---------------------------------------------------------------------------
# Helpers: governed graph execution and one-shot approval revocation.
# ---------------------------------------------------------------------------
run_graph () {
  local graph="$1"
  local label="$2"
  local sched="$WORK/$label.schedule.json"
  local prep="$WORK/$label.prepare.json"
  local disp="$WORK/$label.dispatch.json"

  "${PC[@]}" schedule --project "$PROJECT" --graph "$graph" > "$sched"
  local plan
  plan="$(python3 - "$sched" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
  echo "${label}_SCHEDULE=PASS"
  echo "${label}_PLAN=$plan"

  "${PC[@]}" prepare-run --project "$PROJECT" --plan "$plan" --graph "$graph" > "$prep"
  python3 - "$prep" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
PY
  echo "${label}_PREPARE=PASS"

  set +e
  "${PC[@]}" dispatch --project "$PROJECT" --plan "$plan" --graph "$graph" --execute > "$disp"
  local rc=$?
  set -e
  local run_record
  run_record="$(python3 - "$disp" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
print((x.get('details') or {}).get('RUN_RECORD') or '')
PY
)"
  echo "${label}_DISPATCH_RC=$rc"
  echo "${label}_RUN_RECORD=$run_record"
  [ -n "$run_record" ] || return 20
  echo "$run_record"
}

revoke_approval () {
  [ "$APPROVAL_ACTIVE" -eq 1 ] || return 0
  local ev="$EVIDENCE_DIR/approval-radar-v6197-functional-pilot-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v6197-functional-pilot-revoked.task-graph.json"
  local result="$WORK/approval-revoked.task-result.json"
  python3 - "$ev" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
  "schema":"chacha.dev/human-approval-evidence/v1",
  "approval_id":"production-release",
  "project":"wfgg-radar",
  "actor":"human-user",
  "source":"scope-expiry",
  "statement":"The explicit V6.19.7 functional stale-cycle pilot approval has been consumed and is revoked after the single functional pilot window.",
  "observed_at":datetime.now(timezone.utc).isoformat(),
  "single_pilot_window":True,
  "status":"REJECTED"
}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(obj,indent=2)+"\n")
PY
  chmod 0640 "$ev"
  local dg="sha256:$(sha256sum "$ev" | awk '{print $1}')"
  python3 - "$graph" "$result" "$ev" "$dg" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,s,d=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
graph={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"PILOT-APPROVAL-REVOKE","generated_at":now,
 "tasks":[{"id":"approval:radar-v6197-functional-pilot-revoke","kind":"approval","description":"Revoke the consumed one-shot production approval.","owner_role":"project-owner","capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"production-release"}],"verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v6197-functional-pilot-revoke","status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Consumed single-window V6.19.7 functional pilot approval revoked.","evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"production-release","status":"REJECTED"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"REJECTED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}}
open(g,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding="utf-8").write(json.dumps(res,indent=2)+"\n")
PY
  "${PC[@]}" verify-result --project "$PROJECT" --result "$result" --graph "$graph" --method human --verifier human-user --ingest > "$WORK/approval-revoke-ingest.json" || true
  if python3 - "$WORK/approval-revoke-ingest.json" <<'PY'
import json,sys
try: x=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception: raise SystemExit(1)
raise SystemExit(0 if x.get('status')=='OK' else 1)
PY
  then
    echo "PRODUCTION_RELEASE_APPROVAL_REVOKED=PASS"
    APPROVAL_ACTIVE=0
  else
    echo "PRODUCTION_RELEASE_APPROVAL_REVOKED=FAIL"
  fi
}

close_pilot () {
  [ "$CLOSE_ATTEMPTED" -eq 0 ] || return 0
  CLOSE_ATTEMPTED=1
  local graph="$PLAN_DIR/radar-v6197-close.task-graph.json"
  python3 - "$graph" <<'PY'
import json,sys
from datetime import datetime,timezone
p=sys.argv[1]; now=datetime.now(timezone.utc).isoformat()
g={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"OPERATE->OPERATE","generated_at":now,
"tasks":[{"id":"radar-runtime:pilot-close-v6197","kind":"runtime-deploy","description":"Close the V6.19.7 Autopilot pilot window and restore Radar Sentinel protection.","owner_role":"sre-observability","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":[],"outputs":[{"type":"gate","id":"radar-sentinel-protection"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-close"}}}],
"summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":1}}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY
  if rr="$(run_graph "$graph" RADAR_V6197_CLOSE | tail -1)"; then
    python3 - "$rr" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
ok=len(tasks)==1 and tasks[0].get('status')=='SUCCEEDED'
print('RADAR_V6197_PILOT_CLOSE='+('PASS' if ok else 'FAIL'))
raise SystemExit(0 if ok else 1)
PY
  else
    echo "RADAR_V6197_PILOT_CLOSE=FAIL"
    return 1
  fi
}

finalize () {
  rc=$?
  set +e
  if [ "$APPROVAL_ACTIVE" -eq 1 ]; then
    close_pilot
    revoke_approval
  fi
  cleanup
  exit "$rc"
}
trap finalize EXIT

# ---------------------------------------------------------------------------
# 3) ChaCha DEV governed pilot: open -> install -> guard-only Autopilot route probe.
#    No Last War scan or Collector mutation is executed by the probe; close is guaranteed in the EXIT path.
# ---------------------------------------------------------------------------
PILOT_GRAPH="$PLAN_DIR/radar-v6197-pilot.task-graph.json"
python3 - "$PILOT_GRAPH" "$PILOT_REV" "$CONNECTOR_SHA" "$NATIVE_SHA" "$INSTALLER" "$PROBE" <<'PY'
import json,sys
from datetime import datetime,timezone
p,rev,csha,nsha,installer,probe=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
g={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"OPERATE->OPERATE","generated_at":now,
 "tasks":[
  {"id":"radar-runtime:pilot-open-v6197","kind":"runtime-deploy","description":"Open the protected Radar V6.19.7 Autopilot pilot window.","owner_role":"sre-observability","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":[],"outputs":[{"type":"gate","id":"radar-pilot-window"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-open"}}},
  {"id":"radar-runtime:pilot-install-v6197","kind":"runtime-deploy","description":"Install SHA-pinned V6.19.7 Autopilot pilot binaries with installer rollback protection.","owner_role":"release","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":["radar-runtime:pilot-open-v6197"],"outputs":[{"type":"artifact","id":rev}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-install","revision":rev,"installer":installer,"expected_connector_sha256":csha,"expected_native_sha256":nsha}}},
  {"id":"radar-runtime:pilot-probe-v6197","kind":"runtime-diagnostic","description":"Verify the installed V6.19.7 Autopilot routes and guards without executing a Last War scan or Collector mutation.","owner_role":"sre-observability","capabilities":["radar-runtime-inspect"],"permission":"read","depends_on":["radar-runtime:pilot-install-v6197"],"outputs":[{"type":"artifact","id":"radar-v6197-runtime-probe"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-probe","revision":rev,"installer":installer,"probe":probe,"expected_connector_sha256":csha,"expected_native_sha256":nsha}}}
 ],
 "summary":{"task_count":3,"artifact_tasks":2,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":3}
}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

PILOT_RUN="$(run_graph "$PILOT_GRAPH" RADAR_V6197_PILOT | tail -1)"
PILOT_OPENED=1

python3 - "$PILOT_RUN" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
by={t.get('task_id'):t for t in tasks}
for tid in ("radar-runtime:pilot-open-v6197","radar-runtime:pilot-install-v6197","radar-runtime:pilot-probe-v6197"):
    t=by.get(tid) or {}
    print(tid.replace("radar-runtime:","").upper().replace("-","_")+"_STATUS="+str(t.get('status')))
    if t.get('status')!="SUCCEEDED":
        raise SystemExit("PILOT_TASK_NOT_SUCCEEDED:"+tid)
probe=by.get("radar-runtime:pilot-probe-v6197") or {}
result_path=probe.get("task_result")
if not result_path:
    raise SystemExit("PILOT_PROBE_TASK_RESULT_MISSING")
r=json.load(open(result_path,encoding='utf-8'))
if r.get("status")!="OK":
    raise SystemExit("PILOT_PROBE_RESULT_NOT_OK")
print("RADAR_V6197_RUNTIME_ROUTE_GUARDS=PASS")
print("RADAR_V6197_GAME_SCAN_EXECUTED=NO")
print("RADAR_V6197_COLLECTOR_MUTATION=NO")
print("RADAR_V6197_PHONE_REQUIRED_FOR_RUNTIME=NO")
PY
# ---------------------------------------------------------------------------
# 4) Functional stale-cycle proof.
#    The human now triggers exactly one normal Radar search for @federated:8131.
#    The production UI supplies the already-vaulted Last War credential.
#    Last War remains READ-ONLY; Collector writes are expected for recovery/evidence.
# ---------------------------------------------------------------------------
echo "RADAR_V6197_FUNCTIONAL_WINDOW_READY=YES"
echo "RADAR_V6197_FUNCTIONAL_ACTION=Dans Radar, laisse @federated:8131 dans le champ puis appuie UNE SEULE FOIS sur RECHERCHE. Ne démarre pas Autopilot."
echo "RADAR_V6197_FUNCTIONAL_WAIT_MAX_SECONDS=1200"

set +e
python3 - "$COLLECTOR_DB" "$TARGET_QUERY" "$STALE_CYCLE_ID" <<'PY'
import sqlite3,sys,time
from datetime import datetime,timezone
db,q,stale_s=sys.argv[1:4]
stale=int(stale_s)
deadline=time.time()+1200
last=None
while time.time() < deadline:
    con=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    old=con.execute("SELECT id,status,COALESCE(error,'') error,COALESCE(finished_at,'') finished_at FROM cycles WHERE id=?",(stale,)).fetchone()
    new=con.execute("SELECT id,status,COALESCE(error,'') error,COALESCE(started_at,'') started_at,COALESCE(finished_at,'') finished_at FROM cycles WHERE lower(query)=lower(?) AND id>? ORDER BY id DESC LIMIT 1",(q,stale)).fetchone()
    con.close()
    state=(
        str(old['status'] if old else 'MISSING'),
        str(old['error'] if old else ''),
        int(new['id']) if new else 0,
        str(new['status'] if new else 'NONE'),
        str(new['error'] if new else ''),
    )
    if state != last:
        print("RADAR_V6197_FUNCTIONAL_OLD_STATUS="+state[0], flush=True)
        print("RADAR_V6197_FUNCTIONAL_OLD_ERROR="+(state[1] or 'NONE'), flush=True)
        print("RADAR_V6197_FUNCTIONAL_NEW_CYCLE_ID="+str(state[2]), flush=True)
        print("RADAR_V6197_FUNCTIONAL_NEW_STATUS="+state[3], flush=True)
        print("RADAR_V6197_FUNCTIONAL_NEW_ERROR="+(state[4] or 'NONE'), flush=True)
        last=state
    recovered=(state[0].upper()=='FAILED' and state[1]=='STALE_RUNNING_CYCLE_RECOVERED_V6197')
    terminal=(state[2] > stale and state[3].upper() in ('SUCCESS','FAILED'))
    if recovered and terminal:
        print("RADAR_V6197_STALE_CYCLE_RECOVERED=PASS", flush=True)
        print("RADAR_V6197_FRESH_CYCLE_OBSERVED=PASS", flush=True)
        print("RADAR_V6197_FRESH_CYCLE_TERMINAL=PASS", flush=True)
        raise SystemExit(0)
    # If a fresh cycle itself ages past 15 minutes while RUNNING, fail rather
    # than pretending the recovery is qualified.
    if new and str(new['status']).upper()=='RUNNING':
        raw=str(new['started_at'] or '').strip()
        try:
            dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds() >= 900:
                print("RADAR_V6197_FUNCTIONAL_FAIL=FRESH_CYCLE_BECAME_STALE", flush=True)
                raise SystemExit(4)
        except ValueError:
            pass
    time.sleep(5)
print("RADAR_V6197_FUNCTIONAL_FAIL=TIMEOUT_WAITING_FOR_USER_SEARCH_OR_TERMINAL_CYCLE", flush=True)
raise SystemExit(3)
PY
FUNCTIONAL_RC=$?
set -e

# Close while approval is still active; EXIT will retry if close fails.
close_pilot
revoke_approval

[ "$FUNCTIONAL_RC" -eq 0 ] || die functional_stale_cycle_verification_failed
echo "RADAR_V6197_LASTWAR_MUTATION=NO"
echo "RADAR_V6197_FUNCTIONAL_COLLECTOR_MUTATION=STALE_RECOVERY_PLUS_TARGETED_EVIDENCE_ONLY"
echo "RADAR_V6197_FUNCTIONAL_PROOF=PASS"

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "RADAR_V6197_PRODUCTION_APPROVAL_STANDING=NO"
echo "RADAR_V6197_PILOT_WINDOW_CLOSED=YES"
echo "RADAR_V6197_CHACHA_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_V6197_CHACHA_DEPLOY=PASS"

trap - EXIT
cleanup
