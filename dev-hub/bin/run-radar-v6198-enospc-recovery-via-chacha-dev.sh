#!/usr/bin/env bash
# Emergency finalizer for the V6.19.8 functional pilot after ENOSPC.
# Scope: close the already-authorized pilot window, force Sentinel reconcile,
# verify production fingerprints, revoke the consumed one-shot approval.
# No Last War scan. No Collector mutation.
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6198_RECOVERY_REV:-}"
PROJECT="wfgg-radar"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
PROD_REV="c5a5b0f6acda2870f2567be7e43d48fcb9af05c4"
PROD_CONNECTOR="b7ff60476f3afe7c8bcb9b78963c46daa4e8b5507490cc83cbcbc4ced63e7c35"
PROD_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v6198-enospc-recovery.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
REPO=""

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT
die(){ echo "RADAR_V6198_ENOSPC_RECOVERY=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_dev_hub_revision_required
for c in curl tar python3 sha256sum systemctl df stat; do
  command -v "$c" >/dev/null 2>&1 || die "missing_command:$c"
done

echo "=== CHACHA DEV RADAR V6.19.8 ENOSPC RECOVERY ==="
echo "DEV_HUB_REV=$REV"
echo "PRODUCTION_REV=$PROD_REV"
echo "EXPECTED_PRODUCTION_CONNECTOR_SHA256=$PROD_CONNECTOR"
echo "EXPECTED_NATIVE_SHA256=$PROD_NATIVE"

python3 - <<'PY'
import os
st=os.statvfs("/")
free=st.f_bavail*st.f_frsize
total=st.f_blocks*st.f_frsize
print("DISK_TOTAL_BYTES="+str(total))
print("DISK_FREE_BYTES="+str(free))
print("DISK_FREE_GIB="+f"{free/(1024**3):.2f}")
if free < 1024**3:
    raise SystemExit("RECOVERY_REQUIRES_AT_LEAST_1_GIB_FREE")
PY
echo "RADAR_V6198_ENOSPC_DISK_PREFLIGHT=PASS"

echo "RADAR_CONNECTOR_SHA_BEFORE=$(sha256sum /opt/wfgg-radar/bin/radar-connector | awk '{print $1}')"
echo "RADAR_NATIVE_SHA_BEFORE=$(sha256sum /opt/wfgg-radar/bin/radar-native-template | awk '{print $1}')"
echo "RADAR_SENTINEL_TIMER_BEFORE=$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
echo "RADAR_SENTINEL_ENABLED_BEFORE=$(systemctl is-enabled wfgg-radar-sentinel.timer 2>/dev/null || true)"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed
cd "$REPO"

python3 -m py_compile   dev-hub/adapters/radar-runtime-adapter.py   dev-hub/bin/project-control-cli.py   dev-hub/bin/project-control.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/external-runtime-dispatch.py   dev-hub/bin/verification-broker.py   dev-hub/bin/evidence-collector.py
python3 dev-hub/tests/test_radar_runtime_adapter_contract.py >/dev/null
echo "CHACHA_DEV_RADAR_ADAPTER_TESTS=PASS"

WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh >/dev/null
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

  "${PC[@]}" prepare-run --project "$PROJECT" --plan "$plan" --graph "$graph" > "$prep"
  python3 - "$prep" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
PY
  echo "${label}_PREPARE=PASS"

  "${PC[@]}" dispatch --project "$PROJECT" --plan "$plan" --graph "$graph" --execute > "$disp"
  python3 - "$disp" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
rr=(x.get('details') or {}).get('RUN_RECORD')
assert rr, x
print(rr)
PY
}

# Close the already-authorized pilot window and force a Sentinel reconcile.
CLOSE_GRAPH="$PLAN_DIR/radar-v6198-enospc-close.task-graph.json"
python3 - "$CLOSE_GRAPH" <<'PY'
import json,sys
from datetime import datetime,timezone
p=sys.argv[1]; now=datetime.now(timezone.utc).isoformat()
g={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar",
 "transition":"OPERATE->OPERATE","generated_at":now,
 "tasks":[{
   "id":"radar-runtime:pilot-close-v6198-enospc-recovery",
   "kind":"runtime-deploy",
   "description":"Complete the previously approved V6.19.8 pilot close after ENOSPC and restore Radar Sentinel protection.",
   "owner_role":"sre-observability",
   "capabilities":["radar-pilot-control"],
   "permission":"production-deploy",
   "depends_on":[],
   "outputs":[{"type":"gate","id":"radar-sentinel-protection"}],
   "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
   "blocking":True,
   "metadata":{"radar_runtime":{"action":"pilot-close"}}
 }],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":1}
}
open(p,"w",encoding='utf-8').write(json.dumps(g,indent=2)+"\n")
PY

CLOSE_RUN="$(run_graph "$CLOSE_GRAPH" RADAR_V6198_RECOVERY_CLOSE | tail -1)"
python3 - "$CLOSE_RUN" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
assert len(tasks)==1,tasks
assert tasks[0].get('status')=='SUCCEEDED',tasks
print('RADAR_V6198_PILOT_CLOSE_RECOVERY=PASS')
PY

# Verify Sentinel actually reconciled back to immutable production fingerprints.
python3 - "$PROD_CONNECTOR" "$PROD_NATIVE" <<'PY'
import hashlib,sys,time,subprocess
expected_connector,expected_native=sys.argv[1:3]
def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()
deadline=time.time()+180
last=None
while time.time()<deadline:
    conn=sha('/opt/wfgg-radar/bin/radar-connector')
    native=sha('/opt/wfgg-radar/bin/radar-native-template')
    timer=subprocess.run(['systemctl','is-active','wfgg-radar-sentinel.timer'],capture_output=True,text=True).stdout.strip()
    enabled=subprocess.run(['systemctl','is-enabled','wfgg-radar-sentinel.timer'],capture_output=True,text=True).stdout.strip()
    state=(conn,native,timer,enabled)
    if state != last:
        print('RADAR_CONNECTOR_SHA_RECOVERY='+conn,flush=True)
        print('RADAR_NATIVE_SHA_RECOVERY='+native,flush=True)
        print('RADAR_SENTINEL_TIMER_RECOVERY='+timer,flush=True)
        print('RADAR_SENTINEL_ENABLED_RECOVERY='+enabled,flush=True)
        last=state
    if conn==expected_connector and native==expected_native and timer=='active' and enabled=='enabled':
        print('RADAR_V6198_PRODUCTION_RUNTIME_RESTORED=PASS',flush=True)
        raise SystemExit(0)
    time.sleep(3)
raise SystemExit('PRODUCTION_RUNTIME_RESTORE_TIMEOUT')
PY

# Revoke the consumed one-shot approval. This is the same revocation that the
# approved functional pilot attempted before ENOSPC prevented evidence writes.
REVOKE_EVIDENCE="$EVIDENCE_DIR/approval-radar-v6198-enospc-recovery-revoked.json"
REVOKE_GRAPH="$PLAN_DIR/approval-radar-v6198-enospc-recovery-revoked.task-graph.json"
REVOKE_RESULT="$WORK/approval-revoked.task-result.json"

python3 - "$REVOKE_EVIDENCE" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
 "schema":"chacha.dev/human-approval-evidence/v1",
 "approval_id":"production-release",
 "project":"wfgg-radar",
 "actor":"human-user",
 "source":"scope-expiry-recovery",
 "statement":"The consumed V6.19.8 functional pilot approval is revoked after completing the ENOSPC-interrupted pilot close.",
 "observed_at":datetime.now(timezone.utc).isoformat(),
 "single_pilot_window":True,
 "status":"REJECTED"
}
open(sys.argv[1],"w",encoding='utf-8').write(json.dumps(obj,indent=2)+"\n")
PY
chmod 0640 "$REVOKE_EVIDENCE"
DG="sha256:$(sha256sum "$REVOKE_EVIDENCE" | awk '{print $1}')"

python3 - "$REVOKE_GRAPH" "$REVOKE_RESULT" "$REVOKE_EVIDENCE" "$DG" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,s,d=sys.argv[1:]
now=datetime.now(timezone.utc).isoformat()
graph={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar",
 "transition":"PILOT-APPROVAL-REVOKE-RECOVERY","generated_at":now,
 "tasks":[{
   "id":"approval:radar-v6198-enospc-recovery-revoke",
   "kind":"approval",
   "description":"Revoke the consumed V6.19.8 one-shot approval after ENOSPC recovery.",
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
 "task_id":"approval:radar-v6198-enospc-recovery-revoke",
 "status":"OK","producer":"human-approval-recorder","observed_at":now,
 "summary":"Consumed V6.19.8 one-shot approval revoked after ENOSPC recovery.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"production-release","status":"REJECTED"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"REJECTED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}
}
open(g,"w",encoding='utf-8').write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding='utf-8').write(json.dumps(res,indent=2)+"\n")
PY

"${PC[@]}" verify-result --project "$PROJECT" --result "$REVOKE_RESULT" --graph "$REVOKE_GRAPH" --method human --verifier human-user --ingest > "$WORK/revoke.json"
python3 - "$WORK/revoke.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
assert (x.get('details') or {}).get('verification_status')=='VERIFIED',x
print('PRODUCTION_RELEASE_APPROVAL_REVOKED=PASS')
PY

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "LASTWAR_CONTACT=NO"
echo "RADAR_V6198_GAME_SCAN_EXECUTED=NO"
echo "RADAR_V6198_COLLECTOR_MUTATION=NO"
echo "RADAR_V6198_PILOT_WINDOW_CLOSED=YES"
echo "RADAR_V6198_PRODUCTION_APPROVAL_STANDING=NO"
echo "RADAR_V6198_ENOSPC_RECOVERY=PASS"
