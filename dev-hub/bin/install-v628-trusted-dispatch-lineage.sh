#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V628_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v628.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
CONFIDENCE="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
MEMORY="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
PREVIOUS=""
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V628_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V628_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      systemctl restart chacha-dev-verified-evidence-learning.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-production-lineage-feedback.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-component-confidence.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-central-memory-assimilation.timer >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V628_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink grep chmod find env; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$CONFIDENCE" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=v627_confidence_snapshot_missing"; exit 2; }
[ -f "$CURRENT/dev-hub/bin/verified-evidence-learning.py" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=v627_learning_reconciler_missing"; exit 2; }
systemctl is-enabled --quiet chacha-dev-verified-evidence-learning.timer || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=v627_learning_timer_not_enabled"; exit 2; }
python3 - "$CONFIDENCE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("schema")=="chacha.dev/component-confidence-snapshot/v1",x.get("schema")
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
assert x.get("confidence_is_advisory_not_final_authority") is True,x
assert x.get("technology_revalidation_required") is True,x
print("CHACHA_DEV_V628_V627_BASELINE=PASS")
PY
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True:raise SystemExit("CHACHA_DEV_V628_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
for required in   dev-hub/bin/trusted_dispatch_learning.py   dev-hub/bin/task-contract-binder.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/project-control.py   dev-hub/bin/evidence-collector.py   dev-hub/bin/verified-evidence-learning.py   dev-hub/bin/learning-delta-ingest.py   dev-hub/bin/guardian-governed-production-lineage-feedback.py   dev-hub/bin/guardian-governed-component-confidence.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/adapters/platform-selftest-adapter.py   dev-hub/config/provider-adapters.v1.json   dev-hub/config/run-controller.v1.json   dev-hub/config/project-control.v1.json   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/tests/test_v628_trusted_dispatch_lineage.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
chmod 0755 "$RELEASE/dev-hub/adapters/platform-selftest-adapter.py"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/trusted_dispatch_learning.py"   "$RELEASE/dev-hub/bin/task-contract-binder.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/project-control.py"   "$RELEASE/dev-hub/bin/evidence-collector.py"   "$RELEASE/dev-hub/adapters/platform-selftest-adapter.py"
python3 -m json.tool "$RELEASE/dev-hub/config/provider-adapters.v1.json" >/dev/null
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V628_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v628_trusted_dispatch_lineage.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V628_DYNAMIC_AGENT_LINEAGE_DERIVED=PASS   CHACHA_DEV_V628_DYNAMIC_BRANCH_LINEAGE_DERIVED=PASS   CHACHA_DEV_V628_FOUNDRY_LINEAGE_DERIVED=PASS   CHACHA_DEV_V628_CONNECTOR_LINEAGE_CONTENT_ADDRESSED=PASS   CHACHA_DEV_V628_PROVIDER_SELF_ATTRIBUTION_BLOCKED=PASS   CHACHA_DEV_V628_VERIFIED_RESULT_TRUSTED_CONTEXT_INJECTION=PASS   CHACHA_DEV_V628_EVIDENCE_INGEST_REQUIRES_TRUSTED_PROOF=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V628_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
chmod 0755 "$CURRENT/dev-hub/adapters/platform-selftest-adapter.py"

stage guardian-coverage-bootstrap
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V628_GUARDIAN_COVERAGE=PASS"

stage real-run-controller-dispatch
PROJECT="v628-runtime-pilot-$STAMP"
TASK="artifact:platform-selftest"
mkdir -p "$WORK/evidence/$PROJECT" "$WORK/runs" "$WORK/state" "$WORK/transactions" "$WORK/locks" "$WORK/plans" "$WORK/health"

cat >"$WORK/raw-graph.json" <<JSON
{"schema":"chacha.dev/task-graph/v1","project":"$PROJECT","transition":"BUILD->VERIFY","tasks":[{
"id":"$TASK","kind":"artifact","description":"V6.28 trusted dispatch lineage read-only pilot",
"owner_role":"orchestrator","capabilities":["platform-selftest"],"permission":"read","depends_on":[],
"outputs":[{"type":"artifact","id":"platform-selftest"}],
"verification":{"mode":"machine","self_certification_allowed":false,"required_evidence":["source","digest"]},
"metadata":{"platform_selftest":{"action":"revision-proof"}}}]}
JSON
printf '%s\n' '{"contracts":[]}' >"$WORK/agent-contracts.json"
printf '%s\n' '{"contracts":[]}' >"$WORK/component-contracts.json"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/task-contract-binder.py"   --graph "$WORK/raw-graph.json"   --agent-contracts "$WORK/agent-contracts.json"   --component-contracts "$WORK/component-contracts.json"   --role-contracts "$CURRENT/dev-hub/config/guardian-role-contracts.v1.json"   --output "$WORK/bound-graph.json" >"$WORK/binder.out"

cat >"$WORK/registry.json" <<'JSON'
{"schema":"chacha.dev/capability-registry/v1","capabilities":{
"platform-selftest":{"providers":[{"id":"platform-selftest-runtime","status":"ADOPT"}]}
}}
JSON
cat >"$WORK/health.json" <<'JSON'
{"schema":"chacha.dev/provider-health-snapshot/v1","providers":{
"platform-selftest-runtime":{"state":"HEALTHY","source":"v628-live-pilot"}
}}
JSON
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/execution-scheduler.py"   --graph "$WORK/bound-graph.json" --registry "$WORK/registry.json" --health "$WORK/health.json"   --policy "$CURRENT/dev-hub/config/execution-scheduler.v1.json" --output "$WORK/plan.json" >"$WORK/scheduler.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/evidence-collector.py" init   --project "$PROJECT" --ledger "$WORK/evidence/$PROJECT/ledger.json" >"$WORK/ledger-init.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/run-controller.py"   --plan "$WORK/plan.json" --graph "$WORK/bound-graph.json" --ledger "$WORK/evidence/$PROJECT/ledger.json"   --policy "$CURRENT/dev-hub/config/run-controller.v1.json"   --adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json"   --output-dir "$WORK/runs" --execute >"$WORK/run-controller.out" 2>"$WORK/run-controller.stderr"
RUN_RECORD="$(grep '^RUN_RECORD=' "$WORK/run-controller.out" | tail -1 | cut -d= -f2-)"
[ -s "$RUN_RECORD" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=run_record_missing"; exit 2; }
RESULT="$(python3 - "$RUN_RECORD" "$TASK" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));task=sys.argv[2]
assert int((x.get("summary") or {}).get("succeeded") or 0)==1,x.get("summary")
for w in x.get("waves") or []:
  for t in w.get("tasks") or []:
    if t.get("task_id")==task:
      assert t.get("status")=="SUCCEEDED",t
      print(t["task_result"]);raise SystemExit(0)
raise SystemExit("V628_TASK_RESULT_MISSING")
PY
)"
[ -s "$RESULT" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=task_result_missing"; exit 2; }
python3 - "$RESULT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="OK",x
assert x.get("producer")=="platform-selftest-adapter",x
assert (x.get("verification") or {}).get("status")=="UNVERIFIED",x
assert "learning_context" not in x,x
print("CHACHA_DEV_V628_REAL_PROVIDER_RESULT_IMMUTABLE=PASS")
PY
echo "CHACHA_DEV_V628_REAL_RUN_CONTROLLER_DISPATCH=PASS"
echo "CHACHA_DEV_V628_REAL_GUARDIAN_BYPASS=NO"

stage project-control-independent-verification
python3 - "$CURRENT" "$WORK" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);work=Path(sys.argv[2])
def load(p):return json.load(open(p,encoding="utf-8"))
def save(p,x):p.write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")
sp=load(root/"dev-hub/config/control-plane-state.v1.json")
sp["storage"]["runtime_root"]=str(work/"state")
sp["storage"]["transaction_root"]=str(work/"transactions")
save(work/"control-plane-state.json",sp)
pc=load(root/"dev-hub/config/project-control.v1.json")
pc["runtime"].update({
 "state_root":str(work/"state"),"evidence_root":str(work/"evidence"),
 "plans_root":str(work/"plans"),"health_root":str(work/"health"),
 "runs_root":str(work/"runs"),"transactions_root":str(work/"transactions"),
 "locks_root":str(work/"locks")
})
pc["repository_paths"]["control_plane_state"]=str(work/"control-plane-state.json")
save(work/"project-control.json",pc)
PY
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/control-plane-store.py"   --policy "$WORK/control-plane-state.json" --root "$WORK/state" init   --project "$PROJECT" --actor v628-pilot >"$WORK/control-init.out"
env -u CHACHA_DEV_INDEPENDENT_RESULT PYTHONPATH="$CURRENT/dev-hub/bin"   python3 "$CURRENT/dev-hub/bin/project-control.py"   --policy "$WORK/project-control.json" --repo-root "$CURRENT" --json   verify-result --project "$PROJECT" --result "$RESULT" --graph "$WORK/bound-graph.json"   --method machine --verifier v628-independent-verifier --ingest   >"$WORK/project-control-verify.out" 2>"$WORK/project-control-verify.stderr"
VERIFIED="$(python3 - "$WORK/project-control-verify.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="OK",x
d=x.get("details") or {}
assert d.get("trusted_learning_context") is True,d
assert d.get("learning_context_status")=="TRUSTED_DISPATCH_CONTEXT",d
for a in x.get("artifacts") or []:
  if a.get("type")=="verified-task-result":
    print(a["path"]);raise SystemExit(0)
raise SystemExit("VERIFIED_RESULT_ARTIFACT_MISSING")
PY
)"
[ -s "$VERIFIED" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=verified_result_missing"; exit 2; }
python3 - "$VERIFIED" "$WORK/evidence/$PROJECT/ledger.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding="utf-8"));l=json.load(open(sys.argv[2],encoding="utf-8"))
ctx=v.get("learning_context") or {}
rows=ctx.get("component_lineage",{}).get("components") or []
assert ctx.get("surface_kind")=="trusted-dispatch-result",ctx
assert any(r.get("component_id")=="orchestrator" for r in rows),rows
assert any(r.get("component_id")=="platform-selftest-adapter" and r.get("kind")=="runtime" for r in rows),rows
e=l["history"][-1]
assert e.get("verification_status")=="VERIFIED",e
assert e.get("learning_eligibility")=="EXACT_LINEAGE",e
assert e.get("learning_context")==ctx,e
print("CHACHA_DEV_V628_REAL_TRUSTED_CONTEXT_INJECTION=PASS")
print("CHACHA_DEV_V628_REAL_EVIDENCE_LEDGER_TRUSTED_LINEAGE=PASS")
PY

stage verified-evidence-learning
mkdir -p "$WORK/learning-markers" "$WORK/learning-outbox" "$WORK/learning-state"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/verified-evidence-learning.py"   --ledger "$WORK/evidence/$PROJECT/ledger.json"   --marker-root "$WORK/learning-markers" --outbox-root "$WORK/learning-outbox" --state-root "$WORK/learning-state"   >"$WORK/learning.out" 2>"$WORK/learning.stderr"
grep -Fq 'CHACHA_DEV_V627_VERIFIED_EVIDENCE_LEARNING=PASS' "$WORK/learning.out"
DELTA="$(find "$WORK/learning-outbox" -maxdepth 1 -type f -name 'ld-*.json' | head -1)"
[ -s "$DELTA" ] || { echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=trusted_dispatch_delta_missing"; exit 2; }
python3 - "$DELTA" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
rows=(x.get("lineage") or {}).get("components") or []
assert (x.get("evaluation") or {}).get("verified") is True,x
assert (x.get("evaluation") or {}).get("outcome")=="PASS",x
assert any(r.get("component_id")=="platform-selftest-adapter" for r in rows),rows
assert any(r.get("component_id")=="orchestrator" for r in rows),rows
print("CHACHA_DEV_V628_REAL_DISPATCH_TO_LEARNING_DELTA=PASS")
PY

stage central-ingest
python3 "$CURRENT/dev-hub/bin/learning-delta-ingest.py"   --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db --delta "$DELTA" --nas >"$WORK/ingest.out"
python3 - "$WORK/ingest.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status") in {"RECORDED","DEDUPLICATED"},x
assert (x.get("nas") or {}).get("status")=="PERSISTED",x
print("CHACHA_DEV_V628_REAL_DELTA_NAS=PASS")
PY

stage feedback-confidence-memory
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-production-lineage-feedback.py" >"$WORK/feedback.out" 2>"$WORK/feedback.stderr"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-component-confidence.py" >"$WORK/confidence.out" 2>"$WORK/confidence.stderr"
python3 - "$CONFIDENCE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
rows={str(r.get("component_id")):r for r in x.get("items") or []}
a=rows.get("platform-selftest-adapter")
assert a is not None,rows.keys()
assert int(a.get("verified_success_count") or 0)>=1,a
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
print("CHACHA_DEV_V628_REAL_DISPATCH_CONFIDENCE_ATTRIBUTION=PASS")
PY
systemctl start chacha-dev-central-memory-assimilation.service
if systemctl is-failed --quiet chacha-dev-central-memory-assimilation.service; then
  echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=central_memory_refresh_failed"; exit 2
fi
python3 - "$MEMORY" "$CONFIDENCE" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"));c=json.load(open(sys.argv[2],encoding="utf-8"))
cc=m.get("component_confidence") or {}
assert cc.get("available") is True,cc
assert cc.get("snapshot_digest")==c.get("snapshot_digest"),(cc,c.get("snapshot_digest"))
print("CHACHA_DEV_V628_DISPATCH_LINEAGE_TO_CENTRAL_MEMORY=PASS")
PY

stage background-services
systemctl is-enabled --quiet chacha-dev-verified-evidence-learning.timer
systemctl start chacha-dev-verified-evidence-learning.service
if systemctl is-failed --quiet chacha-dev-verified-evidence-learning.service; then
  echo "CHACHA_DEV_V628_INSTALL=BLOCKED reason=v627_background_reconciler_regression"; exit 2
fi
echo "CHACHA_DEV_V628_BACKGROUND_RECONCILER_COMPATIBILITY=PASS"

cat >"/opt/chacha-dev/evidence/v628-trusted-dispatch-lineage-$STAMP.json" <<JSON
{"schema":"chacha.dev/v628-trusted-dispatch-lineage-evidence/v1","revision":"$REV","observed_at":"$STAMP",
"semantic_pilot":"PASS","guardian_coverage":"PASS","real_run_controller_dispatch":"PASS",
"provider_result_immutable":"PASS","trusted_context_injection":"PASS","evidence_ledger_lineage":"PASS",
"learning_delta":"PASS","delta_nas":"PASS","confidence_attribution":"PASS","central_memory":"PASS",
"automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V628_LEARNING_LINEAGE_CONTROLLER_OWNED=YES"
echo "CHACHA_DEV_V628_PROVIDER_SELF_ATTRIBUTION_ALLOWED=NO"
echo "CHACHA_DEV_V628_DYNAMIC_AGENT_BRANCH_FOUNDRY_LINEAGE=YES"
echo "CHACHA_DEV_V628_CONNECTOR_RUNTIME_LINEAGE=YES"
echo "CHACHA_DEV_V628_VERIFIED_CONTEXT_AFTER_INDEPENDENT_VERIFICATION=YES"
echo "CHACHA_DEV_V628_UNTRUSTED_CONTEXT_CONFIDENCE_CHANGE=NO"
echo "CHACHA_DEV_V628_EVIDENCE_LEDGER_FACTUAL_AUTHORITY=YES"
echo "CHACHA_DEV_V628_LEARNING_ADVISORY=YES"
echo "CHACHA_DEV_V628_TECHNOLOGY_REVALIDATION_REQUIRED=YES"
echo "CHACHA_DEV_V628_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V628_DIRECT_APPLICATION_MUTATION=NO"
echo "CHACHA_DEV_V628_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V628_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V628_INSTALL=PASS"

trap - EXIT
cleanup
