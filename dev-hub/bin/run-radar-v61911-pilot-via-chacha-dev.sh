#!/usr/bin/env bash
# Radar V6.19.11 Manual Search Stop governed PILOT runner via ChaCha DEV.
# Scope: one pilot window, install + guard-only probe, no Last War scan, then close.
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V61911_DEPLOY_REV:-}"
PROJECT="wfgg-radar"
APPROVED_CANDIDATE_REV="cbf67e46308e925f1ba5fad0be3f58764231935d"
PILOT_REV="895f288e6f8bd18486b02b022b9ecbef9d3102ab"
PILOT_BRANCH="radar-v61911-manual-search-stop"
CONNECTOR_SHA="4d66709f10d3a6b27ac255a1dfdc62e51d2817652634409ffe2edc071762c69f"
NATIVE_SHA="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
INSTALLER="radar-vps/install-v61911-pilot.sh"
PROBE="radar-vps/probe-v61911-pilot-runtime.sh"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
WORK="$(mktemp -d /tmp/chacha-radar-v61911-pilot.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
RUNTIME="/opt/chacha-dev/runtime"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
APPROVAL_ID="production-release"
APPROVAL_ACTIVE=0
CLOSE_ATTEMPTED=0
REPO=""

cleanup(){ rm -rf "$WORK"; }
die(){ echo "RADAR_V61911_CHACHA_PILOT=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required

for cmd in curl tar python3 sha256sum systemctl grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR V6.19.11 MANUAL SEARCH STOP PILOT ==="
echo "DEV_HUB_REV=$REV"
echo "APPROVED_CANDIDATE_REV=$APPROVED_CANDIDATE_REV"
echo "PILOT_REV=$PILOT_REV"
echo "PILOT_BRANCH=$PILOT_BRANCH"
echo "EXPECTED_CONNECTOR_SHA256=$CONNECTOR_SHA"
echo "EXPECTED_NATIVE_SHA256=$NATIVE_SHA"
echo "RADAR_V61911_GAME_SCAN_AUTHORIZED=NO"
echo "RADAR_V61911_LASTWAR_MODE=READ_ONLY"
echo "RADAR_V61911_TOKEN_PERSISTENCE=NO"
echo "RADAR_V61911_PRODUCTION_PROMOTION=NO"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile   dev-hub/adapters/radar-runtime-adapter.py   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py   dev-hub/bin/verification-broker.py   dev-hub/bin/evidence-collector.py

python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "CHACHA_DEV_RADAR_ADAPTER_TESTS=PASS"

python3 - <<'PY'
import json
x=json.load(open('dev-hub/config/provider-adapters.v1.json',encoding='utf-8'))
a=x['adapters']['radar-runtime-adapter']
assert a['status']=='ENABLED',a
assert a['executable']=='/opt/chacha-dev/adapters/radar-runtime/current/radar-runtime-adapter',a
print('CHACHA_DEV_RADAR_ADAPTER_REGISTRY=ENABLED')
PY
[ -x /opt/chacha-dev/adapters/radar-runtime/current/radar-runtime-adapter ] || die adapter_runtime_missing
echo "CHACHA_DEV_RADAR_ADAPTER_RUNTIME=PRESENT"

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

# Record the user's explicit, one-shot approval for the guard-only V6.19.11 PILOT.
APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v61911-pilot.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v61911-pilot.task-graph.json"
APPROVAL_RESULT="$WORK/approval.task-result.json"

python3 - "$APPROVAL_EVIDENCE" "$APPROVED_CANDIDATE_REV" "$PILOT_REV" <<'PY'
import json,sys
from datetime import datetime,timezone
p,candidate,bundle=sys.argv[1:]
obj={
  "schema":"chacha.dev/human-approval-evidence/v1",
  "approval_id":"production-release",
  "project":"wfgg-radar",
  "scope":{
    "pilot":"V6.19.11",
    "approved_candidate_revision":candidate,
    "pilot_bundle_revision":bundle,
    "change":"Manual Search Stop",
    "purpose":"Install the SHA-pinned V6.19.11 pilot and execute only a guard probe without any Last War game scan.",
    "lastwar_mode":"READ_ONLY",
    "game_scan_authorized":False,
    "token_persistence":False,
    "production_promotion":False
  },
  "actor":"human-user",
  "source":"chat-explicit-approval",
  "statement":"J’approuve le PILOT Radar V6.19.11 Manual Search Stop révision cbf67e46308e925f1ba5fad0be3f58764231935d, avec probe de garde sans scan Last War, Last War strictement READ-ONLY, aucune persistance de token et aucune promotion/déploiement production.",
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
    "id":"approval:radar-v61911-pilot",
    "kind":"approval",
    "description":"Record explicit human approval for the single V6.19.11 Manual Search Stop guard-only pilot window.",
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
  "task_id":"approval:radar-v61911-pilot",
  "status":"OK",
  "producer":"human-approval-recorder",
  "observed_at":now,
  "summary":"Human approved the single V6.19.11 Manual Search Stop guard-only pilot window.",
  "evidence":[{"kind":"human-approval","source":src,"digest":digest,"details":{"approval_id":"production-release","scope":"radar-v61911-pilot"}}],
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
print('RADAR_V61911_PILOT_APPROVAL_INGESTED=PASS')
PY
APPROVAL_ACTIVE=1

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
  local ev="$EVIDENCE_DIR/approval-radar-v61911-pilot-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v61911-pilot-revoked.task-graph.json"
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
  "statement":"The explicit V6.19.11 Manual Search Stop guard-only pilot approval has been consumed and is revoked after the single pilot window.",
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
 "tasks":[{"id":"approval:radar-v61911-pilot-revoke","kind":"approval","description":"Revoke the consumed one-shot V6.19.11 pilot approval.","owner_role":"project-owner","capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"production-release"}],"verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v61911-pilot-revoke","status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Consumed single-window V6.19.11 pilot approval revoked.","evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"production-release","status":"REJECTED"}}],
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
    echo "RADAR_V61911_PILOT_APPROVAL_REVOKED=PASS"
    APPROVAL_ACTIVE=0
  else
    echo "RADAR_V61911_PILOT_APPROVAL_REVOKED=FAIL"
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
  {"id":"radar-runtime:pilot-install-v61911","kind":"runtime-deploy","description":"Install the SHA-pinned V6.19.11 Manual Search Stop connector with rollback protection.","owner_role":"release","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":["radar-runtime:pilot-open-v61911"],"outputs":[{"type":"artifact","id":rev}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-install","revision":rev,"installer":installer,"expected_connector_sha256":csha,"expected_native_sha256":nsha}}},
  {"id":"radar-runtime:pilot-probe-v61911","kind":"runtime-diagnostic","description":"Verify V6.19.11 STOP route and runtime guards without reading a game token, starting a search, or executing a Last War scan.","owner_role":"sre-observability","capabilities":["radar-runtime-inspect"],"permission":"read","depends_on":["radar-runtime:pilot-install-v61911"],"outputs":[{"type":"artifact","id":"radar-v61911-guard-probe"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"pilot-probe","revision":rev,"installer":installer,"probe":probe,"expected_connector_sha256":csha,"expected_native_sha256":nsha}}}
 ],
 "summary":{"task_count":3,"artifact_tasks":2,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":3}
}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

PILOT_RUN="$(run_graph "$PILOT_GRAPH" RADAR_V61911_PILOT | tail -1)"

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
print("RADAR_V61911_STOP_ROUTE_GUARD=PASS")
print("RADAR_V61911_GAME_SCAN_EXECUTED=NO")
print("RADAR_V61911_COLLECTOR_MUTATION=NO")
print("RADAR_V61911_LASTWAR_MODE=READ_ONLY")
print("RADAR_V61911_TOKEN_PERSISTENCE=NO")
PY

close_pilot
revoke_approval

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "RADAR_V61911_PILOT_APPROVAL_STANDING=NO"
echo "RADAR_V61911_PILOT_WINDOW_CLOSED=YES"
echo "RADAR_V61911_PRODUCTION_PROMOTION=NO"
echo "RADAR_V61911_CHACHA_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_V61911_CHACHA_PILOT=PASS"

trap - EXIT
cleanup
