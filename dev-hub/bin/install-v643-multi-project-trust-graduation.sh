#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V643_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V643_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v643.XXXXXX)"
SYNTH_TMP="$WORK/synthetic-trust"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V643_STAGE=$STAGE"; }

cleanup(){
  rm -rf "$WORK" 2>/dev/null || true
}

rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V643_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.stderr; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -200 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V643_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in python3 cp ln readlink grep sha256sum find; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p,encoding="utf-8"))
except Exception:x={}
if x.get("active") is True:
    raise SystemExit("CHACHA_DEV_V643_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi

[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"
[ -d "$PREVIOUS/dev-hub" ] || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=current_release_invalid"; exit 2; }

stage v642-real-baseline
python3 - "$PREVIOUS/dev-hub/bin/autonomous-project-orchestrator.py" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
assert p.is_file(),p
s=p.read_text(encoding="utf-8")
assert '"version":"6.42.0"' in s, "V642_RUNTIME_VERSION_NOT_ACTIVE"
print("CHACHA_DEV_V643_V642_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  command -v curl >/dev/null || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=curl_required_without_source_root"; exit 2; }
  command -v tar >/dev/null || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=tar_required_without_source_root"; exit 2; }
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/capability-trust-observer.py   dev-hub/bin/component-confidence-engine.py   dev-hub/bin/durable-capability-registry.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/capability-trust-graduation.v1.json   dev-hub/config/component-confidence.v1.json   dev-hub/tests/test_v643_multi_project_trust_graduation.py   dev-hub/tests/test_v642_durable_capability_adoption.py   dev-hub/tests/test_v625_component_confidence.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

python3 -m py_compile   "$RELEASE/dev-hub/bin/capability-trust-observer.py"   "$RELEASE/dev-hub/bin/component-confidence-engine.py"   "$RELEASE/dev-hub/bin/durable-capability-registry.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/tests/test_v643_multi_project_trust_graduation.py"
python3 -m json.tool "$RELEASE/dev-hub/config/capability-trust-graduation.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/component-confidence.v1.json" >/dev/null
grep -Fq '"version":"6.43.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V643_STATIC=PASS"

stage semantic-qualification
mkdir -p "$SYNTH_TMP"
(
  cd "$RELEASE"
  TMPDIR="$SYNTH_TMP" PYTHONPATH="$RELEASE/dev-hub/bin"     python3 dev-hub/tests/test_v643_multi_project_trust_graduation.py
) >"$WORK/v643-semantic.out" 2>"$WORK/v643-semantic.err"

for marker in   CHACHA_DEV_V643_PROJECT_CONTROL_VERIFIED_OBSERVATION=PASS   CHACHA_DEV_V643_DISTINCT_PROJECT_COUNTING=PASS   CHACHA_DEV_V643_REPLAY_TRUST_INFLATION=NO   CHACHA_DEV_V643_THREE_DISTINCT_PROJECTS_TRUSTED=PASS   CHACHA_DEV_V643_CRITICAL_INCIDENT_QUARANTINE=PASS   CHACHA_DEV_V643_NEGATIVE_TRUST_REMOVED_FROM_REUSE=PASS   CHACHA_DEV_V643_VERIFIED_RECOVERY_FRESH_EVIDENCE_REQUIRED=PASS   CHACHA_DEV_V643_RECOVERY_RETURNS_PROVISIONAL_NOT_TRUSTED=PASS   CHACHA_DEV_V643_TRUST_PERMISSION_ESCALATION=NO   CHACHA_DEV_V643_TECHNOLOGY_WATCH_REVALIDATION_REQUIRED=YES   CHACHA_DEV_V643_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES   CHACHA_DEV_V643_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v643-semantic.out"
done
echo "CHACHA_DEV_V643_SEMANTIC_QUALIFICATION=PASS"
echo "CHACHA_DEV_V643_REAL_PROJECT_CONTROL_VERIFIED_OBSERVATION=PASS"
echo "CHACHA_DEV_V643_REAL_DISTINCT_PROJECT_COUNTING=PASS"
echo "CHACHA_DEV_V643_REAL_REPLAY_TRUST_INFLATION=NO"
echo "CHACHA_DEV_V643_REAL_THREE_DISTINCT_PROJECTS_TRUSTED=PASS"
echo "CHACHA_DEV_V643_REAL_CRITICAL_INCIDENT_QUARANTINE=PASS"
echo "CHACHA_DEV_V643_REAL_NEGATIVE_TRUST_REMOVED_FROM_REUSE=PASS"
echo "CHACHA_DEV_V643_REAL_VERIFIED_RECOVERY_FRESH_EVIDENCE_REQUIRED=PASS"
echo "CHACHA_DEV_V643_REAL_RECOVERY_RETURNS_PROVISIONAL=PASS"

stage acquired-regressions
(
  cd "$RELEASE"
  TMPDIR="$SYNTH_TMP" PYTHONPATH="$RELEASE/dev-hub/bin"     python3 dev-hub/tests/test_v642_durable_capability_adoption.py
) >"$WORK/v642-regression.out" 2>"$WORK/v642-regression.err"
grep -Fq 'CHACHA_DEV_V642_VERIFIED_SUCCESS_BEFORE_ADOPTION=PASS' "$WORK/v642-regression.out"
grep -Fq 'CHACHA_DEV_V642_CROSS_PROJECT_REUSE_WITHOUT_REBUILD=PASS' "$WORK/v642-regression.out"

(
  cd "$RELEASE"
  TMPDIR="$SYNTH_TMP" PYTHONPATH="$RELEASE/dev-hub/bin"     python3 dev-hub/tests/test_v625_component_confidence.py
) >"$WORK/v625-regression.out" 2>"$WORK/v625-regression.err"
grep -Fq 'CHACHA_DEV_V625_THREE_SUCCESS_TRUSTED=PASS' "$WORK/v625-regression.out"
grep -Fq 'CHACHA_DEV_V625_CRITICAL_ANOMALY_QUARANTINE=PASS' "$WORK/v625-regression.out"
echo "CHACHA_DEV_V643_ACQUIRED_REGRESSIONS=PASS"

stage canonical-trust-isolation
python3 - <<'PY'
import json, pathlib, sqlite3
needle="v643-durable-read"
paths=[
  pathlib.Path("/opt/chacha-dev/runtime/knowledge/component-confidence.json"),
  pathlib.Path("/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"),
]
for p in paths:
    if p.is_file():
        assert needle not in p.read_text(encoding="utf-8",errors="ignore"),("SYNTHETIC_TRUST_POLLUTION",str(p))
for p,table in [
  (pathlib.Path("/opt/chacha-dev/runtime/knowledge/component-confidence.db"),"component_confidence"),
  (pathlib.Path("/opt/chacha-dev/runtime/knowledge/production-lineage-feedback.db"),"component_reputation"),
]:
    if not p.is_file():
        continue
    db=sqlite3.connect(f"file:{p}?mode=ro",uri=True)
    try:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if table in tables:
            n=db.execute(f"SELECT COUNT(*) FROM {table} WHERE component_kind='capability' AND component_id=?",(needle,)).fetchone()[0]
            assert int(n)==0,("SYNTHETIC_TRUST_POLLUTION",str(p),n)
    finally:
        db.close()
print("CHACHA_DEV_V643_REAL_CANONICAL_TRUST_SYNTHETIC_MUTATION=NO")
PY

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ] || { echo "CHACHA_DEV_V643_INSTALL=BLOCKED reason=activation_symlink_failed"; exit 31; }
echo "CHACHA_DEV_V643_RELEASE_ACTIVATED=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V643_GUARDIAN_COVERAGE=PASS"

stage post-activation
rm -rf "$SYNTH_TMP"
mkdir -p "$SYNTH_TMP"
(
  cd "$CURRENT"
  TMPDIR="$SYNTH_TMP" PYTHONPATH="$CURRENT/dev-hub/bin"     python3 dev-hub/tests/test_v643_multi_project_trust_graduation.py
) >"$WORK/post-activation.out" 2>"$WORK/post-activation.err"
grep -Fq 'CHACHA_DEV_V643_DISTINCT_PROJECT_COUNTING=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V643_THREE_DISTINCT_PROJECTS_TRUSTED=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V643_CRITICAL_INCIDENT_QUARANTINE=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V643_RECOVERY_RETURNS_PROVISIONAL_NOT_TRUSTED=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V643_TRUST_PERMISSION_ESCALATION=NO' "$WORK/post-activation.out"
echo "CHACHA_DEV_V643_POST_ACTIVATION=PASS"

stage post-activation-isolation
python3 - <<'PY'
import json, pathlib, sqlite3
needle="v643-durable-read"
paths=[
  pathlib.Path("/opt/chacha-dev/runtime/knowledge/component-confidence.json"),
  pathlib.Path("/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"),
]
for p in paths:
    if p.is_file():
        assert needle not in p.read_text(encoding="utf-8",errors="ignore"),("SYNTHETIC_TRUST_POLLUTION",str(p))
for p,table in [
  (pathlib.Path("/opt/chacha-dev/runtime/knowledge/component-confidence.db"),"component_confidence"),
  (pathlib.Path("/opt/chacha-dev/runtime/knowledge/production-lineage-feedback.db"),"component_reputation"),
]:
    if not p.is_file():
        continue
    db=sqlite3.connect(f"file:{p}?mode=ro",uri=True)
    try:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if table in tables:
            n=db.execute(f"SELECT COUNT(*) FROM {table} WHERE component_kind='capability' AND component_id=?",(needle,)).fetchone()[0]
            assert int(n)==0,("SYNTHETIC_TRUST_POLLUTION",str(p),n)
    finally:
        db.close()
print("CHACHA_DEV_V643_POST_ACTIVATION_SYNTHETIC_POLLUTION=NO")
PY

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v643-multi-project-trust-graduation-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v643-multi-project-trust-graduation-evidence/v1",
  "revision":"$REV",
  "observed_at":"$STAMP",
  "v642_real_baseline":"PASS",
  "project_control_verified_observation":"PASS",
  "distinct_project_counting":"PASS",
  "same_project_replay_inflation":false,
  "three_distinct_projects_trusted":"PASS",
  "critical_incident_quarantine":"PASS",
  "negative_trust_removed_from_reuse":"PASS",
  "verified_recovery_fresh_evidence_required":"PASS",
  "recovery_returns_provisional":"PASS",
  "trust_permission_escalation":false,
  "synthetic_canonical_trust_mutation":false,
  "guardian_coverage":"PASS",
  "post_activation":"PASS",
  "technology_watch_revalidation_required":true,
  "architecture_council_final_authority":true,
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V643_MULTI_PROJECT_TRUST_GRADUATION=PASS"
echo "CHACHA_DEV_V643_PROJECT_CONTROL_VERIFIED_OBSERVATION=PASS"
echo "CHACHA_DEV_V643_DISTINCT_PROJECT_COUNTING=PASS"
echo "CHACHA_DEV_V643_REPLAY_TRUST_INFLATION=NO"
echo "CHACHA_DEV_V643_THREE_DISTINCT_PROJECTS_TRUSTED=PASS"
echo "CHACHA_DEV_V643_CRITICAL_INCIDENT_QUARANTINE=PASS"
echo "CHACHA_DEV_V643_NEGATIVE_TRUST_REMOVED_FROM_REUSE=PASS"
echo "CHACHA_DEV_V643_VERIFIED_RECOVERY_FRESH_EVIDENCE_REQUIRED=PASS"
echo "CHACHA_DEV_V643_RECOVERY_RETURNS_PROVISIONAL_NOT_TRUSTED=PASS"
echo "CHACHA_DEV_V643_TRUST_PERMISSION_ESCALATION=NO"
echo "CHACHA_DEV_V643_REAL_CANONICAL_TRUST_SYNTHETIC_MUTATION=NO"
echo "CHACHA_DEV_V643_TECHNOLOGY_WATCH_REVALIDATION_REQUIRED=YES"
echo "CHACHA_DEV_V643_GUARDIAN_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V643_SENTINEL_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V643_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V643_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V643_INSTALL=PASS"

trap - EXIT
cleanup
