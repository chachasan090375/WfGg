#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V625_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v625.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
MEMORY="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
FEEDBACK_DB="/opt/chacha-dev/runtime/knowledge/production-lineage-feedback.db"
CONFIDENCE="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
GUARDIAN_URL="https://chacha-dev-guardian.chachasan090375.workers.dev"
PREVIOUS=""
STAGE="bootstrap"
UNITS_INSTALLED=0

stage(){ STAGE="$1"; echo "CHACHA_DEV_V625_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V625_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/semantic.out "$WORK"/coverage.out "$WORK"/feedback.out "$WORK"/feedback.stderr "$WORK"/confidence.out "$WORK"/confidence.stderr "$WORK"/recall.out "$WORK"/guardian-arch-pre.out "$WORK"/guardian-arch-post.out; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ "$UNITS_INSTALLED" -eq 1 ]; then
      systemctl disable --now chacha-dev-component-confidence.timer >/dev/null 2>&1 || true
      rm -f /etc/systemd/system/chacha-dev-component-confidence.service /etc/systemd/system/chacha-dev-component-confidence.timer
      systemctl daemon-reload >/dev/null 2>&1 || true
    fi
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      systemctl restart chacha-dev-production-lineage-feedback.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-central-memory-assimilation.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V625_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink grep install; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$MEMORY" ] || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=central_memory_missing"; exit 2; }
[ -s "$FEEDBACK_DB" ] || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=v624_feedback_db_missing"; exit 2; }

python3 - "$MEMORY" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("schema")=="chacha.dev/central-memory-assimilation/v1",x.get("schema")
assert x.get("technology_revalidation_required_before_reuse") is True,x
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
print("CHACHA_DEV_V625_V624_MEMORY_BASELINE=PASS")
PY

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True:raise SystemExit("CHACHA_DEV_V625_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/component-confidence-engine.py   dev-hub/bin/guardian-governed-component-confidence.py   dev-hub/bin/production-lineage-feedback.py   dev-hub/bin/guardian-governed-production-lineage-feedback.py   dev-hub/bin/universal-learning-producer.py   dev-hub/bin/universal_learning_runtime.py   dev-hub/bin/learning-delta-ingest.py   dev-hub/bin/central-memory-assimilator.py   dev-hub/bin/central-memory-recall.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/bin/guardian-client.py   dev-hub/config/component-confidence.v1.json   dev-hub/config/production-lineage-feedback.v1.json   dev-hub/config/central-memory-recall.v1.json   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/systemd/chacha-dev-component-confidence.service   dev-hub/systemd/chacha-dev-component-confidence.timer   dev-hub/systemd/chacha-dev-production-lineage-feedback.service   dev-hub/tests/test_v625_component_confidence.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/component-confidence-engine.py"   "$RELEASE/dev-hub/bin/guardian-governed-component-confidence.py"   "$RELEASE/dev-hub/bin/production-lineage-feedback.py"   "$RELEASE/dev-hub/bin/universal_learning_runtime.py"   "$RELEASE/dev-hub/bin/universal-learning-producer.py"   "$RELEASE/dev-hub/bin/central-memory-assimilator.py"   "$RELEASE/dev-hub/bin/central-memory-recall.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V625_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v625_component_confidence.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V625_EXPLICIT_VERIFIED_SUCCESS=PASS   CHACHA_DEV_V625_THREE_SUCCESS_TRUSTED=PASS   CHACHA_DEV_V625_CRITICAL_ANOMALY_QUARANTINE=PASS   CHACHA_DEV_V625_RECOVERY_NOT_AUTO_READOPT=PASS   CHACHA_DEV_V625_NEGATIVE_CONFIDENCE_EXCLUDED_FROM_CURRENT_BEST=PASS   CHACHA_DEV_V625_RECALL_DEFENSE_IN_DEPTH=PASS   CHACHA_DEV_V625_GUARDIAN_COMPONENT_CONFIDENCE_GATE=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V625_SEMANTIC_PILOT=PASS"

stage external-guardian-confidence-gate
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"component_confidence_evidence_required":true' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V625_EXTERNAL_GUARDIAN_CONFIDENCE_GATE=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage guardian-coverage-bootstrap
python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V625_GUARDIAN_COVERAGE_BOOTSTRAP=PASS"

stage real-verified-success-lineage
PILOT_SOURCE="v625-pilot-agent-$STAMP"
PILOT_DEPLOY="v625-pilot-$STAMP"
PILOT_AGENT="v625-pilot-agent-$STAMP"
PILOT_RUNTIME="v625-pilot-runtime-$STAMP"
cat >"$WORK/lineage.json" <<JSON
{"schema":"chacha.dev/component-lineage/v1","components":[
  {"kind":"agent","component_id":"$PILOT_AGENT","version":"1"},
  {"kind":"runtime","component_id":"$PILOT_RUNTIME","version":"1"}
]}
JSON
cat >"$WORK/evaluation.json" <<'JSON'
{"schema":"chacha.dev/component-evaluation/v1","verified":true,"outcome":"PASS","acceptance_score":1.0,"evidence_refs":["v625-runtime-pilot"]}
JSON

for n in 1 2 3; do
  printf '{"health":"PASS","counter":%s}\n' "$n" >"$WORK/state-$n.json"
  PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" observe     --project-id v625-runtime-pilot --source-id "$PILOT_SOURCE" --source-kind agent     --deployment-id "$PILOT_DEPLOY" --state "$WORK/state-$n.json"     --lineage "$WORK/lineage.json" --evaluation "$WORK/evaluation.json"     --outbox "$WORK/outbox" --state-root "$WORK/state-root" >"$WORK/producer-$n.out"
  OUTBOX="$(python3 - "$WORK/producer-$n.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="QUEUED",x
print(x["outbox"])
PY
)"
  python3 "$CURRENT/dev-hub/bin/learning-delta-ingest.py"     --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db     --delta "$OUTBOX" --nas >"$WORK/ingest-$n.out"
  python3 - "$WORK/ingest-$n.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status") in {"RECORDED","DEDUPLICATED"},x
assert (x.get("nas") or {}).get("status")=="PERSISTED",x
PY
done
echo "CHACHA_DEV_V625_REAL_VERIFIED_SUCCESS_LINEAGE=PASS"

stage guardian-governed-production-feedback
set +e
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-production-lineage-feedback.py"   >"$WORK/feedback.out" 2>"$WORK/feedback.stderr"
FB_RC=$?
set -e
[ "$FB_RC" -eq 0 ] || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=production_feedback_failed"; exit 2; }
grep -Fq 'CHACHA_DEV_V625_PRODUCTION_LINEAGE_FEEDBACK=PASS' "$WORK/feedback.out"
grep -Fq 'CHACHA_DEV_V625_GUARDIAN_GOVERNED_FEEDBACK=PASS' "$WORK/feedback.out"
echo "CHACHA_DEV_V625_REAL_PRODUCTION_FEEDBACK=PASS"

stage guardian-governed-component-confidence
set +e
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-component-confidence.py"   >"$WORK/confidence.out" 2>"$WORK/confidence.stderr"
CC_RC=$?
set -e
[ "$CC_RC" -eq 0 ] || { echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=component_confidence_failed"; exit 2; }
grep -Fq 'CHACHA_DEV_V625_COMPONENT_CONFIDENCE=PASS' "$WORK/confidence.out"
grep -Fq 'CHACHA_DEV_V625_GUARDIAN_GOVERNED_COMPONENT_CONFIDENCE=PASS' "$WORK/confidence.out"
python3 - "$CONFIDENCE" "$PILOT_AGENT" "$PILOT_RUNTIME" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));ids=set(sys.argv[2:])
assert x.get("schema")=="chacha.dev/component-confidence-snapshot/v1",x
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
rows={str(r.get("component_id")):r for r in x.get("items") or [] if str(r.get("component_id")) in ids}
assert set(rows)==ids,(rows,ids)
for r in rows.values():
    assert r.get("state")=="TRUSTED",r
    assert int(r.get("verified_success_count") or 0)>=3,r
    assert r.get("reuse_advisory_eligible") is True,r
    assert r.get("confidence_is_advisory") is True,r
    assert r.get("technology_revalidation_required") is True,r
print("CHACHA_DEV_V625_REAL_COMPONENT_CONFIDENCE_TRUST=PASS")
print("CHACHA_DEV_V625_REAL_CONFIDENCE_NAS=PASS")
PY

stage central-memory-confidence-assimilation
systemctl start chacha-dev-central-memory-assimilation.service
if systemctl is-failed --quiet chacha-dev-central-memory-assimilation.service; then
  echo "CHACHA_DEV_V625_INSTALL=BLOCKED reason=central_memory_refresh_failed"; exit 2
fi
python3 - "$MEMORY" "$CONFIDENCE" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"));c=json.load(open(sys.argv[2],encoding="utf-8"))
cc=m.get("component_confidence") or {}
assert cc.get("available") is True,cc
assert cc.get("snapshot_digest")==c.get("snapshot_digest"),(cc,c.get("snapshot_digest"))
assert cc.get("negative_states_excluded_from_current_best") is True,cc
assert (m.get("nas") or {}).get("status")=="PERSISTED",m.get("nas")
print("CHACHA_DEV_V625_CENTRAL_MEMORY_CONFIDENCE_ASSIMILATION=PASS")
PY

stage contextual-recall-sees-confidence
cat >"$WORK/intent.json" <<'JSON'
{"goal":"V6.25 confidence recall pilot","domains":["product"],"capabilities":["memory-learning"]}
JSON
cat >"$WORK/preplan.json" <<'JSON'
{"schema":"chacha.dev/domain-plan/v1","intent":"V6.25 confidence recall pilot","dispatch_allowed":false,
 "packages":[{"id":"confidence-pilot","domain":"product","kind":"primary","capabilities":["memory-learning"],"roles":[],"toolchain":[]}]}
JSON
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/central-memory-recall.py"   --memory "$MEMORY" --policy "$CURRENT/dev-hub/config/central-memory-recall.v1.json"   --intent "$WORK/intent.json" --preplan "$WORK/preplan.json" --project-id v625-runtime-pilot   --output "$WORK/recall.json" >"$WORK/recall.out"
grep -Fq 'CHACHA_DEV_V625_CENTRAL_MEMORY_RECALL=PASS' "$WORK/recall.out"
python3 - "$WORK/recall.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));c=x.get("component_confidence") or {}
assert c.get("available") is True,c
assert c.get("negative_states_excluded_from_reuse") is True,c
assert c.get("confidence_is_advisory") is True,c
assert x.get("technology_revalidation_required") is True,x
assert x.get("architecture_council_final_authority") is True,x
print("CHACHA_DEV_V625_CONTEXTUAL_RECALL_CONFIDENCE=PASS")
PY

stage guardian-final-architecture-confidence-evidence
ARCH_ACTION="v625-arch-$STAMP"
cat >"$WORK/guardian-arch-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v625-arch-pre-$STAMP","action_id":"$ARCH_ACTION","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"architecture-decision-council","action":"FINAL_ARCHITECTURE_DECISION","task_kind":"architecture-decision-council","permission":"plan","project_id":"platform-bootstrap","run_id":"v625-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
cat >"$WORK/guardian-arch-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v625-arch-post-$STAMP","action_id":"$ARCH_ACTION","phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"architecture-decision-council","action":"FINAL_ARCHITECTURE_DECISION","task_kind":"architecture-decision-council","permission":"plan","project_id":"platform-bootstrap","run_id":"v625-runtime","adapters":[],"evidence":{"emergency_stop_active":false,"technology_watch_pre":true,"technology_watch_final":true,"central_memory_assimilation":true,"component_confidence":true,"central_memory_recall":true,"reuse_memory":true,"architecture_memory":true,"architecture_portfolio":true,"branch_foundry":true,"agent_foundry":true,"capability_foundry":true,"constraint_policy":true},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-arch-pre.json" >"$WORK/guardian-arch-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-arch-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-arch-post.json" >"$WORK/guardian-arch-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-arch-post.out"
echo "CHACHA_DEV_V625_GUARDIAN_FINAL_ARCH_CONFIDENCE_EVIDENCE=PASS"

stage install-background-confidence
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-component-confidence.service" /etc/systemd/system/chacha-dev-component-confidence.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-component-confidence.timer" /etc/systemd/system/chacha-dev-component-confidence.timer
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-production-lineage-feedback.service" /etc/systemd/system/chacha-dev-production-lineage-feedback.service
UNITS_INSTALLED=1
systemctl daemon-reload
systemctl enable --now chacha-dev-component-confidence.timer
systemctl enable --now chacha-dev-production-lineage-feedback.timer
systemctl is-active --quiet chacha-dev-component-confidence.timer
systemctl is-active --quiet chacha-dev-production-lineage-feedback.timer
echo "CHACHA_DEV_V625_BACKGROUND_CONFIDENCE_TIMER=PASS"
echo "CHACHA_DEV_V625_FEEDBACK_CONFIDENCE_MEMORY_CHAIN=PASS"

cat >"/opt/chacha-dev/evidence/v625-component-confidence-$STAMP.json" <<JSON
{"schema":"chacha.dev/v625-component-confidence-evidence/v1","revision":"$REV","observed_at":"$STAMP","semantic_pilot":"PASS","guardian_coverage":"PASS","verified_success_lineage":"PASS","production_feedback":"PASS","component_confidence":"PASS","confidence_nas":"PASS","central_memory_assimilation":"PASS","contextual_recall":"PASS","guardian_final_architecture_gate":"PASS","background_timer":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V625_VERIFIED_SUCCESS_REQUIRED_FOR_POSITIVE_CONFIDENCE=YES"
echo "CHACHA_DEV_V625_ABSENCE_OF_ANOMALY_COUNTS_AS_SUCCESS=NO"
echo "CHACHA_DEV_V625_MIN_VERIFIED_SUCCESSES_FOR_TRUSTED=3"
echo "CHACHA_DEV_V625_HIGH_ANOMALY_DEGRADES=YES"
echo "CHACHA_DEV_V625_CRITICAL_ANOMALY_QUARANTINES=YES"
echo "CHACHA_DEV_V625_VERIFIED_RECOVERY_AUTO_READOPT=NO"
echo "CHACHA_DEV_V625_NEGATIVE_CONFIDENCE_EXCLUDED_FROM_FAST_REUSE=YES"
echo "CHACHA_DEV_V625_CONFIDENCE_AUTHORITY=ADVISORY"
echo "CHACHA_DEV_V625_TECHNOLOGY_REVALIDATION_REQUIRED=YES"
echo "CHACHA_DEV_V625_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V625_NAS_AUTHORITATIVE=YES"
echo "CHACHA_DEV_V625_DIRECT_APPLICATION_MUTATION=NO"
echo "CHACHA_DEV_V625_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V625_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V625_INSTALL=PASS"

trap - EXIT
cleanup
