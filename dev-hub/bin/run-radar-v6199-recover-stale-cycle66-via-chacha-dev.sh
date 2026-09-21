#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6199_STALE66_RECOVERY_REV:-}"
PROJECT="wfgg-radar"
EXPECTED_CONNECTOR="5058159307ccb99e8e631fe71014608934b8575e69d5599e4388550306baab7f"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
COLLECTOR_DB="${WFGG_COLLECTOR_DB:-/opt/wfgg-collector/data/collector.db}"
COLLECTOR_URL="${WFGG_COLLECTOR_URL:-http://127.0.0.1:8790}"
TARGET_CYCLE_ID=66
TARGET_QUERY="@federated:8125"
STALE_MIN_SECONDS=900
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v6199-stale66-recovery.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
APPROVAL_ACTIVE=0
REPO=""

die(){ echo "RADAR_V6199_STALE66_RECOVERY=BLOCKED reason=$1"; exit 2; }
cleanup(){ rm -rf "$WORK"; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for c in curl tar python3 sha256sum systemctl; do command -v "$c" >/dev/null 2>&1 || die "missing_command:$c"; done
[ -r "$COLLECTOR_DB" ] || die collector_db_unreadable

echo "=== CHACHA DEV RADAR V6.19.9 STALE CYCLE 66 RECOVERY ==="
echo "SOURCE_REV=$REV"
echo "TARGET_CYCLE_ID=$TARGET_CYCLE_ID"
echo "TARGET_QUERY=$TARGET_QUERY"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile   dev-hub/adapters/radar-runtime-adapter.py   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py   dev-hub/bin/verification-broker.py   dev-hub/bin/evidence-collector.py
python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "RADAR_V6199_STALE66_RECOVERY_CONTRACT_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh >/dev/null
echo "RADAR_V6199_STALE66_RECOVERY_ADAPTER=READY"

mkdir -p "$EVIDENCE_DIR" "$PLAN_DIR"
PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-before.json"
python3 - "$WORK/verify-before.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_BEFORE=PASS')
PY

test "$(sha256sum /opt/wfgg-radar/bin/radar-connector | awk '{print $1}')" = "$EXPECTED_CONNECTOR" || die connector_sha_mismatch
test "$(sha256sum /opt/wfgg-radar/bin/radar-native-template | awk '{print $1}')" = "$EXPECTED_NATIVE" || die native_sha_mismatch
test "$(systemctl is-active wfgg-radar-connector)" = "active" || die radar_service_not_active
test "$(systemctl is-active wfgg-radar-sentinel.timer)" = "active" || die sentinel_timer_not_active
test "$(systemctl is-enabled wfgg-radar-sentinel.timer)" = "enabled" || die sentinel_not_enabled

read -r CYCLE_STATUS CYCLE_QUERY CYCLE_ERROR CYCLE_STARTED AGE_SECONDS RUNNING_TARGETED_COUNT <<< "$(python3 - "$COLLECTOR_DB" "$TARGET_CYCLE_ID" <<'PY'
import datetime,sqlite3,sys
db=sys.argv[1]; cid=int(sys.argv[2])
con=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
con.row_factory=sqlite3.Row
con.execute('PRAGMA query_only=ON')
r=con.execute("SELECT id,COALESCE(query,'') query,COALESCE(status,'') status,COALESCE(error,'') error,COALESCE(started_at,'') started_at FROM cycles WHERE id=?",(cid,)).fetchone()
if r is None:
    print("NOT_FOUND - - - 0 0")
    raise SystemExit(0)
started=str(r['started_at'] or '').strip()
age=0
if started:
    try:
        dt=datetime.datetime.fromisoformat(started.replace('Z','+00:00'))
        now=datetime.datetime.now(datetime.timezone.utc)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=datetime.timezone.utc)
        age=max(0,int((now-dt.astimezone(datetime.timezone.utc)).total_seconds()))
    except Exception:
        age=0
cnt=int(con.execute("SELECT COUNT(*) FROM cycles WHERE upper(trim(COALESCE(status,'')))='RUNNING' AND lower(query) LIKE '@federated:%'").fetchone()[0] or 0)
con.close()
def safe(v):
    v=str(v or '')
    return v.replace(' ','%20') if v else '-'
print(safe(r['status']),safe(r['query']),safe(r['error']),safe(started),age,cnt)
PY
)" || die stale66_read_failed

CYCLE_STATUS="${CYCLE_STATUS//%20/ }"
CYCLE_QUERY="${CYCLE_QUERY//%20/ }"
CYCLE_ERROR="${CYCLE_ERROR//%20/ }"
CYCLE_STARTED="${CYCLE_STARTED//%20/ }"

echo "RADAR_V6199_STALE66_STATUS=$CYCLE_STATUS"
echo "RADAR_V6199_STALE66_QUERY=$CYCLE_QUERY"
echo "RADAR_V6199_STALE66_ERROR=$CYCLE_ERROR"
echo "RADAR_V6199_STALE66_STARTED_AT=$CYCLE_STARTED"
echo "RADAR_V6199_STALE66_AGE_SECONDS=$AGE_SECONDS"
echo "RADAR_V6199_RUNNING_TARGETED_COUNT=$RUNNING_TARGETED_COUNT"

[ "$CYCLE_STATUS" = "RUNNING" ] || die cycle66_not_running
[ "$CYCLE_QUERY" = "$TARGET_QUERY" ] || die cycle66_query_mismatch
[ "$AGE_SECONDS" -ge "$STALE_MIN_SECONDS" ] || die cycle66_not_stale_yet
[ "$RUNNING_TARGETED_COUNT" -eq 1 ] || die unexpected_running_targeted_count
echo "RADAR_V6199_STALE66_PREFLIGHT=PASS"

revoke_approval () {
  [ "$APPROVAL_ACTIVE" -eq 1 ] || return 0
  local ev="$EVIDENCE_DIR/approval-radar-v6199-stale66-recovery-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v6199-stale66-recovery-revoked.task-graph.json"
  local result="$WORK/revoke.task-result.json"
  python3 - "$ev" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
 "schema":"chacha.dev/human-approval-evidence/v1",
 "approval_id":"radar-v6199-stale66-recovery",
 "project":"wfgg-radar","actor":"human-user","source":"scope-expiry",
 "statement":"The one-shot V6.19.9 stale cycle 66 recovery approval has been consumed or the recovery window has ended.",
 "observed_at":datetime.now(timezone.utc).isoformat(),
 "single_activation_window":True,"status":"REJECTED"
}
open(sys.argv[1],"w",encoding='utf-8').write(json.dumps(obj,indent=2)+"\n")
PY
  chmod 0640 "$ev"
  local dg="sha256:$(sha256sum "$ev" | awk '{print $1}')"
  python3 - "$graph" "$result" "$ev" "$dg" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,s,d=sys.argv[1:]; now=datetime.now(timezone.utc).isoformat()
graph={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"STALE66-RECOVERY-APPROVAL-REVOKE","generated_at":now,
 "tasks":[{"id":"approval:radar-v6199-stale66-recovery-revoke","kind":"approval",
 "description":"Revoke consumed V6.19.9 stale cycle 66 recovery approval.","owner_role":"project-owner",
 "capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"radar-v6199-stale66-recovery"}],
 "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={"schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v6199-stale66-recovery-revoke",
 "status":"OK","producer":"human-approval-recorder","observed_at":now,"summary":"Stale cycle 66 recovery approval revoked.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"radar-v6199-stale66-recovery","status":"REJECTED"}}],
 "outputs":[{"type":"approval","id":"radar-v6199-stale66-recovery","status":"REJECTED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}}
open(g,"w",encoding='utf-8').write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding='utf-8').write(json.dumps(res,indent=2)+"\n")
PY
  "${PC[@]}" verify-result --project "$PROJECT" --result "$result" --graph "$graph" --method human --verifier human-user --ingest > "$WORK/revoke.json" || true
  if python3 - "$WORK/revoke.json" <<'PY'
import json,sys
try:x=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception:raise SystemExit(1)
raise SystemExit(0 if x.get('status')=='OK' else 1)
PY
  then
    echo "RADAR_V6199_STALE66_RECOVERY_APPROVAL_REVOKED=PASS"
    APPROVAL_ACTIVE=0
  else
    echo "RADAR_V6199_STALE66_RECOVERY_APPROVAL_REVOKED=FAIL"
  fi
}

finalize(){ rc=$?; set +e; revoke_approval; cleanup; exit "$rc"; }
trap finalize EXIT

APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v6199-stale66-recovery.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v6199-stale66-recovery.task-graph.json"
APPROVAL_RESULT="$WORK/approval.task-result.json"

python3 - "$APPROVAL_EVIDENCE" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
 "schema":"chacha.dev/human-approval-evidence/v1",
 "approval_id":"radar-v6199-stale66-recovery","project":"wfgg-radar",
 "scope":{"release":"V6.19.9 Autopilot Targeted History Quality","action":"terminalize stale Collector cycle 66 only",
 "cycle_id":66,"query":"@federated:8125","lastwar_mode":"NO_CONTACT","collector_mutation":"cycle 66 terminalization only"},
 "actor":"human-user","source":"chat-explicit-approval",
 "statement":"J’approuve la récupération du cycle Collector stale 66 de Radar V6.19.9, limitée à sa terminalisation en FAILED avec STALE_RUNNING_CYCLE_RECOVERED_V6197, sans scan Last War et sans autre mutation Collector.",
 "observed_at":datetime.now(timezone.utc).isoformat(),"single_activation_window":True
}
open(sys.argv[1],"w",encoding='utf-8').write(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
PY
chmod 0640 "$APPROVAL_EVIDENCE"
DG="sha256:$(sha256sum "$APPROVAL_EVIDENCE" | awk '{print $1}')"
python3 - "$APPROVAL_GRAPH" "$APPROVAL_RESULT" "$APPROVAL_EVIDENCE" "$DG" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,s,d=sys.argv[1:]; now=datetime.now(timezone.utc).isoformat()
graph={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"STALE66-RECOVERY-APPROVAL","generated_at":now,
 "tasks":[{"id":"approval:radar-v6199-stale66-recovery","kind":"approval",
 "description":"Record explicit human approval for stale Collector cycle 66 terminalization only.","owner_role":"project-owner",
 "capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"radar-v6199-stale66-recovery"}],
 "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={"schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v6199-stale66-recovery",
 "status":"OK","producer":"human-approval-recorder","observed_at":now,"summary":"Human approved stale cycle 66 recovery.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"radar-v6199-stale66-recovery","scope":"cycle66-terminalization-only"}}],
 "outputs":[{"type":"approval","id":"radar-v6199-stale66-recovery","status":"APPROVED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}}
open(g,"w",encoding='utf-8').write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding='utf-8').write(json.dumps(res,indent=2)+"\n")
PY
"${PC[@]}" verify-result --project "$PROJECT" --result "$APPROVAL_RESULT" --graph "$APPROVAL_GRAPH" --method human --verifier human-user --ingest > "$WORK/approval.json"
python3 - "$WORK/approval.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
assert (x.get('details') or {}).get('verification_status')=='VERIFIED',x
print('RADAR_V6199_STALE66_RECOVERY_APPROVAL_INGESTED=PASS')
PY
APPROVAL_ACTIVE=1

# Use the Collector's own terminalization API; do not mutate SQLite directly.
curl -fsS -X POST "$COLLECTOR_URL/cycle/finish"   -H 'Content-Type: application/json'   --data '{"cycleId":66,"status":"FAILED","error":"STALE_RUNNING_CYCLE_RECOVERED_V6197"}'   -o "$WORK/finish.json"
python3 - "$WORK/finish.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x.get('ok') is True,x
print('RADAR_V6199_STALE66_COLLECTOR_FINISH_API=PASS')
PY

python3 - "$COLLECTOR_DB" "$TARGET_CYCLE_ID" "$TARGET_QUERY" <<'PY'
import sqlite3,sys
db=sys.argv[1]; cid=int(sys.argv[2]); q=sys.argv[3]
con=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
con.row_factory=sqlite3.Row
con.execute('PRAGMA query_only=ON')
r=con.execute("SELECT id,query,status,COALESCE(error,'') error,COALESCE(finished_at,'') finished_at FROM cycles WHERE id=?",(cid,)).fetchone()
active=int(con.execute("SELECT COUNT(*) FROM cycles WHERE upper(trim(COALESCE(status,'')))='RUNNING' AND lower(query) LIKE '@federated:%'").fetchone()[0] or 0)
con.close()
assert r is not None,r
assert str(r['query'])==q,r
assert str(r['status']).upper()=='FAILED',r
assert str(r['error'])=='STALE_RUNNING_CYCLE_RECOVERED_V6197',r
assert str(r['finished_at'] or '').strip(),r
assert active==0,active
print('RADAR_V6199_STALE66_TERMINAL=PASS')
print('RADAR_V6199_STALE66_RUNNING_TARGETED_AFTER=0')
PY

revoke_approval

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "LASTWAR_CONTACT=NO"
echo "RADAR_PRODUCTION_MUTATION=NO"
echo "RADAR_V6199_COLLECTOR_MUTATION=CYCLE_66_TERMINALIZATION_ONLY"
echo "RADAR_V6199_HISTORY_MUTATION=NO"
echo "RADAR_V6199_STALE66_RECOVERY_APPROVAL_STANDING=NO"
echo "RADAR_V6199_STALE66_RECOVERY=PASS"

trap - EXIT
cleanup
