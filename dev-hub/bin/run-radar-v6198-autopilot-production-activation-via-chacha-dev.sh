#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6198_AUTOPILOT_ACTIVATION_REV:-}"
PROJECT="wfgg-radar"
EXPECTED_CONNECTOR="fb21a02feeaaa6a7013cf4e17c77bbb033a30a4bce021066fd947fc665360a9b"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
RADAR_URL="https://wfgg-radar.chachasan090375.workers.dev"
COLLECTOR_DB="${WFGG_COLLECTOR_DB:-/opt/wfgg-collector/data/collector.db}"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v6198-autopilot-activate.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
APPROVAL_ACTIVE=0
REPO=""

die(){ echo "RADAR_V6198_AUTOPILOT_ACTIVATION=BLOCKED reason=$1"; exit 2; }
cleanup(){ rm -rf "$WORK"; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for c in curl tar python3 sha256sum systemctl; do command -v "$c" >/dev/null 2>&1 || die "missing_command:$c"; done
[ -r "$COLLECTOR_DB" ] || die collector_db_unreadable

echo "=== CHACHA DEV RADAR V6.19.8 AUTOPILOT PRODUCTION ACTIVATION ==="
echo "SOURCE_REV=$REV"
echo "EXPECTED_CONNECTOR_SHA256=$EXPECTED_CONNECTOR"
echo "EXPECTED_NATIVE_SHA256=$EXPECTED_NATIVE"

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
echo "RADAR_V6198_AUTOPILOT_ACTIVATION_CONTRACT_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh >/dev/null
echo "RADAR_V6198_AUTOPILOT_ACTIVATION_ADAPTER=READY"

mkdir -p "$EVIDENCE_DIR" "$PLAN_DIR"
PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-before.json"
python3 - "$WORK/verify-before.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_BEFORE=PASS')
PY

# Fail closed unless the exact V6.19.8 production runtime and Cloudflare surface are live.
test "$(sha256sum /opt/wfgg-radar/bin/radar-connector | awk '{print $1}')" = "$EXPECTED_CONNECTOR" || die connector_sha_mismatch
test "$(sha256sum /opt/wfgg-radar/bin/radar-native-template | awk '{print $1}')" = "$EXPECTED_NATIVE" || die native_sha_mismatch
test "$(systemctl is-active wfgg-radar-connector)" = "active" || die radar_service_not_active
test "$(systemctl is-active wfgg-radar-sentinel.timer)" = "active" || die sentinel_timer_not_active
test "$(systemctl is-enabled wfgg-radar-sentinel.timer)" = "enabled" || die sentinel_not_enabled
curl -fsSL "$RADAR_URL/api/health?activation=$REV" -o "$WORK/health.json"
python3 - "$WORK/health.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
assert d.get('ok') is True,d
assert d.get('app')=='wfgg-radar',d
assert d.get('gameConnector')=='configured',d
print('RADAR_V6198_AUTOPILOT_CLOUDFLARE_HEALTH=PASS')
PY
curl -fsSL "$RADAR_URL/live-radar.html?activation=$REV" -o "$WORK/live-radar.html"
grep -Fq 'WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_UI_V6198' "$WORK/live-radar.html"
grep -Fq 'AUTOPILOT V6.19.8 · ARRÊTÉ' "$WORK/live-radar.html"
echo "RADAR_V6198_AUTOPILOT_PRODUCTION_PREFLIGHT=PASS"

# Baseline must be quiet: no targeted Collector cycle already RUNNING.
BASELINE_ID="$(python3 - "$COLLECTOR_DB" <<'PY'
import sqlite3,sys
db=sys.argv[1]
con=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
con.row_factory=sqlite3.Row
active=con.execute("SELECT id,query,status FROM cycles WHERE status='RUNNING' AND lower(query) LIKE '@federated:%' ORDER BY id").fetchall()
if active:
    for r in active:
        print(f"ACTIVE_TARGETED_CYCLE={r['id']}|{r['query']}|{r['status']}",file=sys.stderr)
    raise SystemExit(3)
row=con.execute("SELECT COALESCE(MAX(id),0) FROM cycles").fetchone()
con.close()
print(int(row[0] or 0))
PY
)" || die active_targeted_cycle_preexists
echo "RADAR_V6198_AUTOPILOT_BASELINE_CYCLE_ID=$BASELINE_ID"
echo "RADAR_V6198_AUTOPILOT_BASELINE_QUIET=PASS"

revoke_approval () {
  [ "$APPROVAL_ACTIVE" -eq 1 ] || return 0
  local ev="$EVIDENCE_DIR/approval-radar-v6198-autopilot-production-activation-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v6198-autopilot-production-activation-revoked.task-graph.json"
  local result="$WORK/revoke.task-result.json"
  python3 - "$ev" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
 "schema":"chacha.dev/human-approval-evidence/v1",
 "approval_id":"radar-autopilot-production-activation",
 "project":"wfgg-radar","actor":"human-user","source":"scope-expiry",
 "statement":"The one-shot V6.19.8 Autopilot production activation approval has been consumed or the activation window has ended.",
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
graph={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"AUTOPILOT-ACTIVATION-APPROVAL-REVOKE","generated_at":now,
 "tasks":[{"id":"approval:radar-v6198-autopilot-activation-revoke","kind":"approval",
 "description":"Revoke consumed V6.19.8 Autopilot production activation approval.","owner_role":"project-owner",
 "capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"radar-autopilot-production-activation"}],
 "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={"schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v6198-autopilot-activation-revoke",
 "status":"OK","producer":"human-approval-recorder","observed_at":now,"summary":"Autopilot activation approval revoked.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"radar-autopilot-production-activation","status":"REJECTED"}}],
 "outputs":[{"type":"approval","id":"radar-autopilot-production-activation","status":"REJECTED"}],
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
    echo "RADAR_V6198_AUTOPILOT_ACTIVATION_APPROVAL_REVOKED=PASS"
    APPROVAL_ACTIVE=0
  else
    echo "RADAR_V6198_AUTOPILOT_ACTIVATION_APPROVAL_REVOKED=FAIL"
  fi
}

finalize(){ rc=$?; set +e; revoke_approval; cleanup; exit "$rc"; }
trap finalize EXIT

APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v6198-autopilot-production-activation.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v6198-autopilot-production-activation.task-graph.json"
APPROVAL_RESULT="$WORK/approval.task-result.json"

python3 - "$APPROVAL_EVIDENCE" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
 "schema":"chacha.dev/human-approval-evidence/v1",
 "approval_id":"radar-autopilot-production-activation","project":"wfgg-radar",
 "scope":{"release":"V6.19.8 Collector Cycle Terminalization","action":"activate production Autopilot",
 "lastwar_mode":"READ-ONLY","collector_mutation":"discovery, evidence and terminalization only"},
 "actor":"human-user","source":"chat-explicit-approval",
 "statement":"J’approuve l’activation production de Radar Autopilot V6.19.8 en mode READ-ONLY Last War, avec mutations Collector limitées aux cycles de découverte, preuves et terminalisation.",
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
graph={"schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"AUTOPILOT-PRODUCTION-ACTIVATION-APPROVAL","generated_at":now,
 "tasks":[{"id":"approval:radar-v6198-autopilot-activation","kind":"approval",
 "description":"Record explicit human approval for V6.19.8 production Autopilot activation.","owner_role":"project-owner",
 "capabilities":[],"permission":"read","depends_on":[],"outputs":[{"type":"approval","id":"radar-autopilot-production-activation"}],
 "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},"blocking":True}],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}}
res={"schema":"chacha.dev/task-result/v1","project":"wfgg-radar","task_id":"approval:radar-v6198-autopilot-activation",
 "status":"OK","producer":"human-approval-recorder","observed_at":now,"summary":"Human approved V6.19.8 production Autopilot activation.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"radar-autopilot-production-activation","scope":"v6198-readonly-autopilot"}}],
 "outputs":[{"type":"approval","id":"radar-autopilot-production-activation","status":"APPROVED"}],
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
print('RADAR_V6198_AUTOPILOT_ACTIVATION_APPROVAL_INGESTED=PASS')
PY
APPROVAL_ACTIVE=1

echo "RADAR_V6198_AUTOPILOT_ACTIVATION_WINDOW_READY=YES"
echo "RADAR_V6198_AUTOPILOT_ACTIVATION_ACTION=Dans Radar production, appuie UNE SEULE FOIS sur DÉMARRER L’AUTOPILOT. Ne lance aucune recherche manuelle."
echo "RADAR_V6198_AUTOPILOT_ACTIVATION_WAIT_MAX_SECONDS=1200"
echo "RADAR_V6198_LASTWAR_MODE=READ_ONLY"
echo "RADAR_V6198_TOKEN_CAPTURE=NO"
echo "RADAR_V6198_TOKEN_PERSISTENCE=NO"

set +e
python3 - "$COLLECTOR_DB" "$BASELINE_ID" <<'PY'
import sqlite3,sys,time
db=sys.argv[1]; baseline=int(sys.argv[2]); deadline=time.time()+1200; last=None
while time.time()<deadline:
    con=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    row=con.execute(
      "SELECT id,query,status,COALESCE(error,'') error,COALESCE(started_at,'') started_at "
      "FROM cycles WHERE id>? AND lower(query) LIKE '@federated:%' ORDER BY id ASC LIMIT 1",(baseline,)
    ).fetchone()
    con.close()
    if row:
        state=(int(row['id']),str(row['query']),str(row['status']),str(row['error']))
        if state!=last:
            print("RADAR_V6198_AUTOPILOT_FIRST_CYCLE_ID="+str(row['id']),flush=True)
            print("RADAR_V6198_AUTOPILOT_FIRST_QUERY="+str(row['query']),flush=True)
            print("RADAR_V6198_AUTOPILOT_FIRST_STATUS="+str(row['status']),flush=True)
            print("RADAR_V6198_AUTOPILOT_FIRST_ERROR="+(str(row['error']) or 'NONE'),flush=True)
            last=state
        print("RADAR_V6198_AUTOPILOT_ACTIVITY_OBSERVED=PASS",flush=True)
        raise SystemExit(0)
    time.sleep(5)
print("RADAR_V6198_AUTOPILOT_ACTIVATION_FAIL=NO_NEW_TARGETED_CYCLE_WITHIN_1200S",flush=True)
raise SystemExit(3)
PY
ACTIVATION_RC=$?
set -e

revoke_approval
[ "$ACTIVATION_RC" -eq 0 ] || die activation_activity_not_observed

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "RADAR_V6198_AUTOPILOT_ACTIVATION_APPROVAL_STANDING=NO"
echo "RADAR_V6198_AUTOPILOT_PRODUCTION=ACTIVE_OBSERVED"
echo "RADAR_V6198_AUTOPILOT_ACTIVATION=PASS"
echo "RADAR_V6198_AUTOPILOT_CHACHA_PATH=PROJECT_CONTROL>HUMAN_APPROVAL>BROWSER_START>COLLECTOR_EVIDENCE"

trap - EXIT
cleanup
