#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V640_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V640_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v640.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V640_STAGE=$STAGE"; }

cleanup(){
  rm -rf "$WORK" 2>/dev/null || true
}

rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V640_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then
        echo "=== $(basename "$f") ==="
        cat "$f"
      fi
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V640_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in python3 cp ln readlink grep sha256sum find; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p,encoding="utf-8"))
except Exception:x={}
if x.get("active") is True:
    raise SystemExit("CHACHA_DEV_V640_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi

[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"
[ -d "$PREVIOUS/dev-hub" ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=current_release_invalid"; exit 2; }

stage v639-real-baseline
python3 -   "/opt/chacha-dev/runtime/state/v639-real-production-pilot-wfgg-20260923/state.json"   "/opt/chacha-dev/runtime/evidence/v639-real-production-pilot-wfgg-20260923/ledger.json" <<'PY'
import json,sys
state=json.load(open(sys.argv[1],encoding="utf-8"))
ledger=json.load(open(sys.argv[2],encoding="utf-8"))
assert state["state"]["lifecycle"]["stage"]=="OPERATE",state
approval=(ledger.get("approvals") or {}).get("production-deployment") or {}
assert approval.get("status")=="APPROVED",approval
for aid in [
 "production-deployment-receipt","post-deploy-smoke","production-health",
 "observability-health","post-release-signed-checkpoint","post-release-anchor-quorum"
]:
    assert ((ledger.get("artifacts") or {}).get(aid) or {}).get("status")=="OK",(aid,ledger.get("artifacts"))
print("CHACHA_DEV_V640_V639_OPERATE_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  command -v curl >/dev/null || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=curl_required_without_source_root"; exit 2; }
  command -v tar >/dev/null || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=tar_required_without_source_root"; exit 2; }
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/capability-foundry.py   dev-hub/bin/capability-foundry-closure.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/execution-scheduler.py   dev-hub/config/capability-foundry-closure.v1.json   dev-hub/config/capability-registry.v1.json   dev-hub/config/provider-adapters.v1.json   dev-hub/config/execution-scheduler.v1.json   dev-hub/tests/test_v640_capability_foundry_auto_closure.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/capability-foundry.py"   "$RELEASE/dev-hub/bin/capability-foundry-closure.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/execution-scheduler.py"
python3 -m json.tool "$RELEASE/dev-hub/config/capability-foundry-closure.v1.json" >/dev/null
echo "CHACHA_DEV_V640_STATIC=PASS"

stage semantic-qualification
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v640_capability_foundry_auto_closure.py
) >"$WORK/v640-semantic.out" 2>"$WORK/v640-semantic.stderr"
for marker in   CHACHA_DEV_V640_EXISTING_ENABLED_PROVIDER_AUTO_CLOSURE=PASS   CHACHA_DEV_V640_NONZERO_SPEND_FAIL_CLOSED=PASS   CHACHA_DEV_V640_CREDENTIAL_BOUNDARY_FAIL_CLOSED=PASS   CHACHA_DEV_V640_ADAPTER_NOT_ENABLED_FAIL_CLOSED=PASS   CHACHA_DEV_V640_UNKNOWN_PROVIDER_INVENTION=NO   CHACHA_DEV_V640_BUILD_REQUIRED_BLOCKS_DISPATCH=PASS   CHACHA_DEV_V640_ACTIVE_CAPABILITY_REGISTRY_PROPAGATED=PASS   CHACHA_DEV_V640_PRODUCTION_CAPABILITY_HUMAN_ADOPTION_BOUNDARY=PASS; do
  grep -Fq "$marker" "$WORK/v640-semantic.out"
done
echo "CHACHA_DEV_V640_SEMANTIC_QUALIFICATION=PASS"

stage live-registry-read
LIVE_PROVIDER_REGISTRY="$CURRENT/dev-hub/config/provider-adapters.v1.json"
LIVE_CAPABILITY_REGISTRY="$CURRENT/dev-hub/config/capability-registry.v1.json"
[ -f "$LIVE_PROVIDER_REGISTRY" ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=live_provider_registry_missing"; exit 2; }
[ -f "$LIVE_CAPABILITY_REGISTRY" ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=live_capability_registry_missing"; exit 2; }
LIVE_PROVIDER_DIGEST_BEFORE="$(sha256sum "$LIVE_PROVIDER_REGISTRY" | awk '{print $1}')"
LIVE_CAPABILITY_DIGEST_BEFORE="$(sha256sum "$LIVE_CAPABILITY_REGISTRY" | awk '{print $1}')"

python3 - "$LIVE_PROVIDER_REGISTRY" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
p=r["providers"]["playwright-mcp"]
a=r["adapters"][p["adapter"]]
assert p["adapter"]=="playwright-mcp-adapter",p
assert a["status"]=="ENABLED",a
assert set(a.get("supports") or []) >= {"read"},a
print("CHACHA_DEV_V640_LIVE_ENABLED_PROVIDER=PASS")
PY

stage real-project-local-auto-closure
CAPABILITY="v640-browser-proof-$STAMP"
cat >"$WORK/safe-foundry.json" <<JSON
{
  "schema":"chacha.dev/capability-foundry-plan/v1",
  "project_id":"v640-real-pilot-$STAMP",
  "plans":[{
    "capability":"$CAPABILITY",
    "already_registered":false,
    "owner_domain":"domain-v640-real-pilot",
    "technology_candidates":[
      {"provider_id":"playwright-mcp","external_spend_eur":0}
    ],
    "technology_watch":{
      "consulted":true,
      "snapshot_freshness":"PILOT_PINNED",
      "zero_spend_candidate_available":true,
      "automatic_external_spend_eur":0
    },
    "state":"PROJECT_LOCAL_PILOT"
  }],
  "promotion_requires_qualification":true
}
JSON

python3 "$RELEASE/dev-hub/bin/capability-foundry-closure.py"   --policy "$RELEASE/dev-hub/config/capability-foundry-closure.v1.json"   --foundry-plan "$WORK/safe-foundry.json"   --capability-registry "$LIVE_CAPABILITY_REGISTRY"   --provider-adapters "$LIVE_PROVIDER_REGISTRY"   --output "$WORK/safe-closure.json"   --overlay "$WORK/safe-overlay.json" plan   >"$WORK/safe-closure.out"

python3 - "$WORK/safe-closure.json" "$WORK/safe-overlay.json" "$CAPABILITY" <<'PY'
import json,sys
plan=json.load(open(sys.argv[1],encoding="utf-8"))
overlay=json.load(open(sys.argv[2],encoding="utf-8"))
cap=sys.argv[3]
row=plan["plans"][0]
assert row["capability"]==cap,row
assert row["state"]=="PROJECT_LOCAL_READY",row
assert row["selected_provider"]=="playwright-mcp",row
assert row["selected_adapter"]=="playwright-mcp-adapter",row
assert row["selected_adapter_status"]=="ENABLED",row
assert row["same_project_resume_allowed"] is True,row
assert row["production_capable"] is False,row
assert plan["summary"]["build_required_count"]==0,plan
assert plan["automatic_external_spend_eur"]==0,plan
assert overlay["capabilities"][cap]["providers"][0]["status"]=="PILOT",overlay
print("CHACHA_DEV_V640_REAL_PROJECT_LOCAL_AUTO_CLOSURE=PASS")
print("CHACHA_DEV_V640_REAL_EXISTING_ADAPTER_REUSE=PASS")
PY

stage same-project-scheduler-resume
python3 - "$LIVE_CAPABILITY_REGISTRY" "$WORK/safe-overlay.json" "$WORK/temp-capabilities.json" <<'PY'
import json,pathlib,sys
base=json.load(open(sys.argv[1],encoding="utf-8"))
overlay=json.load(open(sys.argv[2],encoding="utf-8"))
base.setdefault("capabilities",{}).update(overlay.get("capabilities") or {})
pathlib.Path(sys.argv[3]).write_text(json.dumps(base,indent=2)+"\n",encoding="utf-8")
PY

cat >"$WORK/task-graph.json" <<JSON
{
  "schema":"chacha.dev/task-graph/v1",
  "project":"v640-real-pilot-$STAMP",
  "transition":"BUILD->VERIFY",
  "tasks":[{
    "id":"v640-use-auto-closed-capability",
    "kind":"verification",
    "permission":"read",
    "capabilities":["$CAPABILITY"],
    "depends_on":[]
  }]
}
JSON
cat >"$WORK/health.json" <<'JSON'
{
  "schema":"chacha.dev/provider-health-snapshot/v1",
  "providers":{
    "playwright-mcp":{"state":"HEALTHY","observed_at":"PILOT"}
  }
}
JSON

python3 "$RELEASE/dev-hub/bin/execution-scheduler.py"   --graph "$WORK/task-graph.json"   --registry "$WORK/temp-capabilities.json"   --health "$WORK/health.json"   --policy "$RELEASE/dev-hub/config/execution-scheduler.v1.json"   --output "$WORK/execution-plan.json"   >"$WORK/scheduler.out"

python3 - "$WORK/execution-plan.json" "$CAPABILITY" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"))
cap=sys.argv[2]
assert p["summary"]["task_count"]==1,p
assert p["summary"]["scheduled_count"]==1,p
assert p["summary"]["blocked_count"]==0,p
task=p["waves"][0]["tasks"][0]
b=task["provider_bindings"][0]
assert b["capability"]==cap,b
assert b["provider"]=="playwright-mcp",b
assert b["state"]=="READY",b
print("CHACHA_DEV_V640_REAL_SAME_PROJECT_RESUME=PASS")
print("CHACHA_DEV_V640_REAL_ACTIVE_CAPABILITY_REGISTRY=PASS")
PY

stage build-required-fail-closed
cat >"$WORK/unknown-foundry.json" <<JSON
{
  "schema":"chacha.dev/capability-foundry-plan/v1",
  "project_id":"v640-build-required-$STAMP",
  "plans":[{
    "capability":"v640-never-invent-$STAMP",
    "already_registered":false,
    "owner_domain":"domain-v640-build-required",
    "technology_candidates":[
      {"provider_id":"v640-made-up-provider","external_spend_eur":0}
    ],
    "technology_watch":{
      "consulted":true,
      "snapshot_freshness":"PILOT_PINNED",
      "zero_spend_candidate_available":true,
      "automatic_external_spend_eur":0
    },
    "state":"PROJECT_LOCAL_PILOT"
  }],
  "promotion_requires_qualification":true
}
JSON
python3 "$RELEASE/dev-hub/bin/capability-foundry-closure.py"   --policy "$RELEASE/dev-hub/config/capability-foundry-closure.v1.json"   --foundry-plan "$WORK/unknown-foundry.json"   --capability-registry "$LIVE_CAPABILITY_REGISTRY"   --provider-adapters "$LIVE_PROVIDER_REGISTRY"   --output "$WORK/unknown-closure.json"   --overlay "$WORK/unknown-overlay.json" plan   >"$WORK/unknown-closure.out"
python3 - "$WORK/unknown-closure.json" "$WORK/unknown-overlay.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"))
o=json.load(open(sys.argv[2],encoding="utf-8"))
row=p["plans"][0]
assert row["state"]=="BUILD_REQUIRED",row
assert row["same_project_resume_allowed"] is False,row
assert p["summary"]["build_required_count"]==1,p
assert p["summary"]["same_project_resume_allowed"] is False,p
assert not (o.get("capabilities") or {}),o
assert "NO_EXISTING_ENABLED_ZERO_SPEND_PROVIDER" in row["reason_codes"],row
print("CHACHA_DEV_V640_REAL_BUILD_REQUIRED_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V640_REAL_UNKNOWN_PROVIDER_INVENTION=NO")
PY

stage verified-adoption-temp-only
cp "$LIVE_CAPABILITY_REGISTRY" "$WORK/adoption-registry.json"
cat >"$WORK/adoption-evidence.json" <<JSON
{
  "schema":"chacha.dev/capability-adoption-evidence/v1",
  "status":"PASS",
  "project_id":"v640-real-pilot-$STAMP",
  "capability":"$CAPABILITY",
  "provider":"playwright-mcp",
  "project_success":true,
  "approvals":[]
}
JSON

python3 "$RELEASE/dev-hub/bin/capability-foundry-closure.py"   --policy "$RELEASE/dev-hub/config/capability-foundry-closure.v1.json"   --foundry-plan "$WORK/safe-foundry.json"   --capability-registry "$WORK/adoption-registry.json"   --provider-adapters "$LIVE_PROVIDER_REGISTRY"   --output "$WORK/adoption-plan.json"   adopt --capability "$CAPABILITY"   --verification "$WORK/adoption-evidence.json"   --actor central-orchestrator   --receipt "$WORK/adoption-receipt.json" --apply   >"$WORK/adoption.out"

python3 - "$WORK/adoption-registry.json" "$WORK/adoption-receipt.json" "$CAPABILITY" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
receipt=json.load(open(sys.argv[2],encoding="utf-8"))
cap=sys.argv[3]
v=r["capabilities"][cap]
assert v["promotion_state"]=="ADOPT",v
assert v["providers"][0]["id"]=="playwright-mcp",v
assert v["providers"][0]["status"]=="ADOPT",v
assert receipt["status"]=="COMMITTED" and receipt["applied"] is True,receipt
print("CHACHA_DEV_V640_REAL_VERIFIED_ADOPTION_TEMP=PASS")
PY

python3 "$RELEASE/dev-hub/bin/capability-foundry-closure.py"   --policy "$RELEASE/dev-hub/config/capability-foundry-closure.v1.json"   --foundry-plan "$WORK/safe-foundry.json"   --capability-registry "$WORK/adoption-registry.json"   --provider-adapters "$LIVE_PROVIDER_REGISTRY"   --output "$WORK/adoption-plan-replay.json"   adopt --capability "$CAPABILITY"   --verification "$WORK/adoption-evidence.json"   --actor central-orchestrator   --receipt "$WORK/adoption-receipt-replay.json" --apply   >"$WORK/adoption-replay.out"
python3 - "$WORK/adoption-receipt-replay.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
assert r["status"]=="IDEMPOTENT" and r["applied"] is False,r
print("CHACHA_DEV_V640_REAL_ADOPTION_IDEMPOTENCE=PASS")
PY

LIVE_PROVIDER_DIGEST_AFTER="$(sha256sum "$LIVE_PROVIDER_REGISTRY" | awk '{print $1}')"
LIVE_CAPABILITY_DIGEST_AFTER="$(sha256sum "$LIVE_CAPABILITY_REGISTRY" | awk '{print $1}')"
[ "$LIVE_PROVIDER_DIGEST_BEFORE" = "$LIVE_PROVIDER_DIGEST_AFTER" ] || {
  echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=live_provider_registry_mutated_during_pilot"; exit 21;
}
[ "$LIVE_CAPABILITY_DIGEST_BEFORE" = "$LIVE_CAPABILITY_DIGEST_AFTER" ] || {
  echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=live_capability_registry_mutated_during_pilot"; exit 22;
}
echo "CHACHA_DEV_V640_REAL_SYNTHETIC_REGISTRY_POLLUTION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ] || { echo "CHACHA_DEV_V640_INSTALL=BLOCKED reason=activation_symlink_failed"; exit 23; }
echo "CHACHA_DEV_V640_RELEASE_ACTIVATED=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V640_GUARDIAN_COVERAGE=PASS"

stage post-activation
(
  cd "$CURRENT"
  PYTHONPATH="$CURRENT/dev-hub/bin" python3 dev-hub/tests/test_v640_capability_foundry_auto_closure.py
) >"$WORK/post-activation.out" 2>"$WORK/post-activation.stderr"
grep -Fq 'CHACHA_DEV_V640_EXISTING_ENABLED_PROVIDER_AUTO_CLOSURE=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V640_BUILD_REQUIRED_BLOCKS_DISPATCH=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V640_ACTIVE_CAPABILITY_REGISTRY_PROPAGATED=PASS' "$WORK/post-activation.out"
echo "CHACHA_DEV_V640_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v640-capability-foundry-auto-closure-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v640-capability-foundry-auto-closure-evidence/v1",
  "revision":"$REV",
  "observed_at":"$STAMP",
  "v639_operate_baseline":"PASS",
  "semantic_qualification":"PASS",
  "live_enabled_provider":"playwright-mcp",
  "project_local_auto_closure":"PASS",
  "same_project_scheduler_resume":"PASS",
  "build_required_fail_closed":"PASS",
  "verified_adoption_temp_only":"PASS",
  "adoption_idempotence":"PASS",
  "synthetic_registry_pollution":false,
  "guardian_coverage":"PASS",
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V640_CAPABILITY_FOUNDRY_AUTO_CLOSURE=PASS"
echo "CHACHA_DEV_V640_EXISTING_ENABLED_PROVIDER_REUSE=PASS"
echo "CHACHA_DEV_V640_SAME_PROJECT_RESUME=PASS"
echo "CHACHA_DEV_V640_BUILD_REQUIRED_FAIL_CLOSED=PASS"
echo "CHACHA_DEV_V640_UNKNOWN_PROVIDER_INVENTION=NO"
echo "CHACHA_DEV_V640_VERIFIED_ADOPTION_BEFORE_DURABLE_REGISTRATION=PASS"
echo "CHACHA_DEV_V640_REAL_REGISTRY_SYNTHETIC_MUTATION=NO"
echo "CHACHA_DEV_V640_PRODUCTION_CAPABILITY_HUMAN_BOUNDARY=PRESERVED"
echo "CHACHA_DEV_V640_TECHNOLOGY_WATCH_REQUIRED=YES"
echo "CHACHA_DEV_V640_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V640_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V640_INSTALL=PASS"

trap - EXIT
cleanup
