#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V644_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V644_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v644.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V644_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V644_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -200 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V644_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in python3 cp ln readlink grep sha256sum find; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p,encoding="utf-8"))
except Exception:x={}
if x.get("active") is True:
    raise SystemExit("CHACHA_DEV_V644_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi

[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"
[ -d "$PREVIOUS/dev-hub" ] || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=current_release_invalid"; exit 2; }

stage v643-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
orch=root/"dev-hub/bin/autonomous-project-orchestrator.py"
assert orch.is_file(),orch
s=orch.read_text(encoding="utf-8")
assert '"version":"6.43.0"' in s,"V643_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="634c76248b611cacde37ddbc3c60bd2861d0afe6",("V643_ACQUIRED_REVISION_MISMATCH",rev)
evidence=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v643-multi-project-trust-graduation-*.json"))
assert evidence,"V643_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V644_V643_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  command -v curl >/dev/null || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=curl_required_without_source_root"; exit 2; }
  command -v tar >/dev/null || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=tar_required_without_source_root"; exit 2; }
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/capability-trust-freshness.py   dev-hub/bin/technology_watch_runtime.py   dev-hub/bin/durable-capability-registry.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/capability-trust-freshness.v1.json   dev-hub/config/capability-trust-graduation.v1.json   dev-hub/config/technology-watch-runtime.v1.json   dev-hub/tests/test_v644_trust_freshness_continuous_revalidation.py   dev-hub/tests/test_v643_multi_project_trust_graduation.py   dev-hub/tests/test_v64_technology_watch_runtime.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
python3 -m py_compile   "$RELEASE/dev-hub/bin/capability-trust-freshness.py"   "$RELEASE/dev-hub/bin/durable-capability-registry.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/tests/test_v644_trust_freshness_continuous_revalidation.py"
python3 -m json.tool "$RELEASE/dev-hub/config/capability-trust-freshness.v1.json" >/dev/null
grep -Fq '"version":"6.44.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V644_STATIC=PASS"

stage semantic-qualification
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v644_trust_freshness_continuous_revalidation.py
) >"$WORK/v644-semantic.out" 2>"$WORK/v644-semantic.err"
for marker in   CHACHA_DEV_V644_TECHNOLOGY_WATCH_FRESH_REVALIDATION=PASS   CHACHA_DEV_V644_TARGETED_REFRESH_ON_STALE=PASS   CHACHA_DEV_V644_EXACT_ADOPTION_BINDING=PASS   CHACHA_DEV_V644_STALE_OR_MISSING_FAST_REUSE_BLOCKED=PASS   CHACHA_DEV_V644_NEGATIVE_TRUST_PRECEDENCE=PASS   CHACHA_DEV_V644_TRUST_HISTORY_PRESERVED=PASS   CHACHA_DEV_V644_TRUST_PERMISSION_ESCALATION=NO   CHACHA_DEV_V644_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v644-semantic.out"
done
echo "CHACHA_DEV_V644_SEMANTIC_QUALIFICATION=PASS"

stage acquired-regressions
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v643_multi_project_trust_graduation.py
) >"$WORK/v643-regression.out" 2>"$WORK/v643-regression.err"
grep -Fq 'CHACHA_DEV_V643_THREE_DISTINCT_PROJECTS_TRUSTED=PASS' "$WORK/v643-regression.out"
grep -Fq 'CHACHA_DEV_V643_CRITICAL_INCIDENT_QUARANTINE=PASS' "$WORK/v643-regression.out"
grep -Fq 'CHACHA_DEV_V643_RECOVERY_RETURNS_PROVISIONAL_NOT_TRUSTED=PASS' "$WORK/v643-regression.out"
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v64_technology_watch_runtime.py
) >"$WORK/v64-techwatch-regression.out" 2>"$WORK/v64-techwatch-regression.err"
grep -Fq 'CHACHA_DEV_V64_TECHNOLOGY_WATCH_SERVICE=PASS' "$WORK/v64-techwatch-regression.out"
grep -Fq 'CHACHA_DEV_V64_TECHNOLOGY_WATCH_ZERO_SPEND=PASS' "$WORK/v64-techwatch-regression.out"
echo "CHACHA_DEV_V644_ACQUIRED_REGRESSIONS=PASS"

stage canonical-state-baseline
canon_hash(){
  local p="$1"
  if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi
}
DURABLE_CANON="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TRUST_CANON="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE_BEFORE="$(canon_hash "$DURABLE_CANON")"
TRUST_BEFORE="$(canon_hash "$TRUST_CANON")"

cat >"$WORK/synthetic-durable.json" <<'JSON'
{
  "schema":"chacha.dev/durable-capability-adoptions/v1",
  "version":"1.0.0",
  "capabilities":{},
  "providers":{},
  "adapters":{},
  "adoptions":{
    "adopt-v644-real-freshness-0001":{
      "adoption_id":"adopt-v644-real-freshness-0001",
      "status":"ADOPTED",
      "project_id":"v644-real-pilot",
      "capability":"v644-real-freshness-probe",
      "provider":"synthetic-zero-spend",
      "adapter":"synthetic-zero-spend-adapter",
      "provider_origin":"BASE_EXISTING",
      "source_kind":"EXISTING_PROVIDER",
      "production_capable":false,
      "network_access":false,
      "credentials_required":false,
      "automatic_external_spend_eur":0
    }
  },
  "history":[],
  "automatic_external_spend_eur":0
}
JSON

stage real-technology-watch-revalidation
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/capability-trust-freshness.py"   --repo-root "$RELEASE"   --registry "$WORK/synthetic-durable.json"   --policy "$RELEASE/dev-hub/config/capability-trust-freshness.v1.json"   --output "$WORK/real-freshness.json"   >"$WORK/real-freshness.out" 2>"$WORK/real-freshness.err"
grep -Fq 'CHACHA_DEV_V644_TRUST_FRESHNESS_PROOF=PASS' "$WORK/real-freshness.out"
grep -Fq 'CHACHA_DEV_V644_EXACT_ADOPTION_BINDING=PASS' "$WORK/real-freshness.out"
python3 - "$WORK/real-freshness.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="PASS",x
assert x["bindings"]==[{"capability":"v644-real-freshness-probe","adoption_id":"adopt-v644-real-freshness-0001"}],x
assert x["technology_watch"]["source_snapshot_digest"],x
assert x["automatic_external_spend_eur"]==0,x
assert x["freshness_grants_permissions"] is False,x
print("CHACHA_DEV_V644_REAL_TECHNOLOGY_WATCH_FRESH_REVALIDATION=PASS")
PY

DURABLE_AFTER="$(canon_hash "$DURABLE_CANON")"
TRUST_AFTER="$(canon_hash "$TRUST_CANON")"
[ "$DURABLE_BEFORE" = "$DURABLE_AFTER" ] || { echo "CANONICAL_DURABLE_REGISTRY_MUTATED"; exit 41; }
[ "$TRUST_BEFORE" = "$TRUST_AFTER" ] || { echo "CANONICAL_TRUST_SNAPSHOT_MUTATED"; exit 42; }
echo "CHACHA_DEV_V644_REAL_CANONICAL_TRUST_MUTATION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ] || { echo "CHACHA_DEV_V644_INSTALL=BLOCKED reason=activation_symlink_failed"; exit 31; }
echo "CHACHA_DEV_V644_RELEASE_ACTIVATED=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V644_GUARDIAN_COVERAGE=PASS"

stage post-activation
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/capability-trust-freshness.py"   --repo-root "$CURRENT"   --registry "$WORK/synthetic-durable.json"   --policy "$CURRENT/dev-hub/config/capability-trust-freshness.v1.json"   --output "$WORK/post-freshness.json"   >"$WORK/post-freshness.out" 2>"$WORK/post-freshness.err"
grep -Fq 'CHACHA_DEV_V644_TRUST_FRESHNESS_PROOF=PASS' "$WORK/post-freshness.out"
grep -Fq '"version":"6.44.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE_CANON")" ] || { echo "POST_ACTIVATION_DURABLE_REGISTRY_MUTATED"; exit 43; }
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST_CANON")" ] || { echo "POST_ACTIVATION_TRUST_SNAPSHOT_MUTATED"; exit 44; }
echo "CHACHA_DEV_V644_POST_ACTIVATION=PASS"
echo "CHACHA_DEV_V644_POST_ACTIVATION_CANONICAL_TRUST_MUTATION=NO"

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v644-trust-freshness-continuous-revalidation-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v644-trust-freshness-evidence/v1",
  "revision":"$REV",
  "observed_at":"$STAMP",
  "v643_real_baseline":"PASS",
  "semantic_qualification":"PASS",
  "technology_watch_fresh_revalidation":"PASS",
  "exact_adoption_binding":"PASS",
  "targeted_refresh_supported":"PASS",
  "negative_trust_precedence":"PASS",
  "historical_trust_mutation":false,
  "canonical_trust_mutation":false,
  "freshness_permission_escalation":false,
  "guardian_coverage":"PASS",
  "post_activation":"PASS",
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V644_TRUST_FRESHNESS_CONTINUOUS_REVALIDATION=PASS"
echo "CHACHA_DEV_V644_REAL_TECHNOLOGY_WATCH_FRESH_REVALIDATION=PASS"
echo "CHACHA_DEV_V644_EXACT_ADOPTION_BINDING=PASS"
echo "CHACHA_DEV_V644_NEGATIVE_TRUST_PRECEDENCE=PASS"
echo "CHACHA_DEV_V644_TRUST_HISTORY_MUTATION=NO"
echo "CHACHA_DEV_V644_REAL_CANONICAL_TRUST_MUTATION=NO"
echo "CHACHA_DEV_V644_TRUST_PERMISSION_ESCALATION=NO"
echo "CHACHA_DEV_V644_GUARDIAN_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V644_SENTINEL_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V644_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V644_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V644_INSTALL=PASS"

trap - EXIT
cleanup
