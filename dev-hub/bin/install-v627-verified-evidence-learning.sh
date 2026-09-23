#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V627_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v627.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
CONFIDENCE="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
MEMORY="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
MARKERS="/opt/chacha-dev/runtime/knowledge/verified-evidence-learning-applied"
OUTBOX="/opt/chacha-dev/runtime/learning/outbox"
STATE="/opt/chacha-dev/runtime/learning/producer-state"
UNIT_SERVICE="/etc/systemd/system/chacha-dev-verified-evidence-learning.service"
UNIT_TIMER="/etc/systemd/system/chacha-dev-verified-evidence-learning.timer"
PREVIOUS=""
STAGE="bootstrap"
UNITS_INSTALLED=0

stage(){ STAGE="$1"; echo "CHACHA_DEV_V627_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V627_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ "$UNITS_INSTALLED" = 1 ]; then
      systemctl disable --now chacha-dev-verified-evidence-learning.timer >/dev/null 2>&1 || true
      rm -f "$UNIT_SERVICE" "$UNIT_TIMER"
      systemctl daemon-reload >/dev/null 2>&1 || true
    fi
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      systemctl restart chacha-dev-production-lineage-feedback.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-component-confidence.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-central-memory-assimilation.timer >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V627_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink grep cp; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$CONFIDENCE" ] || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=v625_confidence_snapshot_missing"; exit 2; }
[ -f "$CURRENT/dev-hub/bin/acceptance-confidence-bridge.py" ] || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=v626_acceptance_bridge_missing"; exit 2; }
python3 - "$CONFIDENCE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("schema")=="chacha.dev/component-confidence-snapshot/v1",x.get("schema")
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
assert x.get("confidence_is_advisory_not_final_authority") is True,x
assert x.get("technology_revalidation_required") is True,x
print("CHACHA_DEV_V627_V626_BASELINE=PASS")
PY
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True:raise SystemExit("CHACHA_DEV_V627_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
for required in   dev-hub/bin/verified-evidence-learning.py   dev-hub/bin/evidence-collector.py   dev-hub/bin/universal_learning_runtime.py   dev-hub/bin/learning-delta-ingest.py   dev-hub/bin/guardian-governed-production-lineage-feedback.py   dev-hub/bin/guardian-governed-component-confidence.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/verified-evidence-learning.v1.json   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/systemd/chacha-dev-verified-evidence-learning.service   dev-hub/systemd/chacha-dev-verified-evidence-learning.timer   dev-hub/tests/test_v627_verified_evidence_learning.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence "$MARKERS" "$OUTBOX" "$STATE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/verified-evidence-learning.py"   "$RELEASE/dev-hub/bin/evidence-collector.py"
python3 -m json.tool "$RELEASE/dev-hub/config/verified-evidence-learning.v1.json" >/dev/null
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V627_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  CHACHA_DEV_TEST_GUARDIAN_BYPASS=1 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v627_verified_evidence_learning.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V627_EVIDENCE_LEDGER_LEARNING_CONTEXT=PASS   CHACHA_DEV_V627_VERIFIED_SUCCESS_AUTO_DELTA=PASS   CHACHA_DEV_V627_EXACT_LINEAGE_REQUIRED_FOR_CONFIDENCE=PASS   CHACHA_DEV_V627_MISSING_LINEAGE_NO_CONFIDENCE_NO_PENALTY=PASS   CHACHA_DEV_V627_IDEMPOTENT_RECONCILIATION=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V627_SEMANTIC_PILOT=PASS"
echo "CHACHA_DEV_V627_SEMANTIC_GUARDIAN_BYPASS=TEST_ONLY"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage install-background-reconciler
cp "$CURRENT/dev-hub/systemd/chacha-dev-verified-evidence-learning.service" "$UNIT_SERVICE"
cp "$CURRENT/dev-hub/systemd/chacha-dev-verified-evidence-learning.timer" "$UNIT_TIMER"
chmod 0644 "$UNIT_SERVICE" "$UNIT_TIMER"
systemctl daemon-reload
UNITS_INSTALLED=1
echo "CHACHA_DEV_V627_BACKGROUND_RECONCILER_STAGED=PASS"

stage guardian-coverage-bootstrap
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V627_GUARDIAN_COVERAGE=PASS"

stage real-verified-evidence-learning
PILOT_PROJECT="v627-runtime-pilot-$STAMP"
PILOT_DEPLOY="v627-deployment-$STAMP"
PILOT_AGENT="v627-evidence-agent-$STAMP"
PILOT_BRANCH="v627-evidence-branch-$STAMP"
EVIDENCE_DIR="/opt/chacha-dev/runtime/evidence/$PILOT_PROJECT"
LEDGER="$EVIDENCE_DIR/ledger.json"
mkdir -p "$EVIDENCE_DIR"
cat >"$WORK/graph.json" <<JSON
{"schema":"chacha.dev/task-graph/v1","project":"$PILOT_PROJECT","transition":"VERIFY->PREVIEW","tasks":[{
"id":"artifact:test-result","kind":"artifact","owner_role":"testing","permission":"read","depends_on":[],
"outputs":[{"type":"artifact","id":"test-result"}],
"verification":{"mode":"machine","self_certification_allowed":false}
}]}
JSON
cat >"$WORK/result.json" <<JSON
{"schema":"chacha.dev/task-result/v1","project":"$PILOT_PROJECT","task_id":"artifact:test-result",
"status":"OK","producer":"v627-runtime-test-runner","observed_at":"$STAMP",
"evidence":[{"kind":"report","source":"v627-runtime-proof","digest":"sha256:1111111111111111111111111111111111111111111111111111111111111111"}],
"verification":{"status":"VERIFIED","method":"machine","verifier":"v627-independent-verifier"},
"outputs":[{"type":"artifact","id":"test-result","status":"OK"}],
"learning_context":{"schema":"chacha.dev/verified-evidence-learning-context/v1",
"deployment_id":"$PILOT_DEPLOY","source_id":"v627-real-evidence-surface","surface_kind":"qualification",
"evidence_refs":["v627:real:qualification"],
"component_lineage":{"schema":"chacha.dev/component-lineage/v1","components":[
{"kind":"agent","component_id":"$PILOT_AGENT","version":"1"},
{"kind":"branch","component_id":"$PILOT_BRANCH","version":"1"}]}}}
JSON
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/evidence-collector.py" init --project "$PILOT_PROJECT" --ledger "$LEDGER" >"$WORK/evidence-init.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/evidence-collector.py" ingest --graph "$WORK/graph.json" --result "$WORK/result.json" --ledger "$LEDGER" >"$WORK/evidence-ingest.out"
python3 - "$LEDGER" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));e=x["history"][-1]
assert e.get("verification_status")=="VERIFIED",e
assert e.get("learning_eligibility")=="EXACT_LINEAGE",e
assert (e.get("learning_context") or {}).get("component_lineage"),e
print("CHACHA_DEV_V627_REAL_EVIDENCE_LEDGER_CONTEXT=PASS")
PY

PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/verified-evidence-learning.py" --ledger "$LEDGER" >"$WORK/reconcile-1.out"
grep -Fq 'CHACHA_DEV_V627_VERIFIED_EVIDENCE_LEARNING=PASS' "$WORK/reconcile-1.out"
python3 - "$WORK/reconcile-1.out" <<'PY'
import json,sys
lines=open(sys.argv[1],encoding="utf-8").read().splitlines()
payload=json.loads("\n".join(x for x in lines if not x.startswith("CHACHA_DEV_V627_")))
assert payload.get("queued")==1,payload
print("CHACHA_DEV_V627_REAL_VERIFIED_SUCCESS_AUTO_DELTA=PASS")
PY
DELTA="$(PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$CURRENT" "$LEDGER" "$MARKERS" <<'PY'
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);ledger=json.load(open(sys.argv[2],encoding="utf-8"));event=ledger["history"][-1]
spec=importlib.util.spec_from_file_location("v627",root/"dev-hub/bin/verified-evidence-learning.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
key=m.digest({"project_id":ledger["project"],"result_digest":event["result_digest"],"learning_context":event["learning_context"]})
marker=json.load(open(Path(sys.argv[3])/(key+".json"),encoding="utf-8"))
print(marker["outbox"])
PY
)"
[ -s "$DELTA" ] || { echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=verified_delta_missing"; exit 2; }
echo "CHACHA_DEV_V627_REAL_GUARDIAN_BYPASS=NO"

stage real-idempotency
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/verified-evidence-learning.py" --ledger "$LEDGER" >"$WORK/reconcile-2.out"
python3 - "$WORK/reconcile-2.out" <<'PY'
import json,sys
lines=open(sys.argv[1],encoding="utf-8").read().splitlines()
payload=json.loads("\n".join(x for x in lines if not x.startswith("CHACHA_DEV_V627_")))
assert payload.get("queued")==0,payload
assert payload.get("deduplicated")==1,payload
print("CHACHA_DEV_V627_REAL_IDEMPOTENCY=PASS")
PY

stage central-ingest
python3 "$CURRENT/dev-hub/bin/learning-delta-ingest.py" --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db --delta "$DELTA" --nas >"$WORK/ingest.out"
python3 - "$WORK/ingest.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status") in {"RECORDED","DEDUPLICATED"},x
assert (x.get("nas") or {}).get("status")=="PERSISTED",x
print("CHACHA_DEV_V627_REAL_DELTA_NAS=PASS")
PY

stage feedback-confidence-memory
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-production-lineage-feedback.py" >"$WORK/feedback.out" 2>"$WORK/feedback.stderr"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-component-confidence.py" >"$WORK/confidence.out" 2>"$WORK/confidence.stderr"
python3 - "$CONFIDENCE" "$PILOT_AGENT" "$PILOT_BRANCH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));ids=set(sys.argv[2:])
rows={str(r.get("component_id")):r for r in x.get("items") or [] if str(r.get("component_id")) in ids}
assert set(rows)==ids,(rows,ids)
for r in rows.values():
    assert int(r.get("verified_success_count") or 0)>=1,r
    assert r.get("state")=="PROVISIONAL",r
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
print("CHACHA_DEV_V627_REAL_CONFIDENCE_ATTRIBUTION=PASS")
PY
systemctl start chacha-dev-central-memory-assimilation.service
if systemctl is-failed --quiet chacha-dev-central-memory-assimilation.service; then
  echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=central_memory_refresh_failed"; exit 2
fi
python3 - "$MEMORY" "$CONFIDENCE" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"));c=json.load(open(sys.argv[2],encoding="utf-8"))
cc=m.get("component_confidence") or {}
assert cc.get("available") is True,cc
assert cc.get("snapshot_digest")==c.get("snapshot_digest"),(cc,c.get("snapshot_digest"))
print("CHACHA_DEV_V627_VERIFIED_EVIDENCE_TO_CENTRAL_MEMORY=PASS")
PY

stage background-reconciler-enable
systemctl enable --now chacha-dev-verified-evidence-learning.timer
systemctl is-enabled --quiet chacha-dev-verified-evidence-learning.timer
systemctl start chacha-dev-verified-evidence-learning.service
if systemctl is-failed --quiet chacha-dev-verified-evidence-learning.service; then
  echo "CHACHA_DEV_V627_INSTALL=BLOCKED reason=background_reconciler_failed"; exit 2
fi
echo "CHACHA_DEV_V627_BACKGROUND_RECONCILER_TIMER=PASS"

cat >"/opt/chacha-dev/evidence/v627-verified-evidence-learning-$STAMP.json" <<JSON
{"schema":"chacha.dev/v627-verified-evidence-learning-evidence/v1","revision":"$REV","observed_at":"$STAMP",
"semantic_pilot":"PASS","guardian_coverage":"PASS","real_verified_success_auto_delta":"PASS",
"idempotency":"PASS","delta_nas":"PASS","exact_confidence_attribution":"PASS",
"central_memory":"PASS","background_reconciler_timer":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V627_VERIFIED_EVIDENCE_AUTO_LEARNING=YES"
echo "CHACHA_DEV_V627_EXACT_COMPONENT_LINEAGE_REQUIRED_FOR_CONFIDENCE=YES"
echo "CHACHA_DEV_V627_MISSING_LINEAGE_CONFIDENCE_CHANGE=NO"
echo "CHACHA_DEV_V627_MISSING_LINEAGE_PENALTY=NO"
echo "CHACHA_DEV_V627_EVIDENCE_LEDGER_FACTUAL_AUTHORITY=YES"
echo "CHACHA_DEV_V627_LEARNING_ADVISORY=YES"
echo "CHACHA_DEV_V627_TECHNOLOGY_REVALIDATION_REQUIRED=YES"
echo "CHACHA_DEV_V627_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V627_DIRECT_APPLICATION_MUTATION=NO"
echo "CHACHA_DEV_V627_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V627_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V627_INSTALL=PASS"

trap - EXIT
cleanup
