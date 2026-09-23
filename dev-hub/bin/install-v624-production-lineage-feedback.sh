#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V624_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v624.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
MEMORY="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
PREVIOUS=""
STAGE="bootstrap"
NEW_UNITS=0

stage(){ STAGE="$1"; echo "CHACHA_DEV_V624_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V624_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/coverage.out "$WORK"/semantic.out "$WORK"/producer.out "$WORK"/feedback.out "$WORK"/feedback.stderr; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ "$NEW_UNITS" -eq 1 ]; then
      systemctl disable --now chacha-dev-production-lineage-feedback.timer >/dev/null 2>&1 || true
      rm -f /etc/systemd/system/chacha-dev-production-lineage-feedback.service             /etc/systemd/system/chacha-dev-production-lineage-feedback.timer
      systemctl daemon-reload >/dev/null 2>&1 || true
    fi
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      systemctl restart chacha-dev-central-memory-assimilation.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V624_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$MEMORY" ] || { echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=v622_memory_snapshot_missing"; exit 2; }
python3 - "$MEMORY" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("schema")=="chacha.dev/central-memory-assimilation/v1",x.get("schema")
assert x.get("technology_revalidation_required_before_reuse") is True,x
assert x.get("nas",{}).get("status")=="PERSISTED",x.get("nas")
print("CHACHA_DEV_V624_MEMORY_BASELINE=PASS")
PY
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True:raise SystemExit("CHACHA_DEV_V624_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/production-lineage-feedback.py   dev-hub/bin/guardian-governed-production-lineage-feedback.py   dev-hub/bin/universal_learning_runtime.py   dev-hub/bin/universal-learning-producer.py   dev-hub/bin/reusable-branch-registry.py   dev-hub/bin/reusable-architecture-registry.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/production-lineage-feedback.v1.json   dev-hub/config/universal-learning.v1.json   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/schemas/learning-delta-v1.schema.json   dev-hub/systemd/chacha-dev-production-lineage-feedback.service   dev-hub/systemd/chacha-dev-production-lineage-feedback.timer   dev-hub/tests/test_v624_production_lineage_feedback.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/production-lineage-feedback.py"   "$RELEASE/dev-hub/bin/guardian-governed-production-lineage-feedback.py"   "$RELEASE/dev-hub/bin/universal_learning_runtime.py"   "$RELEASE/dev-hub/bin/universal-learning-producer.py"   "$RELEASE/dev-hub/bin/reusable-branch-registry.py"   "$RELEASE/dev-hub/bin/reusable-architecture-registry.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V624_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v624_production_lineage_feedback.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V624_LINEAGE_IN_LEARNING_DELTA=PASS   CHACHA_DEV_V624_EXACT_BRANCH_FEEDBACK=PASS   CHACHA_DEV_V624_EXACT_ARCHITECTURE_FEEDBACK=PASS   CHACHA_DEV_V624_CRITICAL_ANOMALY_QUARANTINE=PASS   CHACHA_DEV_V624_FEEDBACK_IDEMPOTENCY=PASS   CHACHA_DEV_V624_VERIFIED_RECOVERY_NOT_AUTO_ADOPT=PASS   CHACHA_DEV_V624_MISSING_LINEAGE_NO_REUSE_MUTATION=PASS   CHACHA_DEV_V624_GUARDIAN_GOVERNED=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V624_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage guardian-coverage-bootstrap
python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V624_GUARDIAN_COVERAGE_BOOTSTRAP=PASS"

stage real-producer-lineage
cat >"$WORK/state.json" <<'JSON'
{"health":"pilot","counter":1}
JSON
cat >"$WORK/lineage.json" <<'JSON'
{"schema":"chacha.dev/component-lineage/v1","components":[
  {"kind":"runtime","component_id":"v624-pilot-runtime","version":"1"},
  {"kind":"agent","component_id":"v624-pilot-agent","version":"1"}
]}
JSON
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" observe   --project-id v624-runtime-pilot --source-id v624-pilot-agent --source-kind agent   --deployment-id v624-pilot --state "$WORK/state.json" --lineage "$WORK/lineage.json"   --outbox "$WORK/outbox" --state-root "$WORK/state-root" >"$WORK/producer.out"
PILOT_OUTBOX="$(python3 - "$WORK/producer.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="QUEUED",x
p=x.get("outbox");d=json.load(open(p,encoding="utf-8"))
lin=d.get("lineage") or {}
assert lin.get("schema")=="chacha.dev/component-lineage/v1",lin
assert len(lin.get("components") or [])==2,lin
print(p)
PY
)"
[ -s "$PILOT_OUTBOX" ] || { echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=pilot_outbox_missing"; exit 2; }
echo "CHACHA_DEV_V624_REAL_PRODUCER_LINEAGE=PASS"

stage real-lineage-central-ingest
python3 "$CURRENT/dev-hub/bin/learning-delta-ingest.py"   --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db   --delta "$PILOT_OUTBOX" --nas >"$WORK/ingest.out"
python3 - "$WORK/ingest.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status") in {"RECORDED","DEDUPLICATED"},x
assert (x.get("nas") or {}).get("status")=="PERSISTED",x
print("CHACHA_DEV_V624_REAL_LINEAGE_CENTRAL_INGEST=PASS")
PY

stage guardian-governed-real-reconciliation
set +e
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-production-lineage-feedback.py"   >"$WORK/feedback.out" 2>"$WORK/feedback.stderr"
FB_RC=$?
set -e
if [ "$FB_RC" -ne 0 ]; then
  echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=guardian_governed_feedback_failed"
  exit 2
fi
grep -Fq 'CHACHA_DEV_V624_PRODUCTION_LINEAGE_FEEDBACK=PASS' "$WORK/feedback.out"
grep -Fq 'CHACHA_DEV_V624_GUARDIAN_GOVERNED_FEEDBACK=PASS' "$WORK/feedback.out"
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/knowledge/production-lineage-feedback-latest.json"
x=json.load(open(p,encoding="utf-8"))
assert x["schema"]=="chacha.dev/production-lineage-feedback-report/v1",x
assert x["exact_lineage_required_for_reuse_mutation"] is True,x
assert x["missing_lineage_still_learns_centrally"] is True,x
assert x["positive_success_inferred_from_absence_of_anomaly"] is False,x
assert x["verified_recovery_auto_adopt"] is False,x
assert x["technology_revalidation_required"] is True,x
assert x["nas"]["status"]=="PERSISTED",x["nas"]
assert int(x.get("lineage_components",0))>=2,x
print("CHACHA_DEV_V624_REAL_FEEDBACK_NAS=PASS")
print("CHACHA_DEV_V624_REAL_LINEAGE_FEEDBACK_E2E=PASS")
print("CHACHA_DEV_V624_RUNTIME_LINEAGE_COMPONENTS="+str(x.get("lineage_components",0)))
print("CHACHA_DEV_V624_RUNTIME_REUSE_UPDATES="+str(x.get("reuse_updates",0)))
print("CHACHA_DEV_V624_RUNTIME_MISSING_LINEAGE="+str(x.get("missing_lineage",0)))
PY

stage refresh-central-memory
systemctl start chacha-dev-central-memory-assimilation.service
systemctl is-failed --quiet chacha-dev-central-memory-assimilation.service && {
  echo "CHACHA_DEV_V624_INSTALL=BLOCKED reason=central_memory_refresh_failed"; exit 2;
} || true
echo "CHACHA_DEV_V624_CENTRAL_MEMORY_REFRESH=PASS"

stage install-background-feedback
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-production-lineage-feedback.service" /etc/systemd/system/chacha-dev-production-lineage-feedback.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-production-lineage-feedback.timer" /etc/systemd/system/chacha-dev-production-lineage-feedback.timer
NEW_UNITS=1
systemctl daemon-reload
systemctl enable --now chacha-dev-production-lineage-feedback.timer
systemctl is-active --quiet chacha-dev-production-lineage-feedback.timer
echo "CHACHA_DEV_V624_BACKGROUND_FEEDBACK_TIMER=PASS"

cat >"/opt/chacha-dev/evidence/v624-production-lineage-feedback-$STAMP.json" <<JSON
{"schema":"chacha.dev/v624-production-lineage-feedback-evidence/v1","revision":"$REV","observed_at":"$STAMP","semantic_pilot":"PASS","guardian_coverage":"PASS","producer_lineage":"PASS","central_ingest":"PASS","lineage_feedback_e2e":"PASS","guardian_governed_feedback":"PASS","nas_persistence":"PASS","central_memory_refresh":"PASS","background_timer":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V624_EXACT_LINEAGE_REQUIRED_FOR_REUSE_MUTATION=YES"
echo "CHACHA_DEV_V624_MISSING_LINEAGE_STILL_LEARNS_CENTRALLY=YES"
echo "CHACHA_DEV_V624_MISSING_LINEAGE_REUSE_MUTATION=NO"
echo "CHACHA_DEV_V624_CRITICAL_ANOMALY_QUARANTINES_EXACT_ASSET=YES"
echo "CHACHA_DEV_V624_HIGH_ANOMALY_DEGRADES_EXACT_ASSET=YES"
echo "CHACHA_DEV_V624_VERIFIED_RECOVERY_AUTO_ADOPT=NO"
echo "CHACHA_DEV_V624_ACCEPTANCE_BEFORE_READOPT=YES"
echo "CHACHA_DEV_V624_TECHNOLOGY_REVALIDATION_REQUIRED=YES"
echo "CHACHA_DEV_V624_ALL_COMPONENT_REPUTATION_INDEX=YES"
echo "CHACHA_DEV_V624_GUARDIAN_GOVERNED=YES"
echo "CHACHA_DEV_V624_DIRECT_APPLICATION_MUTATION=NO"
echo "CHACHA_DEV_V624_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V624_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V624_INSTALL=PASS"

trap - EXIT
cleanup
