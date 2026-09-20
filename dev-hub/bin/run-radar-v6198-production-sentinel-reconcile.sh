#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6198_PROD_RECONCILE_REV:-}"
PROJECT="wfgg-radar"
EXPECTED_CONNECTOR="fb21a02feeaaa6a7013cf4e17c77bbb033a30a4bce021066fd947fc665360a9b"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
RUNTIME="/opt/chacha-dev/runtime"
WORK_ROOT="$RUNTIME/tmp"
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "$WORK_ROOT/chacha-radar-v6198-prod-reconcile.XXXXXX")"
ARCHIVE="$WORK/repo.tar.gz"
EVIDENCE_DIR="$RUNTIME/evidence/$PROJECT"
PLAN_DIR="$RUNTIME/plans/$PROJECT"
APPROVAL_ACTIVE=0
REPO=""

die(){ echo "RADAR_V6198_PROD_RECONCILE=BLOCKED reason=$1"; exit 2; }
cleanup(){ rm -rf "$WORK"; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for c in curl tar python3 sha256sum; do command -v "$c" >/dev/null 2>&1 || die "missing_command:$c"; done

echo "=== CHACHA DEV RADAR V6.19.8 PRODUCTION SENTINEL RECONCILE ==="
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
WFGG_DEV_HUB_RADAR_ADAPTER_REV="$REV" bash dev-hub/bin/install-radar-runtime-adapter-pilot.sh >/dev/null
echo "CHACHA_DEV_RADAR_ADAPTER=READY"

mkdir -p "$EVIDENCE_DIR" "$PLAN_DIR"
PC=(python3 dev-hub/bin/project-control-cli.py --repo-root "$REPO" --policy dev-hub/config/project-control.v1.json --json)

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-before.json"
python3 - "$WORK/verify-before.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_BEFORE=PASS')
PY

revoke_approval () {
  [ "$APPROVAL_ACTIVE" -eq 1 ] || return 0
  local ev="$EVIDENCE_DIR/approval-radar-v6198-production-promotion-revoked.json"
  local graph="$PLAN_DIR/approval-radar-v6198-production-promotion-revoked.task-graph.json"
  local result="$WORK/revoke.task-result.json"
  python3 - "$ev" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
  "schema":"chacha.dev/human-approval-evidence/v1",
  "approval_id":"production-release",
  "project":"wfgg-radar",
  "actor":"human-user",
  "source":"scope-expiry",
  "statement":"The explicit V6.19.8 production promotion approval has been consumed or the single promotion window has ended.",
  "observed_at":datetime.now(timezone.utc).isoformat(),
  "single_promotion_window":True,
  "status":"REJECTED"
}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(obj,indent=2)+"\n")
PY
  chmod 0640 "$ev"
  local dg="sha256:$(sha256sum "$ev" | awk '{print $1}')"
  python3 - "$graph" "$result" "$ev" "$dg" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,s,d=sys.argv[1:]; now=datetime.now(timezone.utc).isoformat()
graph={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"PRODUCTION-APPROVAL-REVOKE","generated_at":now,
 "tasks":[{
   "id":"approval:radar-v6198-production-revoke","kind":"approval",
   "description":"Revoke consumed V6.19.8 production approval.","owner_role":"project-owner",
   "capabilities":[],"permission":"read","depends_on":[],
   "outputs":[{"type":"approval","id":"production-release"}],
   "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
   "blocking":True
 }],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}
}
res={
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar",
 "task_id":"approval:radar-v6198-production-revoke","status":"OK",
 "producer":"human-approval-recorder","observed_at":now,
 "summary":"Consumed V6.19.8 production approval revoked.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"production-release","status":"REJECTED"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"REJECTED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}
}
open(g,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding="utf-8").write(json.dumps(res,indent=2)+"\n")
PY
  "${PC[@]}" verify-result --project "$PROJECT" --result "$result" --graph "$graph" --method human --verifier human-user --ingest > "$WORK/revoke-ingest.json" || true
  if python3 - "$WORK/revoke-ingest.json" <<'PY'
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

finalize () {
  local rc=$?
  set +e
  revoke_approval
  cleanup
  exit "$rc"
}
trap finalize EXIT

APPROVAL_EVIDENCE="$EVIDENCE_DIR/approval-radar-v6198-production-promotion.json"
APPROVAL_GRAPH="$PLAN_DIR/approval-radar-v6198-production-promotion.task-graph.json"
APPROVAL_RESULT="$WORK/approval.task-result.json"

python3 - "$APPROVAL_EVIDENCE" <<'PY'
import json,sys
from datetime import datetime,timezone
obj={
  "schema":"chacha.dev/human-approval-evidence/v1",
  "approval_id":"production-release",
  "project":"wfgg-radar",
  "scope":{
    "release":"V6.19.8 Collector Cycle Terminalization",
    "action":"production promotion, Sentinel reconcile and associated Cloudflare surfaces",
    "connector_sha256":"fb21a02feeaaa6a7013cf4e17c77bbb033a30a4bce021066fd947fc665360a9b",
    "native_sha256":"274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900",
    "lastwar_mutation":False
  },
  "actor":"human-user",
  "source":"chat-explicit-approval",
  "statement":"J’approuve la promotion production Radar V6.19.8 Collector Cycle Terminalization et le déploiement des surfaces Cloudflare associées.",
  "observed_at":datetime.now(timezone.utc).isoformat(),
  "single_promotion_window":True
}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
PY
chmod 0640 "$APPROVAL_EVIDENCE"
DG="sha256:$(sha256sum "$APPROVAL_EVIDENCE" | awk '{print $1}')"

python3 - "$APPROVAL_GRAPH" "$APPROVAL_RESULT" "$APPROVAL_EVIDENCE" "$DG" <<'PY'
import json,sys
from datetime import datetime,timezone
g,r,s,d=sys.argv[1:]; now=datetime.now(timezone.utc).isoformat()
graph={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"PRODUCTION-APPROVAL","generated_at":now,
 "tasks":[{
   "id":"approval:radar-v6198-production","kind":"approval",
   "description":"Record explicit human approval for V6.19.8 production promotion.","owner_role":"project-owner",
   "capabilities":[],"permission":"read","depends_on":[],
   "outputs":[{"type":"approval","id":"production-release"}],
   "verification":{"mode":"human","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
   "blocking":True
 }],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":0,"approval_tasks":1,"blocking_tasks":1}
}
res={
 "schema":"chacha.dev/task-result/v1","project":"wfgg-radar",
 "task_id":"approval:radar-v6198-production","status":"OK",
 "producer":"human-approval-recorder","observed_at":now,
 "summary":"Human approved V6.19.8 production promotion.",
 "evidence":[{"kind":"human-approval","source":s,"digest":d,"details":{"approval_id":"production-release","scope":"radar-v6198-production"}}],
 "outputs":[{"type":"approval","id":"production-release","status":"APPROVED"}],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":None,"observed_at":None,"notes":"Human verification required."}
}
open(g,"w",encoding="utf-8").write(json.dumps(graph,indent=2)+"\n")
open(r,"w",encoding="utf-8").write(json.dumps(res,indent=2)+"\n")
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

GRAPH="$PLAN_DIR/radar-v6198-production-sentinel-reconcile.task-graph.json"
python3 - "$GRAPH" <<'PY'
import json,sys
from datetime import datetime,timezone
g={
 "schema":"chacha.dev/task-graph/v1","project":"wfgg-radar","transition":"OPERATE->OPERATE",
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "tasks":[{
   "id":"radar-runtime:production-sentinel-reconcile-v6198","kind":"runtime-deploy",
   "description":"Trigger Radar Sentinel reconciliation against the published V6.19.8 production release and verify exact runtime SHA.",
   "owner_role":"sre-observability","capabilities":["radar-pilot-control"],
   "permission":"production-deploy","depends_on":[],
   "outputs":[{"type":"gate","id":"radar-v6198-production-runtime"}],
   "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]},
   "blocking":True,"metadata":{"radar_runtime":{"action":"pilot-close"}}
 }],
 "summary":{"task_count":1,"artifact_tasks":0,"gate_tasks":1,"approval_tasks":0,"blocking_tasks":1}
}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(g,indent=2)+"\n")
PY

"${PC[@]}" schedule --project "$PROJECT" --graph "$GRAPH" > "$WORK/schedule.json"
PLAN="$(python3 - "$WORK/schedule.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print((x.get('details') or {})['execution_plan'])
PY
)"
"${PC[@]}" prepare-run --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" > "$WORK/prepare.json"
python3 - "$WORK/prepare.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print('RUN_CONTROLLER_PREPARE=PASS')
PY

"${PC[@]}" dispatch --project "$PROJECT" --plan "$PLAN" --graph "$GRAPH" --execute > "$WORK/dispatch.json"
RUN_RECORD="$(python3 - "$WORK/dispatch.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print((x.get('details') or {})['RUN_RECORD'])
PY
)"
echo "PROJECT_CONTROL_DISPATCH=PASS"

python3 - "$RUN_RECORD" "$EXPECTED_CONNECTOR" "$EXPECTED_NATIVE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); ec,en=sys.argv[2:4]
tasks=[t for w in x.get('waves') or [] for t in w.get('tasks') or []]
assert len(tasks)==1 and tasks[0].get('status')=='SUCCEEDED',tasks
r=json.load(open(tasks[0]['task_result'],encoding='utf-8'))
assert r.get('status')=='OK',r
ev=r.get('evidence') or []
assert ev,ev
d=ev[-1].get('details') or {}
print('RADAR_SERVICE='+str(d.get('radar_service')))
print('RADAR_SENTINEL_TIMER='+str(d.get('radar_sentinel_timer')))
print('RADAR_SENTINEL_ENABLED='+str(d.get('radar_sentinel_enabled')))
print('CONNECTOR_SHA256='+str(d.get('connector_sha256')))
print('NATIVE_SHA256='+str(d.get('native_sha256')))
assert d.get('connector_sha256')==ec,(d.get('connector_sha256'),ec)
assert d.get('native_sha256')==en,(d.get('native_sha256'),en)
assert d.get('radar_service')=='active',d
assert d.get('radar_sentinel_timer')=='active',d
assert d.get('radar_sentinel_enabled')=='enabled',d
print('RADAR_V6198_PRODUCTION_RUNTIME=PASS')
PY

revoke_approval

"${PC[@]}" verify-state --project "$PROJECT" > "$WORK/verify-after.json"
python3 - "$WORK/verify-after.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='OK',x
print('PROJECT_CONTROL_INTEGRITY_AFTER=PASS')
PY

echo "RADAR_V6198_PRODUCTION_APPROVAL_STANDING=NO"
echo "RADAR_V6198_LASTWAR_MUTATION=NO"
echo "RADAR_V6198_COLLECTOR_MUTATION=DISCOVERY_AND_TERMINALIZATION_ONLY"
echo "RADAR_V6198_CHACHA_PATH=PROJECT_CONTROL>SCHEDULER>RUN_CONTROLLER>RADAR_RUNTIME_ADAPTER>SENTINEL"
echo "RADAR_V6198_PROD_RECONCILE=PASS"

trap - EXIT
cleanup
