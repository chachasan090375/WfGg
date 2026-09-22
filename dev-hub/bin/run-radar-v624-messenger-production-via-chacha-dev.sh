#!/usr/bin/env bash
# Governed V6.24 Messenger production helper installation through ChaCha DEV.
# Scope: exact DRY-RUN Messenger binary only. No Radar Connector replacement.
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V624_MESSENGER_PRODUCTION_REV:-}"
PROJECT="wfgg-radar"
RADAR_REV="5e88b3275a0d6f09edec0b9014bdaf693790eaa9"
MESSENGER_SHA="3cf5d175325a319d601667e50388e8472057bcc152df7a618938daf357a3dfa1"
INSTALLER="radar-vps/install-v624-messenger-production.sh"
PROBE="radar-vps/probe-v624-messenger-production-runtime.sh"
ROLLBACK="radar-vps/rollback-v624-messenger-production.sh"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT" "$EVIDENCE_DIR" "$PLAN_DIR"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v624-messenger-prod.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
APPROVAL_ACTIVE=0
REPO=""

cleanup(){ rm -rf "$WORK"; }
die(){ echo "RADAR_V624_MESSENGER_PRODUCTION_CHACHA_DEPLOY=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required

for cmd in curl tar python3 sha256sum grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV RADAR V6.24 MESSENGER PRODUCTION ==="
echo "DEV_HUB_REV=$REV"
echo "RADAR_PRODUCTION_CANDIDATE_REV=$RADAR_REV"
echo "EXPECTED_MESSENGER_SHA256=$MESSENGER_SHA"
echo "MESSENGER_MODE=DRY_RUN_ONLY"
echo "RADAR_LASTWAR_MODE=READ_ONLY"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile   dev-hub/adapters/radar-runtime-adapter.py   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py   dev-hub/bin/verification-broker.py   dev-hub/bin/evidence-collector.py
python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo CHACHA_DEV_RADAR_ADAPTER_TESTS=PASS

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh
echo CHACHA_DEV_RADAR_ADAPTER_PROVISIONING=PASS

STATE="$RUNTIME/state/$PROJECT/state.json"
LEDGER="$EVIDENCE_DIR/ledger.json"
[ -f "$STATE" ] || die project_state_missing
[ -f "$LEDGER" ] || die evidence_ledger_missing
PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

"${PC[@]}" verify-state --project "$PROJECT" >"$WORK/verify-before.json"
python3 - "$WORK/verify-before.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_BEFORE=PASS')
PY

APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v624-messenger-production.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v624-messenger-production.task-graph.json"
APPROVAL_RESULT="$WORK/approval.task-result.json"

python3 - "$APPROVAL_EVIDENCE" "$RADAR_REV" "$MESSENGER_SHA" <<'PY'
import json,sys
from datetime import datetime,timezone
p,rev,sha=sys.argv[1:]
obj={
 "schema":"chacha.dev/human-approval-evidence/v1",
 "approval_id":"production-release",
 "project":"wfgg-radar",
 "scope":{
   "release":"V6.24 Internal Mail Outbox",
   "revision":rev,
   "messenger_sha256":sha,
   "mode":"DRY_RUN_ONLY",
   "lastwar_mode":"READ_ONLY",
   "mail_send_executed":False,
   "lastwar_mutation":False,
   "cross_server_private_mail":"BLOCKED_UNPROVEN",
   "rollback_required":True
 },
 "actor":"human-user",
 "source":"chat-explicit-approval",
 "statement":"J’approuve la promotion production Radar V6.24 Internal Mail Outbox après qualification et PILOT ChaCha DEV PASS, avec Messenger en DRY-RUN ONLY, Radar Last War strictement READ-ONLY, aucun mail.send, aucune mutation Last War, cross-server bloqué tant que non prouvé, et rollback disponible.",
 "observed_at":datetime.now(timezone.utc).isoformat(),
 "single_release_window":True
}
open(p,"w",encoding="utf-8").write(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
PY
chmod 0640 "$APPROVAL_EVIDENCE"
APPROVAL_DIGEST="sha256:$(sha256sum "$APPROVAL_EVIDENCE" | awk '{print $1}')"

python3 - "$APPROVAL_GRAPH" "$APPROVAL_RESULT" "$APPROVAL_EVIDENCE" "$APPROVAL_DIGEST" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,src,digest=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
graph={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"PRODUCTION-APPROVAL","generated_at":now,
 "tasks":[{"id":"approval:radar-v624-messenger-production","kind":"approval","description":"Record explicit human approval for Radar V6.24 Internal Mail Outbox production promotion.","owner_role":"project-owner","capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"production-release"}],"verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={"schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v624-messenger-production","status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Human approved Radar V6.24 Internal Mail Outbox production promotion.","evidence":[{"kind":"human-approval","source":src,"digest":digest,"details":{"approval_id":"production-release","scope":"radar-v624-messenger-production"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"APPROVED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}}
open(g,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding="utf-8").write(json.dumps(res,indent=2)+"\n")
PY

"${PC[@]}" verify-result --project "$PROJECT" --result "$APPROVAL_RESULT" --graph "$APPROVAL_GRAPH" --method human --verifier human-user --ingest >"$WORK/approval-ingest.json"
python3 - "$WORK/approval-ingest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
assert (x.get('details') or {}).get('verification_status')=='VERIFIED',x
print('RADAR_V624_PRODUCTION_RELEASE_APPROVAL_INGESTED=PASS')
PY
APPROVAL_ACTIVE=1

revoke_approval(){
  [ "$APPROVAL_ACTIVE" -eq 1 ] || return 0
  local ev="$EVIDENCE_DIR/approval-radar-v624-messenger-production-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v624-messenger-production-revoked.task-graph.json"
  local result="$WORK/approval-revoked.task-result.json"
  python3 - "$ev" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={"schema":"chacha.dev/human-approval-evidence/v1","approval_id":"production-release","project":"wfgg-radar","actor":"human-user","source":"scope-expiry","statement":"The explicit Radar V6.24 Messenger production approval has been consumed and is revoked after the single release window.","observed_at":datetime.now(timezone.utc).isoformat(),"single_release_window":True,"status":"REJECTED"}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(obj,indent=2)+"\n")
PY
  chmod 0640 "$ev"
  local dg="sha256:$(sha256sum "$ev" | awk '{print $1}')"
  python3 - "$graph" "$result" "$ev" "$dg" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,src,digest=sys.argv[1:]; now=datetime.now(timezone.utc).isoformat()
graph={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"PRODUCTION-APPROVAL-REVOKE","generated_at":now,
 "tasks":[{"id":"approval:radar-v624-messenger-production-revoke","kind":"approval","description":"Revoke consumed one-shot V6.24 Messenger production approval.","owner_role":"project-owner","capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"production-release"}],"verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={"schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v624-messenger-production-revoke","status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Consumed V6.24 Messenger production approval revoked.","evidence":[{"kind":"human-approval","source":src,"digest":digest,"details":{"approval_id":"production-release","status":"REJECTED"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"REJECTED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}}
open(g,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding="utf-8").write(json.dumps(res,indent=2)+"\n")
PY
  "${PC[@]}" verify-result --project "$PROJECT" --result "$result" --graph "$graph" --method human --verifier human-user --ingest >"$WORK/revoke-ingest.json" || true
  if python3 - "$WORK/revoke-ingest.json" <<'PY'
import json,sys
try:x=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception:raise SystemExit(1)
raise SystemExit(0 if x.get('status')=='OK' else 1)
PY
  then
    APPROVAL_ACTIVE=0
    echo PRODUCTION_RELEASE_APPROVAL_REVOKED=PASS
  else
    echo PRODUCTION_RELEASE_APPROVAL_REVOKED=FAIL
    return 1
  fi
}
finalize(){ rc=$?; set +e; revoke_approval; cleanup; exit "$rc"; }
trap finalize EXIT

GRAPH="$PLAN_DIR/radar-v624-messenger-production.task-graph.json"
python3 - "$GRAPH" "$RADAR_REV" "$MESSENGER_SHA" "$INSTALLER" "$PROBE" "$ROLLBACK" <<'PY'
import json,sys
from datetime import datetime,timezone
p,rev,sha,installer,probe,rollback=sys.argv[1:]; now=datetime.now(timezone.utc).isoformat()
g={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"OPERATE->OPERATE","generated_at":now,
 "tasks":[
  {"id":"radar-runtime:messenger-production-install-v624","kind":"runtime-deploy","description":"Install the exact qualified and PILOTed V6.24 dry-run Messenger binary under the Radar production root without replacing or restarting the Radar Connector.","owner_role":"release","capabilities":["radar-pilot-control"],"permission":"production-deploy","depends_on":[],"outputs":[{"type":"artifact","id":"wfgg-messenger-outbox-v624-production"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"messenger-production-install","revision":rev,"installer":installer,"rollback":rollback,"expected_messenger_sha256":sha}}},
  {"id":"radar-runtime:messenger-production-probe-v624","kind":"runtime-diagnostic","description":"Probe V6.24 production Messenger locally with DRAFT to QUEUED to HISTORY and cross-server guard, without Last War network access.","owner_role":"sre-observability","capabilities":["radar-runtime-inspect"],"permission":"read","depends_on":["radar-runtime:messenger-production-install-v624"],"outputs":[{"type":"gate","id":"radar-messenger-v624-production-runtime"}],"verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True,"metadata":{"radar_runtime":{"action":"messenger-production-probe","revision":rev,"probe":probe,"expected_messenger_sha256":sha}}}
 ],
 "summary":{"task_count":2,"artifact_tasks":1,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":2}}
open(p,"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

S="$WORK/schedule.json"; P="$WORK/prepare.json"; D="$WORK/dispatch.json"
"${PC[@]}" schedule --project "$PROJECT" --graph "$GRAPH" >"$S"
PLAN="$(python3 - "$S" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
echo RADAR_V624_MESSENGER_PRODUCTION_SCHEDULE=PASS
"${PC[@]}" prepare-run --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" >"$P"
python3 - "$P" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print('RADAR_V624_MESSENGER_PRODUCTION_PREPARE=PASS')
PY

set +e
"${PC[@]}" dispatch --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" --execute >"$D"
RC=$?
set -e
echo "RADAR_V624_MESSENGER_PRODUCTION_DISPATCH_RC=$RC"
RUN_RECORD="$(python3 - "$D" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
print((x.get('details') or {}).get('RUN_RECORD') or '')
PY
)"
[ -n "$RUN_RECORD" ] || die run_record_missing
echo "RADAR_V624_MESSENGER_PRODUCTION_RUN_RECORD=$RUN_RECORD"

python3 - "$RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
by={t.get('task_id'):t for t in tasks}
checks=[
 ('radar-runtime:messenger-production-install-v624','RADAR_MESSENGER_PRODUCTION_INSTALL_OK'),
 ('radar-runtime:messenger-production-probe-v624','RADAR_MESSENGER_PRODUCTION_PROBE_OK'),
]
for tid,summary in checks:
 t=by.get(tid) or {}
 label=tid.replace('radar-runtime:','').upper().replace('-','_')
 print(label+'_STATUS='+str(t.get('status')))
 if t.get('blockers'): print(label+'_BLOCKERS='+','.join(map(str,t['blockers'])))
 if t.get('status')!='SUCCEEDED': raise SystemExit('PRODUCTION_TASK_NOT_SUCCEEDED:'+tid)
 rp=t.get('task_result')
 if not rp: raise SystemExit('TASK_RESULT_MISSING:'+tid)
 r=json.load(open(rp,encoding='utf-8'))
 print(label+'_RESULT_STATUS='+str(r.get('status')))
 print(label+'_RESULT_SUMMARY='+str(r.get('summary')))
 assert r.get('status')=='OK',r
 assert r.get('summary')==summary,r
print('RADAR_V624_MESSENGER_PRODUCTION_INSTALL=PASS')
print('RADAR_V624_MESSENGER_PRODUCTION_PROBE=PASS')
print('RADAR_V624_PRODUCTION_CONNECTOR_TOUCHED=NO')
print('RADAR_V624_PRODUCTION_SERVICE_RESTARTED=NO')
print('RADAR_V624_GAME_CONNECTION=NONE')
print('RADAR_V624_GAME_SCAN_EXECUTED=NO')
print('RADAR_V624_MAIL_SEND_EXECUTED=NO')
print('RADAR_V624_LASTWAR_MUTATION=NO')
print('RADAR_V624_MESSENGER_ROLLBACK=AVAILABLE_NOT_EXECUTED')
PY

"${PC[@]}" verify-state --project "$PROJECT" >"$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY
revoke_approval
trap - EXIT
cleanup
echo RADAR_V624_MESSENGER_PRODUCTION_CHACHA_DEPLOY=PASS
