#!/usr/bin/env bash
# WfGg Radar V6.24 Internal Mail Outbox — isolated Messenger VPS pilot via ChaCha DEV.
# This runner installs/probes only /opt/wfgg-messenger-pilot.
# It never stops/restarts/replaces wfgg-radar-connector and never sends mail.send.
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V624_DEPLOY_REV:-}"
PROJECT="wfgg-radar"
RADAR_PILOT_REV="633c1cc9b7930b1414beeca6a19f909842b8e58b"
MESSENGER_SHA="3cf5d175325a319d601667e50388e8472057bcc152df7a618938daf357a3dfa1"
INSTALLER="radar-vps/install-v624-messenger-pilot.sh"
PROBE="radar-vps/probe-v624-messenger-pilot-runtime.sh"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"

RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v624-messenger.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
APPROVAL_ACTIVE=0
REPO=""

cleanup(){ rm -rf "$WORK"; }
die(){ echo "RADAR_V624_MESSENGER_CHACHA_PILOT=BLOCKED reason=$1"; exit 2; }

revoke_approval () {
  [ "$APPROVAL_ACTIVE" -eq 1 ] || return 0
  local ev="$EVIDENCE_DIR/approval-radar-v624-messenger-pilot-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v624-messenger-pilot-revoked.task-graph.json"
  local result_file="$WORK/approval-revoked.task-result.json"

  python3 - "$ev" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
  "schema":"chacha.dev/human-approval-evidence/v1",
  "approval_id":"production-release",
  "project":"wfgg-radar",
  "actor":"human-user",
  "source":"scope-expiry",
  "statement":"The contextual Go approval for the isolated V6.24 Messenger Outbox VPS pilot has been consumed and is revoked. It never authorizes V6.24 production promotion or any real Last War mail.send.",
  "observed_at":datetime.now(timezone.utc).isoformat(),
  "single_pilot_window":True,
  "status":"REJECTED"
}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
PY
  chmod 0640 "$ev"
  local dg="sha256:$(sha256sum "$ev" | awk '{print $1}')"

  python3 - "$graph" "$result_file" "$ev" "$dg" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,s,d=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
graph={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"PILOT-APPROVAL-REVOKE","generated_at":now,
 "tasks":[{
   "id":"approval:radar-v624-messenger-pilot-revoke",
   "kind":"approval",
   "description":"Revoke the consumed one-shot V6.24 isolated Messenger pilot approval.",
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
res={
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar",
 "task_id":"approval:radar-v624-messenger-pilot-revoke",
 "status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Consumed V6.24 isolated Messenger pilot approval revoked.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"production-release","status":"REJECTED"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"REJECTED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}
}
open(g,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding="utf-8").write(json.dumps(res,indent=2)+"\n")
PY

  "${PC[@]}" verify-result --project "$PROJECT" --result "$result_file" --graph "$graph"     --method human --verifier human-user --ingest > "$WORK/approval-revoke-ingest.json" || true

  if python3 - "$WORK/approval-revoke-ingest.json" <<'PY'
import json,sys
try: x=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception: raise SystemExit(1)
raise SystemExit(0 if x.get('status')=='OK' else 1)
PY
  then
    echo "RADAR_V624_PILOT_APPROVAL_REVOKED=PASS"
    APPROVAL_ACTIVE=0
  else
    echo "RADAR_V624_PILOT_APPROVAL_REVOKED=FAIL"
  fi
}

finalize(){
  rc=$?
  set +e
  revoke_approval
  cleanup
  exit "$rc"
}
trap finalize EXIT

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required

for cmd in curl tar python3 sha256sum grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR V6.24 ISOLATED MESSENGER PILOT ==="
echo "DEV_HUB_REV=$REV"
echo "RADAR_PILOT_REV=$RADAR_PILOT_REV"
echo "EXPECTED_MESSENGER_SHA256=$MESSENGER_SHA"
echo "RADAR_V624_LASTWAR_MODE=READ_ONLY"
echo "RADAR_V624_MESSENGER_MODE=DRY_RUN_ONLY"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile   dev-hub/adapters/radar-runtime-adapter.py   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py   dev-hub/bin/verification-broker.py   dev-hub/bin/evidence-collector.py

python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
python3 dev-hub/tests/test_radar_v624_messenger_pilot_contract.py >/dev/null
echo "CHACHA_DEV_RADAR_V624_ADAPTER_TESTS=PASS"

# Provision the new immutable adapter digest/version. Sentinel stays active.
WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh
echo "CHACHA_DEV_RADAR_V624_ADAPTER_PROVISIONING=PASS"

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

# Record current V6.24 project intent through the verified evidence path.
INTENT_SRC="$EVIDENCE_DIR/project-intent-v624.v1.json"
install -m 0640 dev-hub/projects/wfgg-radar/project-intent.v1.json "$INTENT_SRC"
INTENT_DIGEST="sha256:$(sha256sum "$INTENT_SRC" | awk '{print $1}')"
INTENT_GRAPH="$PLAN_DIR/project-intent-v624.task-graph.json"
INTENT_RESULT="$WORK/project-intent-v624.task-result.json"

python3 - "$INTENT_GRAPH" "$INTENT_RESULT" "$INTENT_SRC" "$INTENT_DIGEST" <<'PY'
import json,sys
from datetime import datetime,timezone
graph_path,result_path,src,digest=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
graph={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"IDEA->DESIGN","generated_at":now,
 "tasks":[{
   "id":"control:project-intent",
   "kind":"documentation",
   "description":"Register the V6.24 isolated Messenger Outbox project intent.",
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
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"control:project-intent",
 "status":"OK","producer":"project-intent-recorder","observed_at":now,
 "summary":"V6.24 isolated Messenger Outbox project intent registered.",
 "evidence":[{"kind":"artifact","source":src,"digest":digest,"details":{"schema":"chacha.dev/project-intent/v1"}}],
 "outputs":[{"type":"artifact","id":"project-intent","status":"OK"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Independent verification required."}
}
open(graph_path,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(result_path,"w",encoding="utf-8").write(json.dumps(result,indent=2)+"\n")
PY
"${PC[@]}" verify-result --project "$PROJECT" --result "$INTENT_RESULT" --graph "$INTENT_GRAPH"   --method machine --verifier verification-broker --ingest > "$WORK/intent-ingest.json"
python3 - "$WORK/intent-ingest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
assert (x.get('details') or {}).get('verification_status')=='VERIFIED',x
print('PROJECT_INTENT_V624_VERIFIED_INGESTED=PASS')
PY

# Record the user's contextual explicit approval: the user answered "Go" immediately
# after the isolated VPS pilot was described as no production endpoint / no Last War send.
APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v624-messenger-pilot.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v624-messenger-pilot.task-graph.json"
APPROVAL_RESULT="$WORK/approval-v624.task-result.json"
python3 - "$APPROVAL_EVIDENCE" "$RADAR_PILOT_REV" "$MESSENGER_SHA" <<'PY'
import json,sys
from datetime import datetime,timezone
p,rev,sha=sys.argv[1:]
obj={
 "schema":"chacha.dev/human-approval-evidence/v1",
 "approval_id":"production-release",
 "project":"wfgg-radar",
 "scope":{
   "pilot":"V6.24 isolated Messenger Outbox",
   "radar_revision":rev,
   "messenger_sha256":sha,
   "purpose":"install and probe only /opt/wfgg-messenger-pilot; no production Radar replacement and no Last War send"
 },
 "actor":"human-user",
 "source":"chat-explicit-approval",
 "statement":"Go",
 "context":"Assistant stated: continue with the isolated VPS pilot, install only the Outbox binary in a separate pilot directory and run DRAFT -> QUEUED -> HISTORY, with no production endpoint and no Last War send.",
 "observed_at":datetime.now(timezone.utc).isoformat(),
 "single_pilot_window":True,
 "does_not_authorize_production_promotion":True,
 "does_not_authorize_lastwar_write":True
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
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"PILOT-APPROVAL","generated_at":now,
 "tasks":[{
   "id":"approval:radar-v624-messenger-pilot",
   "kind":"approval",
   "description":"Record contextual human approval for one isolated V6.24 Messenger Outbox VPS pilot.",
   "owner_role":"project-owner","capabilities":[],"permission":"read","depends_on":[],
   "outputs":[{"type":"approval","id":"production-release"}],
   "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
   "blocking":True
 }],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}
}
result={
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v624-messenger-pilot",
 "status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Human approved one isolated V6.24 Messenger Outbox VPS pilot only.",
 "evidence":[{"kind":"human-approval","source":src,"digest":digest,"details":{"approval_id":"production-release","scope":"radar-v624-messenger-pilot"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"APPROVED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}
}
open(graph_path,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(result_path,"w",encoding="utf-8").write(json.dumps(result,indent=2)+"\n")
PY
"${PC[@]}" verify-result --project "$PROJECT" --result "$APPROVAL_RESULT" --graph "$APPROVAL_GRAPH"   --method human --verifier human-user --ingest > "$WORK/approval-ingest.json"
python3 - "$WORK/approval-ingest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
assert (x.get('details') or {}).get('verification_status')=='VERIFIED',x
print('RADAR_V624_PILOT_APPROVAL_INGESTED=PASS')
PY
APPROVAL_ACTIVE=1

run_graph () {
  local graph="$1" label="$2"
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

PILOT_GRAPH="$PLAN_DIR/radar-v624-messenger-pilot.task-graph.json"
python3 - "$PILOT_GRAPH" "$RADAR_PILOT_REV" "$MESSENGER_SHA" "$INSTALLER" "$PROBE" <<'PY'
import json,sys
from datetime import datetime,timezone
p,rev,msha,installer,probe=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
g={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"OPERATE->OPERATE","generated_at":now,
 "tasks":[
   {
     "id":"radar-runtime:messenger-pilot-install-v624",
     "kind":"runtime-deploy",
     "description":"Install only the SHA-pinned V6.24 dry-run Messenger Outbox under /opt/wfgg-messenger-pilot while production Radar and Sentinel remain unchanged.",
     "owner_role":"release",
     "capabilities":["radar-pilot-control"],
     "permission":"production-deploy",
     "depends_on":[],
     "outputs":[{"type":"artifact","id":"radar-v624-messenger-pilot"}],
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
     "description":"Run local V6.24 DRAFT->QUEUED->HISTORY dry-run probe without game connection, token or Last War mutation.",
     "owner_role":"sre-observability",
     "capabilities":["radar-runtime-inspect"],
     "permission":"read",
     "depends_on":["radar-runtime:messenger-pilot-install-v624"],
     "outputs":[{"type":"artifact","id":"radar-v624-messenger-runtime-probe"}],
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
 "summary":{"task_count":2,"artifact_tasks":2,"gate_tasks":0,"approval_tasks":0,"blocking_tasks":2}
}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

PILOT_RUN="$(run_graph "$PILOT_GRAPH" RADAR_V624_MESSENGER_PILOT | tail -1)"

python3 - "$PILOT_RUN" "$MESSENGER_SHA" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); expected=sys.argv[2]
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
by={t.get('task_id'):t for t in tasks}
ids=(
 "radar-runtime:messenger-pilot-install-v624",
 "radar-runtime:messenger-pilot-probe-v624",
)
for tid in ids:
    t=by.get(tid) or {}
    print(tid.replace("radar-runtime:","").upper().replace("-","_")+"_STATUS="+str(t.get('status')))
    if t.get('status')!="SUCCEEDED":
        raise SystemExit("V624_PILOT_TASK_NOT_SUCCEEDED:"+tid)
probe=by["radar-runtime:messenger-pilot-probe-v624"]
path=probe.get("task_result")
if not path:
    raise SystemExit("V624_PROBE_TASK_RESULT_MISSING")
r=json.load(open(path,encoding='utf-8'))
assert r.get("status")=="OK",r
ev=r.get("evidence") or []
cmd=next((e for e in ev if e.get("source")=="local://radar-v624-messenger-pilot-probe"),None)
assert cmd,ev
d=cmd.get("details") or {}
assert d.get("pass_marker") is True,d
assert d.get("production_runtime_unchanged") is True,d
assert d.get("game_connection")=="NONE",d
assert d.get("game_scan_executed") is False,d
assert d.get("lastwar_mutation") is False,d
assert d.get("network_send") is False,d
print("RADAR_V624_MESSENGER_SHA_EXPECTED="+expected)
print("RADAR_V624_RUNTIME_DRAFT_QUEUE_HISTORY=PASS")
print("RADAR_V624_PRODUCTION_RUNTIME_UNCHANGED=PASS")
print("RADAR_V624_GAME_CONNECTION=NONE")
print("RADAR_V624_GAME_SCAN_EXECUTED=NO")
print("RADAR_V624_TOKEN_USED=NO")
print("RADAR_V624_MAIL_SEND_EXECUTED=NO")
print("RADAR_V624_LASTWAR_MUTATION=NO")
print("RADAR_V624_NETWORK_SEND=NO")
PY

revoke_approval

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "RADAR_V624_PRODUCTION_APPROVAL_STANDING=NO"
echo "RADAR_V624_PRODUCTION_DEPLOYMENT=NO"
echo "RADAR_V624_LASTWAR_WRITE_AUTHORIZED=NO"
echo "RADAR_V624_CHACHA_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER"
echo "RADAR_V624_MESSENGER_CHACHA_PILOT=PASS"

trap - EXIT
cleanup
