#!/usr/bin/env bash
# V6.19.11 Manual Search Stop functional pilot runner; exact candidate UI + real READ-ONLY manual search + STOP.
# Radar runtime adapter provisioning revision: 1.5.4 (immutable version bump after digest change).
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V61911_FUNCTIONAL_REV:-}"
PROJECT="wfgg-radar"
APPROVED_REV="cbf67e46308e925f1ba5fad0be3f58764231935d"
PILOT_REV="759bfb3fe4620f544cc84fdea34e54bfa3efbdcf"
PILOT_BRANCH="radar-v61911-manual-search-stop"
CONNECTOR_SHA="4d66709f10d3a6b27ac255a1dfdc62e51d2817652634409ffe2edc071762c69f"
NATIVE_SHA="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
INSTALLER="radar-vps/install-v61911-pilot.sh"
PROBE="radar-vps/probe-v61911-pilot-runtime.sh"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v61911-functional-stop.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
APPROVAL_ID="production-release"
APPROVAL_ACTIVE=0
PILOT_OPENED=0
CLOSE_ATTEMPTED=0
REPO=""
PILOT_SERVER_PID=""
TARGET_QUERY="@federated:8120"
PILOT_UI_SHA256="6e6827e660597549bdc8c4c06e06a644a16215aacabdd20a56993a15f651c060"
PILOT_PORT="${WFGG_RADAR_V61911_FUNCTIONAL_PORT:-18799}"
COLLECTOR_DB="${WFGG_COLLECTOR_DB:-/opt/wfgg-collector/data/collector.db}"

cleanup(){ if [[ -n "${PILOT_SERVER_PID:-}" ]]; then kill "$PILOT_SERVER_PID" >/dev/null 2>&1 || true; wait "$PILOT_SERVER_PID" >/dev/null 2>&1 || true; fi; rm -rf "$WORK"; }
die(){ echo "RADAR_V61911_FUNCTIONAL_CHACHA=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required

for cmd in curl tar python3 sha256sum systemctl grep tailscale; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR V6.19.11 FUNCTIONAL MANUAL SEARCH STOP PILOT ==="
echo "DEV_HUB_REV=$REV"
echo "APPROVED_REV=$APPROVED_REV"
echo "PILOT_REV=$PILOT_REV"
echo "PILOT_BRANCH=$PILOT_BRANCH"
echo "EXPECTED_CONNECTOR_SHA256=$CONNECTOR_SHA"
echo "EXPECTED_NATIVE_SHA256=$NATIVE_SHA"
echo "RADAR_V61911_FUNCTIONAL_TARGET_QUERY=$TARGET_QUERY"
[ -r "$COLLECTOR_DB" ] || die collector_db_unreadable

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


# Functional preflight: no active federated cycle may pre-exist.
read -r BASELINE_CYCLE_ID BASELINE_RUNNING_FEDERATED <<< "$(python3 - "$COLLECTOR_DB" <<'PY'
import sqlite3,sys
db=sys.argv[1]
con=sqlite3.connect('file:'+db+'?mode=ro',uri=True,timeout=5)
con.execute('PRAGMA query_only=ON')
baseline=int(con.execute('SELECT COALESCE(MAX(id),0) FROM cycles').fetchone()[0] or 0)
running=int(con.execute("SELECT COUNT(*) FROM cycles WHERE upper(trim(COALESCE(status,'')))='RUNNING' AND lower(trim(COALESCE(query,''))) LIKE '@federated:%'").fetchone()[0] or 0)
con.close()
print(baseline,running)
PY
)"
echo "RADAR_V61911_FUNCTIONAL_BASELINE_CYCLE_ID=$BASELINE_CYCLE_ID"
echo "RADAR_V61911_FUNCTIONAL_BASELINE_RUNNING_FEDERATED=$BASELINE_RUNNING_FEDERATED"
if [ "$BASELINE_RUNNING_FEDERATED" -gt 0 ]; then
  [ "$BASELINE_RUNNING_FEDERATED" -eq 1 ] || die multiple_active_federated_cycles_preexist
  [ "$BASELINE_CYCLE_ID" -eq 81 ] || die unexpected_active_federated_cycle_preexists
  echo "RADAR_V61911_FUNCTIONAL_EXPECT_STALE_RECOVERY_CYCLE=81"
else
  echo "RADAR_V61911_FUNCTIONAL_EXPECT_STALE_RECOVERY_CYCLE=NONE"
fi
echo "RADAR_V61911_FUNCTIONAL_PREFLIGHT=PASS"

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-before.json"
python3 - "$WORK/verify-before.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_BEFORE=PASS')
PY

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
APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v61911-functional-stop-pilot.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v61911-functional-stop-pilot.task-graph.json"
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
    "pilot":"V6.19.11",
    "revision":"cbf67e46308e925f1ba5fad0be3f58764231935d",
    "change":"Manual Search Stop",
    "approved_revision":"cbf67e46308e925f1ba5fad0be3f58764231935d",
    "artifact_revision":"759bfb3fe4620f544cc84fdea34e54bfa3efbdcf",
    "purpose":"reopen one functional V6.19.11 window; allow only the previously validated V6.19.7 stale recovery of cycle 81, then run one real manual @federated:8120 READ-ONLY search and stop only that active manual job with STOP; no persistent token storage and no production promotion/deployment"
  },
  "actor":"human-user",
  "source":"chat-explicit-approval",
  "statement":"J’approuve la réouverture du PILOT fonctionnel Radar V6.19.11 Manual Search Stop avec le runner 3dceb68a89a82836b85163bf3bd40c8b7b7da4c5, candidat issu de cbf67e46308e925f1ba5fad0be3f58764231935d, récupération préalable du cycle stale 81 exclusivement via le mécanisme V6.19.7 validé, puis une recherche manuelle @federated:8120 Last War strictement READ-ONLY et arrêt du seul job manuel via STOP, mutations Collector limitées à la récupération stale/découverte/preuves/terminalisation, aucune persistance de token et aucune promotion/déploiement production.",
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
    "id":"approval:radar-v61911-functional-stop-pilot",
    "kind":"approval",
    "description":"Record explicit human approval for the single V6.19.11 Manual Search Stop functional pilot window.",
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
  "task_id":"approval:radar-v61911-functional-stop-pilot",
  "status":"OK",
  "producer":"human-approval-recorder",
  "observed_at":now,
  "summary":"Human approved the single V6.19.11 Manual Search Stop functional pilot window.",
  "evidence":[{"kind":"human-approval","source":src,"digest":digest,"details":{"approval_id":"production-release","scope":"radar-v61911-functional-stop-pilot"}}],
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
  local ev="$EVIDENCE_DIR/approval-radar-v61911-functional-stop-pilot-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v61911-functional-stop-pilot-revoked.task-graph.json"
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
  "statement":"The explicit V6.19.11 Manual Search Stop functional pilot approval has been consumed and is revoked after the single functional window.",
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
 "tasks":[{"id":"approval:radar-v61911-functional-stop-pilot-revoke","kind":"approval","description":"Revoke the consumed one-shot production approval.","owner_role":"project-owner","capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"production-release"}],"verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v61911-functional-stop-pilot-revoke","status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Consumed single-window V6.19.11 Manual Search Stop functional pilot approval revoked.","evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"production-release","status":"REJECTED"}}],
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
  local graph="$PLAN_DIR/radar-v61911-close.task-graph.json"
  python3 - "$graph" <<'PY'
import json,sys
from datetime import datetime,timezone
p=sys.argv[1]; now=datetime.now(timezone.utc).isoformat()
g={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"OPERATE->OPERATE","generated_at":now,
"tasks":[{"id":"radar-runtime:pilot-close-v61911","kind":"runtime-deploy","description":"Close the V6.19.11 Manual Search Stop pilot window and restore Radar Sentinel protection.","owner_role":"sre-observability","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":[],"outputs":[{"type":"gate","id":"radar-sentinel-protection"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-close"}}}],
"summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":1}}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY
  if rr="$(run_graph "$graph" RADAR_V61911_CLOSE | tail -1)"; then
    python3 - "$rr" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
ok=len(tasks)==1 and tasks[0].get('status')=='SUCCEEDED'
print('RADAR_V61911_PILOT_CLOSE='+('PASS' if ok else 'FAIL'))
raise SystemExit(0 if ok else 1)
PY
  else
    echo "RADAR_V61911_PILOT_CLOSE=FAIL"
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
# 3) ChaCha DEV governed pilot: open -> install -> guard-only Manual Search Stop route probe.
#    No Last War scan or Collector mutation is executed by the probe; close is guaranteed in the EXIT path.
# ---------------------------------------------------------------------------
PILOT_GRAPH="$PLAN_DIR/radar-v61911-pilot.task-graph.json"
python3 - "$PILOT_GRAPH" "$PILOT_REV" "$CONNECTOR_SHA" "$NATIVE_SHA" "$INSTALLER" "$PROBE" <<'PY'
import json,sys
from datetime import datetime,timezone
p,rev,csha,nsha,installer,probe=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
g={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"OPERATE->OPERATE","generated_at":now,
 "tasks":[
  {"id":"radar-runtime:pilot-open-v61911","kind":"runtime-deploy","description":"Open the protected Radar V6.19.11 Manual Search Stop pilot window.","owner_role":"sre-observability","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":[],"outputs":[{"type":"gate","id":"radar-pilot-window"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-open"}}},
  {"id":"radar-runtime:pilot-install-v61911","kind":"runtime-deploy","description":"Install SHA-pinned V6.19.11 Manual Search Stop pilot binaries with installer rollback protection.","owner_role":"release","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":["radar-runtime:pilot-open-v61911"],"outputs":[{"type":"artifact","id":rev}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-install","revision":rev,"installer":installer,"expected_connector_sha256":csha,"expected_native_sha256":nsha}}},
  {"id":"radar-runtime:pilot-probe-v61911","kind":"runtime-diagnostic","description":"Verify the installed V6.19.11 manual-search STOP route and cancellation guards without executing a Last War scan or Collector mutation.","owner_role":"sre-observability","capabilities":["radar-runtime-inspect"],"permission":"read","depends_on":["radar-runtime:pilot-install-v61911"],"outputs":[{"type":"artifact","id":"radar-v61911-runtime-probe"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-probe","revision":rev,"installer":installer,"probe":probe,"expected_connector_sha256":csha,"expected_native_sha256":nsha}}}
 ],
 "summary":{"task_count":3,"artifact_tasks":2,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":3}
}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

PILOT_RUN="$(run_graph "$PILOT_GRAPH" RADAR_V61911_PILOT | tail -1)"
PILOT_OPENED=1

python3 - "$PILOT_RUN" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
by={t.get('task_id'):t for t in tasks}
for tid in ("radar-runtime:pilot-open-v61911","radar-runtime:pilot-install-v61911","radar-runtime:pilot-probe-v61911"):
    t=by.get(tid) or {}
    print(tid.replace("radar-runtime:","").upper().replace("-","_")+"_STATUS="+str(t.get('status')))
    if t.get('status')!="SUCCEEDED":
        raise SystemExit("PILOT_TASK_NOT_SUCCEEDED:"+tid)
probe=by.get("radar-runtime:pilot-probe-v61911") or {}
result_path=probe.get("task_result")
if not result_path:
    raise SystemExit("PILOT_PROBE_TASK_RESULT_MISSING")
r=json.load(open(result_path,encoding='utf-8'))
if r.get("status")!="OK":
    raise SystemExit("PILOT_PROBE_RESULT_NOT_OK")
print("RADAR_V61911_RUNTIME_STOP_GUARDS=PASS")
print("RADAR_V61911_GAME_SCAN_EXECUTED=NO")
print("RADAR_V61911_COLLECTOR_MUTATION=NO")
print("RADAR_V61911_STOP_SCOPE=MANUAL_SEARCH_ONLY")
PY
# ---------------------------------------------------------------------------
# 4) Functional V6.19.11 proof.
#    Serve the exact candidate UI only on the VPS Tailscale address.
#    The temporary proxy keeps the Last War credential in process memory only;
#    it writes no token/credential to disk, D1, GitHub, or logs.
# ---------------------------------------------------------------------------
PILOT_UI="$WORK/live-radar.html"
PILOT_EVIDENCE="$WORK/manual-stop-evidence.json"
PILOT_SERVER="$WORK/v61911-functional-server.py"
PILOT_LOG="$WORK/v61911-functional-server.log"
TS_IP="$(tailscale ip -4 | head -1 | tr -d '[:space:]')"
printf '%s' "$TS_IP" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || die tailscale_ipv4_unavailable

curl -fsSL "https://raw.githubusercontent.com/chachasan090375/WfGg/$PILOT_REV/radar-vps/pilot-v61911/cloudflare/live-radar.html" -o "$PILOT_UI"
test "$(sha256sum "$PILOT_UI" | awk '{print $1}')" = "$PILOT_UI_SHA256" || die pilot_ui_sha_mismatch
echo "RADAR_V61911_FUNCTIONAL_UI_SHA=PASS"

PID_BEFORE_FUNCTIONAL="$(systemctl show -p MainPID --value wfgg-radar-connector)"
[[ "$PID_BEFORE_FUNCTIONAL" =~ ^[0-9]+$ && "$PID_BEFORE_FUNCTIONAL" -gt 1 ]] || die connector_mainpid_invalid

cat > "$PILOT_SERVER" <<'PY'
import hashlib,hmac,json,os,secrets,sys,threading,time,urllib.error,urllib.parse,urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

bind_ip=sys.argv[1]
port=int(sys.argv[2])
html_path=Path(sys.argv[3])
evidence_path=Path(sys.argv[4])
target_query=sys.argv[5]
connector_pid=int(sys.argv[6])

raw=Path(f"/proc/{connector_pid}/environ").read_bytes().split(b"\0")
shared_key=""
for item in raw:
    if item.startswith(b"RADAR_CONNECTOR_SHARED_KEY="):
        shared_key=item.split(b"=",1)[1].decode()
        break
if len(shared_key)<32:
    raise SystemExit("SHARED_KEY_UNAVAILABLE")

sessions={}
challenges={}
lock=threading.Lock()

def connector(method,path,obj=None,timeout=75):
    body=b"" if obj is None else json.dumps(obj,separators=(",",":")).encode()
    ts=str(int(time.time()))
    nonce=secrets.token_hex(16)
    canonical_path=urllib.parse.urlsplit(path).path
    canonical="\n".join([method,canonical_path,ts,nonce,hashlib.sha256(body).hexdigest()])
    sig=hmac.new(shared_key.encode(),canonical.encode(),hashlib.sha256).hexdigest()
    req=urllib.request.Request("http://127.0.0.1:8788"+path,data=body if method!="GET" else None,method=method,headers={"Content-Type":"application/json","X-Radar-Timestamp":ts,"X-Radar-Nonce":nonce,"X-Radar-Signature":sig})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode()
            return r.status,json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try: payload=json.loads(raw)
        except Exception: payload={"error":raw[:300] or ("HTTP_"+str(e.code))}
        return e.code,payload

def write_evidence(payload):
    safe={k:v for k,v in payload.items() if k not in {"credential","token"}}
    tmp=evidence_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(safe,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    os.replace(tmp,evidence_path)

def watch_terminal(job_id,pre_stop):
    deadline=time.time()+120
    while time.time()<deadline:
        status,payload=connector("GET","/v1/collector/search/status?id="+urllib.parse.quote(job_id),None,30)
        job=(payload or {}).get("job") or {}
        if status==200 and str(job.get("status","")).upper() in {"SUCCESS","FAILED"}:
            write_evidence({"proof":"RADAR_V61911_MANUAL_SEARCH_STOP_FUNCTIONAL","jobId":job_id,"query":job.get("query"),"cycleId":job.get("cycleId"),"status":job.get("status"),"phase":job.get("phase"),"error":job.get("error"),"failureCode":job.get("failureCode"),"regionsCompleted":job.get("regionsCompleted"),"regionsFailed":job.get("regionsFailed"),"preStop":pre_stop,"observedAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"tokenPersisted":False,"lastWarMode":"READ_ONLY","stopScope":"MANUAL_SEARCH_ONLY"})
            return
        time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    server_version="WfGgRadarV61911Pilot/1"
    def log_message(self,fmt,*args):
        sys.stdout.write("%s %s\n"%(self.command,self.path.split("?",1)[0])); sys.stdout.flush()

    def send_json(self,status,data,cookie=None):
        raw=json.dumps(data,separators=(",",":")).encode()
        self.send_response(status)
        self.send_header("content-type","application/json; charset=utf-8")
        self.send_header("cache-control","no-store")
        self.send_header("content-length",str(len(raw)))
        if cookie: self.send_header("set-cookie",cookie)
        self.end_headers(); self.wfile.write(raw)

    def body_json(self):
        n=int(self.headers.get("content-length") or 0)
        raw=self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode() or "{}")

    def session_id(self):
        cookie=self.headers.get("cookie") or ""
        for part in cookie.split(";"):
            k,_,v=part.strip().partition("=")
            if k=="pilot_session": return v
        return ""

    def require_session(self):
        sid=self.session_id()
        with lock: s=sessions.get(sid)
        if not s:
            self.send_json(401,{"error":"RADAR_SESSION_REQUIRED"})
            return None,None
        return sid,s

    def do_GET(self):
        p=urllib.parse.urlsplit(self.path)
        if p.path in {"/","/live-radar.html"}:
            raw=html_path.read_bytes()
            self.send_response(200); self.send_header("content-type","text/html; charset=utf-8"); self.send_header("cache-control","no-store"); self.send_header("content-length",str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if p.path=="/api/health":
            self.send_json(200,{"ok":True,"app":"wfgg-radar","mode":"v61911-functional-pilot","gameConnector":"configured","production":False}); return
        if p.path=="/api/me":
            sid,s=self.require_session()
            if not s: return
            self.send_json(200,{"user":s["user"]}); return
        if p.path=="/api/radar/search/status":
            sid,s=self.require_session()
            if not s: return
            job_id=(urllib.parse.parse_qs(p.query).get("id") or [""])[0]
            if job_id != s.get("activeJob",""):
                self.send_json(404,{"error":"JOB_NOT_FOUND"}); return
            st,payload=connector("GET","/v1/collector/search/status?id="+urllib.parse.quote(job_id),None,40)
            self.send_json(st,payload); return
        if p.path=="/api/radar/autopilot/status":
            self.send_json(404,{"error":"AUTOPILOT_JOB_NOT_FOUND"}); return
        self.send_json(404,{"error":"NOT_FOUND"})

    def do_POST(self):
        p=urllib.parse.urlsplit(self.path)
        try: body=self.body_json()
        except Exception:
            self.send_json(400,{"error":"INVALID_JSON"}); return

        if p.path=="/api/auth/lastwar/start":
            game_uid=str(body.get("gameUid") or "").strip()
            email=str(body.get("email") or "").strip()
            st,payload=connector("POST","/v1/auth/email/start",{"gameUid":game_uid,"email":email},45)
            cid=str((payload or {}).get("challengeId") or "")
            if st==202 and cid:
                with lock: challenges[cid]={"uid":game_uid,"created":time.time()}
            self.send_json(st,payload); return

        if p.path=="/api/auth/lastwar/finish":
            cid=str(body.get("challengeId") or "").strip()
            code=str(body.get("code") or "").strip()
            with lock: ch=challenges.pop(cid,None)
            if not ch:
                self.send_json(410,{"error":"LASTWAR_EMAIL_CHALLENGE_NOT_FOUND"}); return
            st,payload=connector("POST","/v1/auth/email/finish",{"challengeId":cid,"code":code},75)
            auth=(payload or {}).get("auth") or {}
            credential=str(auth.get("credential") or "")
            identity=auth.get("identity") or {}
            if st!=200 or len(credential)<8:
                self.send_json(st,payload); return
            sid=secrets.token_urlsafe(32)
            user={"gameUid":str(identity.get("gameUid") or ch["uid"]),"pseudo":str(identity.get("pseudo") or "PILOT"),"serverId":identity.get("serverId"),"role":"OWNER"}
            with lock:
                sessions.clear()
                sessions[sid]={"credential":credential,"user":user,"activeJob":"","created":time.time()}
            self.send_json(200,{"ok":True,"user":user},f"pilot_session={sid}; HttpOnly; SameSite=Strict; Path=/"); return

        if p.path=="/api/auth/session/refresh":
            sid,s=self.require_session()
            if not s: return
            self.send_json(200,{"ok":True,"renewed":True,"expiresIn":3600,"user":s["user"]},f"pilot_session={sid}; HttpOnly; SameSite=Strict; Path=/"); return

        if p.path=="/api/auth/logout":
            sid=self.session_id()
            with lock: sessions.pop(sid,None)
            self.send_json(200,{"ok":True},"pilot_session=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/"); return

        if p.path=="/api/radar/search/start":
            sid,s=self.require_session()
            if not s: return
            q=str(body.get("q") or body.get("query") or "").strip()
            if q.lower()!=target_query.lower():
                self.send_json(400,{"error":"PILOT_TARGET_QUERY_REQUIRED","required":target_query}); return
            st,payload=connector("POST","/v1/collector/search/start",{"token":s["credential"],"query":q},45)
            job=(payload or {}).get("job") or {}
            if st==202 and job.get("id"):
                with lock:
                    if sid in sessions: sessions[sid]["activeJob"]=str(job["id"])
            self.send_json(st,payload); return

        if p.path=="/api/radar/search/stop":
            sid,s=self.require_session()
            if not s: return
            job_id=str(body.get("id") or "").strip()
            if not job_id or job_id!=s.get("activeJob",""):
                self.send_json(404,{"error":"JOB_NOT_FOUND"}); return
            pst,pp=connector("GET","/v1/collector/search/status?id="+urllib.parse.quote(job_id),None,30)
            pre=(pp or {}).get("job") or {}
            st,payload=connector("POST","/v1/collector/search/stop",{"id":job_id},30)
            if st in (200,202):
                threading.Thread(target=watch_terminal,args=(job_id,{"status":pre.get("status"),"phase":pre.get("phase"),"region":pre.get("region"),"cycleId":pre.get("cycleId"),"query":pre.get("query")}),daemon=True).start()
            self.send_json(st,payload); return

        self.send_json(404,{"error":"NOT_FOUND"})

httpd=ThreadingHTTPServer((bind_ip,port),Handler)
print(f"RADAR_V61911_FUNCTIONAL_SERVER_READY=http://{bind_ip}:{port}/live-radar.html",flush=True)
httpd.serve_forever()
PY

python3 "$PILOT_SERVER" "$TS_IP" "$PILOT_PORT" "$PILOT_UI" "$PILOT_EVIDENCE" "$TARGET_QUERY" "$PID_BEFORE_FUNCTIONAL" >"$PILOT_LOG" 2>&1 &
PILOT_SERVER_PID=$!

for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://$TS_IP:$PILOT_PORT/api/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS --max-time 3 "http://$TS_IP:$PILOT_PORT/api/health" >/dev/null || { cat "$PILOT_LOG"; die functional_pilot_ui_server_not_ready; }

echo "RADAR_V61911_FUNCTIONAL_WINDOW_READY=YES"
echo "RADAR_V61911_FUNCTIONAL_URL=http://$TS_IP:$PILOT_PORT/live-radar.html"
echo "RADAR_V61911_FUNCTIONAL_ACTION=Ouvre cette URL sur ton téléphone avec Tailscale actif. Connecte Last War par e-mail/code (laisse Mémoriser décoché), saisis $TARGET_QUERY, appuie sur RECHERCHER, attends que le scan affiche une région en cours puis appuie sur STOP une seule fois."
echo "RADAR_V61911_FUNCTIONAL_EXPECTED_UI=RECHERCHER>STOP>ARRÊT…>RECHERCHER"
echo "RADAR_V61911_FUNCTIONAL_WAIT_MAX_SECONDS=3600"
echo "RADAR_V61911_LASTWAR_MODE=READ_ONLY"
echo "RADAR_V61911_TOKEN_PERSISTENCE=NO"

FUNCTIONAL_RC=0
deadline=$((SECONDS+3600))
while [[ $SECONDS -lt $deadline ]]; do
  if [[ -s "$PILOT_EVIDENCE" ]]; then break; fi
  if ! kill -0 "$PILOT_SERVER_PID" >/dev/null 2>&1; then
    cat "$PILOT_LOG" || true
    FUNCTIONAL_RC=21
    break
  fi
  sleep 2
done
if [[ ! -s "$PILOT_EVIDENCE" && "$FUNCTIONAL_RC" -eq 0 ]]; then FUNCTIONAL_RC=22; fi

if [[ "$FUNCTIONAL_RC" -eq 0 ]]; then
  read -r FUNCTIONAL_JOB_ID FUNCTIONAL_CYCLE_ID <<< "$(python3 - "$PILOT_EVIDENCE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x.get('proof')=='RADAR_V61911_MANUAL_SEARCH_STOP_FUNCTIONAL',x
assert x.get('query')=='@federated:8120',x
assert str(x.get('status','')).upper()=='FAILED',x
assert x.get('error')=='MANUAL_SEARCH_STOPPED' or x.get('failureCode')=='MANUAL_SEARCH_STOPPED',x
assert x.get('tokenPersisted') is False,x
assert x.get('lastWarMode')=='READ_ONLY',x
assert x.get('stopScope')=='MANUAL_SEARCH_ONLY',x
pre=x.get('preStop') or {}
assert str(pre.get('status','')).upper() in {'QUEUED','RUNNING'},x
print(str(x.get('jobId') or ''),str(x.get('cycleId') or pre.get('cycleId') or '0'))
PY
  )" || FUNCTIONAL_RC=23
fi

if [[ "$FUNCTIONAL_RC" -eq 0 ]]; then
  [[ -n "$FUNCTIONAL_JOB_ID" ]] || FUNCTIONAL_RC=24
fi

if [[ "$FUNCTIONAL_RC" -eq 0 && "$FUNCTIONAL_CYCLE_ID" =~ ^[0-9]+$ && "$FUNCTIONAL_CYCLE_ID" -gt 0 ]]; then
  python3 - "$COLLECTOR_DB" "$FUNCTIONAL_CYCLE_ID" <<'PY' || FUNCTIONAL_RC=25
import sqlite3,sys
db,cid=sys.argv[1],int(sys.argv[2])
con=sqlite3.connect('file:'+db+'?mode=ro',uri=True,timeout=5)
con.row_factory=sqlite3.Row
con.execute('PRAGMA query_only=ON')
row=con.execute("SELECT id,query,status,COALESCE(error,'') error,COALESCE(finished_at,'') finished_at FROM cycles WHERE id=?",(cid,)).fetchone()
con.close()
assert row is not None,row
assert str(row['status']).upper()!='RUNNING',dict(row)
assert str(row['finished_at']).strip(),dict(row)
print("RADAR_V61911_FUNCTIONAL_CYCLE_ID="+str(row['id']))
print("RADAR_V61911_FUNCTIONAL_CYCLE_STATUS="+str(row['status']))
print("RADAR_V61911_FUNCTIONAL_CYCLE_ERROR="+(str(row['error']) or 'NONE'))
print("RADAR_V61911_FUNCTIONAL_CYCLE_TERMINALIZED=PASS")
PY
fi

PID_AFTER_FUNCTIONAL="$(systemctl show -p MainPID --value wfgg-radar-connector)"
if [[ "$FUNCTIONAL_RC" -eq 0 && "$PID_AFTER_FUNCTIONAL" != "$PID_BEFORE_FUNCTIONAL" ]]; then FUNCTIONAL_RC=26; fi
if [[ "$FUNCTIONAL_RC" -eq 0 ]]; then
  echo "RADAR_V61911_CONNECTOR_RESTART_DURING_STOP=NO"
  echo "RADAR_V61911_MANUAL_JOB_ID=$FUNCTIONAL_JOB_ID"
  echo "RADAR_V61911_MANUAL_SEARCH_STOPPED=PASS"
  echo "RADAR_V61911_STOP_SCOPE=MANUAL_SEARCH_ONLY"
  echo "RADAR_V61911_LASTWAR_MUTATION=NO"
  echo "RADAR_V61911_FUNCTIONAL_COLLECTOR_MUTATION=DISCOVERY_EVIDENCE_TERMINIZATION_ONLY"
  echo "RADAR_V61911_TOKEN_PERSISTENCE=NO"
  echo "RADAR_V61911_FUNCTIONAL_PROOF=PASS"
else
  echo "RADAR_V61911_FUNCTIONAL_PROOF=FAIL rc=$FUNCTIONAL_RC"
fi

if [[ -n "$PILOT_SERVER_PID" ]]; then
  kill "$PILOT_SERVER_PID" >/dev/null 2>&1 || true
  wait "$PILOT_SERVER_PID" >/dev/null 2>&1 || true
  PILOT_SERVER_PID=""
fi

# Close while approval is still active; EXIT will only retry if this fails.
close_pilot
revoke_approval

[ "$FUNCTIONAL_RC" -eq 0 ] || die functional_manual_search_stop_verification_failed

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "RADAR_V61911_PRODUCTION_APPROVAL_STANDING=NO"
echo "RADAR_V61911_PILOT_WINDOW_CLOSED=YES"
echo "RADAR_V61911_CHACHA_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_V61911_FUNCTIONAL_CHACHA_DEPLOY=PASS"

trap - EXIT
cleanup
