#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V641_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V641_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v641.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V641_STAGE=$STAGE"; }

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }

rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V641_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then
        echo "=== $(basename "$f") ==="
        tail -200 "$f" || true
      fi
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V641_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in python3 cp ln readlink grep sha256sum find; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p,encoding="utf-8"))
except Exception:x={}
if x.get("active") is True:
    raise SystemExit("CHACHA_DEV_V641_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi

[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"
[ -d "$PREVIOUS/dev-hub" ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=current_release_invalid"; exit 2; }

stage v640-real-baseline
python3 - "$PREVIOUS/.revision" "$PREVIOUS/dev-hub/tests/test_v640_capability_foundry_auto_closure.py" <<'PY'
import pathlib,sys
rev=pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").strip()
assert rev=="80082c921c6a5d6dc4cd46184d22b26c9540907e",rev
assert pathlib.Path(sys.argv[2]).is_file(),sys.argv[2]
print("CHACHA_DEV_V641_V640_REAL_BASELINE=PASS")
PY
(
  cd "$PREVIOUS"
  PYTHONPATH="$PREVIOUS/dev-hub/bin" python3 dev-hub/tests/test_v640_capability_foundry_auto_closure.py
) >"$WORK/v640-baseline.out" 2>"$WORK/v640-baseline.stderr"
grep -Fq 'CHACHA_DEV_V640_EXISTING_ENABLED_PROVIDER_AUTO_CLOSURE=PASS' "$WORK/v640-baseline.out"
grep -Fq 'CHACHA_DEV_V640_BUILD_REQUIRED_BLOCKS_DISPATCH=PASS' "$WORK/v640-baseline.out"

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  command -v curl >/dev/null || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=curl_required_without_source_root"; exit 2; }
  command -v tar >/dev/null || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=tar_required_without_source_root"; exit 2; }
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in \
  dev-hub/bin/specification-compiler.py \
  dev-hub/bin/autonomous-project-orchestrator.py \
  dev-hub/bin/capability-foundry.py \
  dev-hub/bin/capability-foundry-closure.py \
  dev-hub/bin/capability-build-request-compiler.py \
  dev-hub/bin/capability-build-loop.py \
  dev-hub/bin/execution-scheduler.py \
  dev-hub/config/capability-build-loop.v1.json \
  dev-hub/config/capability-foundry-closure.v1.json \
  dev-hub/config/provider-adapters.v1.json \
  dev-hub/config/capability-registry.v1.json \
  dev-hub/tests/test_v641_capability_build_loop.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile \
  "$RELEASE/dev-hub/bin/capability-build-loop.py" \
  "$RELEASE/dev-hub/bin/capability-build-request-compiler.py" \
  "$RELEASE/dev-hub/bin/capability-foundry.py" \
  "$RELEASE/dev-hub/bin/capability-foundry-closure.py" \
  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py" \
  "$RELEASE/dev-hub/bin/execution-scheduler.py"
python3 -m json.tool "$RELEASE/dev-hub/config/capability-build-loop.v1.json" >/dev/null
echo "CHACHA_DEV_V641_STATIC=PASS"

stage semantic-qualification
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v641_capability_build_loop.py
) >"$WORK/v641-semantic.out" 2>"$WORK/v641-semantic.stderr"
for marker in \
  CHACHA_DEV_V641_BUILD_REQUIRED_TO_SAFE_ADAPTER=PASS \
  CHACHA_DEV_V641_OFFICIAL_PROVISIONING_CHAIN=PASS \
  CHACHA_DEV_V641_OFFICIAL_PROMOTION_CHAIN=PASS \
  CHACHA_DEV_V641_THREE_RUN_ENABLEMENT=PASS \
  CHACHA_DEV_V641_SAME_PROJECT_RESUME_READY=PASS \
  CHACHA_DEV_V641_UNSAFE_BUILD_CLASSES_FAIL_CLOSED=PASS \
  CHACHA_DEV_V641_GOVERNED_BUILD_REQUEST_COMPILER=PASS \
  CHACHA_DEV_V641_ORCHESTRATOR_POST_COUNCIL_BUILD=PASS \
  CHACHA_DEV_V641_EXPLICIT_BUILD_HINT_PROPAGATION=PASS \
  CHACHA_DEV_V641_BUILD_PROFILE_INFERENCE=NO; do
  grep -Fq "$marker" "$WORK/v641-semantic.out"
done
echo "CHACHA_DEV_V641_SEMANTIC_QUALIFICATION=PASS"

stage live-registry-snapshot
LIVE_PROVIDER_REGISTRY="$CURRENT/dev-hub/config/provider-adapters.v1.json"
LIVE_CAPABILITY_REGISTRY="$CURRENT/dev-hub/config/capability-registry.v1.json"
[ -f "$LIVE_PROVIDER_REGISTRY" ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=live_provider_registry_missing"; exit 2; }
[ -f "$LIVE_CAPABILITY_REGISTRY" ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=live_capability_registry_missing"; exit 2; }
LIVE_PROVIDER_DIGEST_BEFORE="$(sha256sum "$LIVE_PROVIDER_REGISTRY" | awk '{print $1}')"
LIVE_CAPABILITY_DIGEST_BEFORE="$(sha256sum "$LIVE_CAPABILITY_REGISTRY" | awk '{print $1}')"

LOWER_STAMP="$(printf '%s' "$STAMP" | tr '[:upper:]' '[:lower:]')"
CAPABILITY="v641-real-safe-read-${LOWER_STAMP:9:6}"
PROVIDER="v641-real-provider-${LOWER_STAMP:9:6}"
ADAPTER="v641-real-adapter-${LOWER_STAMP:9:6}"
PROJECT="v641-real-build-pilot-${LOWER_STAMP:9:6}"

stage functional-contract-build-hint
cat >"$WORK/intent.json" <<JSON
{
  "name":"V6.41 Real Capability Build Pilot",
  "text":"Construis un projet pilote local qui exige une capacité de lecture structurée absente du registre.",
  "domains":["product"],
  "capability_hints":[{
    "id":"$CAPABILITY",
    "domain":"product",
    "provider_id":"$PROVIDER",
    "adapter_id":"$ADAPTER",
    "build_profile":"structured-read-v1",
    "execution":"vps",
    "supports":["read"],
    "network_access":false,
    "credentials_required":false,
    "production_capable":false,
    "automatic_external_spend_eur":0
  }]
}
JSON
python3 "$RELEASE/dev-hub/bin/specification-compiler.py" \
  --intent "$WORK/intent.json" --output "$WORK/functional-contract.json" \
  >"$WORK/specification.out"
python3 "$RELEASE/dev-hub/bin/functional-intent-orchestrator.py" \
  --config "$RELEASE/dev-hub/config/domain-orchestration.v1.json" \
  --intent "$WORK/intent.json" --output "$WORK/preplan.json"

PYTHONPATH="$RELEASE/dev-hub/bin" python3 - \
  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py" \
  "$WORK/preplan.json" "$WORK/functional-contract.json" \
  "$LIVE_CAPABILITY_REGISTRY" "$PROJECT" "$WORK/capability-gaps.json" <<'PY'
import importlib.util,sys
script,pre,contract,registry,project,out=sys.argv[1:]
spec=importlib.util.spec_from_file_location("v641_orchestrator",script)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
mod.capability_gaps(pre,contract,registry,project,out)
PY
python3 - "$WORK/capability-gaps.json" "$CAPABILITY" "$PROVIDER" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));cap,provider=sys.argv[2:]
row=next(v for v in x["missing_capabilities"] if v["id"]==cap)
assert row["provider_id"]==provider,row
assert row["build_profile"]=="structured-read-v1",row
assert row["network_access"] is False,row
assert row["production_capable"] is False,row
print("CHACHA_DEV_V641_REAL_FUNCTIONAL_BUILD_HINT=PASS")
PY

stage technology-watch-and-foundry
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/capability-foundry.py" \
  --request "$WORK/capability-gaps.json" \
  --policy "$RELEASE/dev-hub/config/capability-foundry.v1.json" \
  --domains "$RELEASE/dev-hub/config/domain-orchestration.v1.json" \
  --capabilities "$LIVE_CAPABILITY_REGISTRY" \
  --output "$WORK/foundry.json" \
  --domain-overlay "$WORK/domain-overlay.json" \
  --capability-overlay "$WORK/logical-capability-overlay.json" \
  --routing-overlay "$WORK/routing-overlay.json" \
  >"$WORK/foundry.out"
python3 - "$WORK/foundry.json" "$CAPABILITY" "$PROVIDER" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));cap,provider=sys.argv[2:]
row=next(v for v in x["plans"] if v["capability"]==cap)
assert row["technology_watch"]["consulted"] is True,row
candidate=next(v for v in row["technology_candidates"] if v.get("provider_id")==provider)
assert candidate["build_profile"]=="structured-read-v1",candidate
assert candidate["evidence"]=="functional-contract-build-hint-reviewed-by-technology-watch",candidate
assert candidate["admissible_for_automatic_selection"] is False,candidate
print("CHACHA_DEV_V641_REAL_TECHNOLOGY_WATCH_CONSULTED=PASS")
print("CHACHA_DEV_V641_REAL_EXPLICIT_BUILD_HINT_PROPAGATED=PASS")
PY

stage v640-build-required
python3 "$RELEASE/dev-hub/bin/capability-foundry-closure.py" \
  --policy "$RELEASE/dev-hub/config/capability-foundry-closure.v1.json" \
  --foundry-plan "$WORK/foundry.json" \
  --capability-registry "$LIVE_CAPABILITY_REGISTRY" \
  --provider-adapters "$LIVE_PROVIDER_REGISTRY" \
  --output "$WORK/closure.json" \
  --overlay "$WORK/closure-overlay.json" plan >"$WORK/closure.out"
python3 - "$WORK/closure.json" "$CAPABILITY" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));cap=sys.argv[2]
row=next(v for v in x["plans"] if v["capability"]==cap)
assert row["state"]=="BUILD_REQUIRED",row
assert row["same_project_resume_allowed"] is False,row
assert "NO_EXISTING_ENABLED_ZERO_SPEND_PROVIDER" in row["reason_codes"],row
print("CHACHA_DEV_V641_REAL_V640_BUILD_REQUIRED=PASS")
PY

stage council-boundary
cat >"$WORK/council-blocked.json" <<JSON
{"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":false,"decisions":[]}
JSON
python3 "$RELEASE/dev-hub/bin/capability-build-request-compiler.py" \
  --closure "$WORK/closure.json" --foundry-plan "$WORK/foundry.json" \
  --architecture-council "$WORK/council-blocked.json" \
  --output "$WORK/build-batch-blocked.json" >"$WORK/compiler-blocked.out"
python3 - "$WORK/build-batch-blocked.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="BLOCKED",x
assert x["buildable_count"]==0,x
print("CHACHA_DEV_V641_REAL_COUNCIL_BLOCKS_BUILD=PASS")
PY

cat >"$WORK/council-approved.json" <<JSON
{
  "schema":"chacha.dev/architecture-decision-council/v1",
  "dispatch_allowed":true,
  "pilot_fixture":true,
  "decisions":[{"package_id":"domain:product","decision_ready":true}]
}
JSON
python3 "$RELEASE/dev-hub/bin/capability-build-request-compiler.py" \
  --closure "$WORK/closure.json" --foundry-plan "$WORK/foundry.json" \
  --architecture-council "$WORK/council-approved.json" \
  --output "$WORK/build-batch.json" >"$WORK/compiler.out"
python3 - "$WORK/build-batch.json" "$CAPABILITY" "$PROVIDER" "$ADAPTER" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));cap,provider,adapter=sys.argv[2:]
assert x["status"]=="READY",x
assert x["buildable_count"]==1 and x["unresolved_count"]==0,x
r=x["requests"][0]
assert r["capability"]==cap and r["provider_id"]==provider and r["adapter_id"]==adapter,r
assert r["architecture_council"]["decision"]=="APPROVED",r
print("CHACHA_DEV_V641_REAL_GOVERNED_BUILD_REQUEST=PASS")
PY

stage autonomous-safe-build
mkdir -p "$WORK/build-repo"
cp -a "$RELEASE/dev-hub" "$WORK/build-repo/dev-hub"
python3 - "$WORK/build-batch.json" "$WORK/build-request.json" <<'PY'
import json,pathlib,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
pathlib.Path(sys.argv[2]).write_text(json.dumps(x["requests"][0],indent=2)+"\n",encoding="utf-8")
PY
PYTHONPATH="$WORK/build-repo/dev-hub/bin" python3 "$WORK/build-repo/dev-hub/bin/capability-build-loop.py" \
  --policy "$WORK/build-repo/dev-hub/config/capability-build-loop.v1.json" \
  --request "$WORK/build-request.json" \
  --repo-root "$WORK/build-repo" \
  --base-registry "$LIVE_PROVIDER_REGISTRY" \
  --workspace "$WORK/build-workspace" \
  build-pilot \
  --runtime-root "$WORK/adapter-runtime" \
  --output "$WORK/build-result.json" \
  --overlay "$WORK/built-capability-overlay.json" \
  --apply >"$WORK/build-loop.out" 2>"$WORK/build-loop.stderr"

for marker in \
  CHACHA_DEV_V641_SAFE_ADAPTER_BUILD=PASS \
  CHACHA_DEV_V641_CONTRACT_OK=PASS \
  CHACHA_DEV_V641_SANDBOX_PILOT=PASS \
  CHACHA_DEV_V641_REPEATABLE_RUNS=3 \
  CHACHA_DEV_V641_SANDBOX_ENABLED=PASS \
  CHACHA_DEV_V641_SAME_PROJECT_RESUME_ALLOWED=YES; do
  grep -Fq "$marker" "$WORK/build-loop.out"
done
python3 - "$WORK/build-result.json" "$CAPABILITY" "$PROVIDER" "$ADAPTER" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));cap,provider,adapter=sys.argv[2:]
assert x["status"]=="PASS",x
assert x["capability"]==cap and x["provider"]==provider and x["adapter"]==adapter,x
assert x["adapter_status"]=="ENABLED",x
assert x["same_project_resume_allowed"] is True,x
assert x["durable_adoption"]=="PENDING_PROJECT_SUCCESS",x
assert x["network_access"] is False and x["credentials_required"] is False,x
assert x["production_capable"] is False,x
assert x["automatic_external_spend_eur"]==0,x
print("CHACHA_DEV_V641_REAL_SAFE_ADAPTER_BUILD=PASS")
print("CHACHA_DEV_V641_REAL_SANDBOX_ENABLED=PASS")
PY

stage same-project-resume
python3 - "$LIVE_CAPABILITY_REGISTRY" "$WORK/built-capability-overlay.json" "$WORK/runtime-capabilities.json" <<'PY'
import json,pathlib,sys
base=json.load(open(sys.argv[1],encoding="utf-8"))
ov=json.load(open(sys.argv[2],encoding="utf-8"))
base.setdefault("capabilities",{}).update(ov.get("capabilities") or {})
pathlib.Path(sys.argv[3]).write_text(json.dumps(base,indent=2)+"\n",encoding="utf-8")
PY
cat >"$WORK/task-graph.json" <<JSON
{
  "schema":"chacha.dev/task-graph/v1",
  "project":"$PROJECT",
  "transition":"BUILD->VERIFY",
  "tasks":[{
    "id":"v641-use-built-capability",
    "kind":"verification",
    "permission":"read",
    "capabilities":["$CAPABILITY"],
    "depends_on":[]
  }]
}
JSON
cat >"$WORK/health.json" <<JSON
{
  "schema":"chacha.dev/provider-health-snapshot/v1",
  "providers":{"$PROVIDER":{"state":"HEALTHY","observed_at":"PILOT"}}
}
JSON
python3 "$RELEASE/dev-hub/bin/execution-scheduler.py" \
  --graph "$WORK/task-graph.json" \
  --registry "$WORK/runtime-capabilities.json" \
  --health "$WORK/health.json" \
  --policy "$RELEASE/dev-hub/config/execution-scheduler.v1.json" \
  --output "$WORK/execution-plan.json" >"$WORK/scheduler.out"
python3 - "$WORK/execution-plan.json" "$CAPABILITY" "$PROVIDER" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"));cap,provider=sys.argv[2:]
assert p["summary"]["scheduled_count"]==1,p
assert p["summary"]["blocked_count"]==0,p
b=p["waves"][0]["tasks"][0]["provider_bindings"][0]
assert b["capability"]==cap and b["provider"]==provider,b
assert b["state"]=="READY",b
print("CHACHA_DEV_V641_REAL_SAME_PROJECT_RESUME=PASS")
PY

stage durable-adoption-boundary
python3 - "$WORK/build-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["durable_adoption"]=="PENDING_PROJECT_SUCCESS",x
print("CHACHA_DEV_V641_REAL_DURABLE_ADOPTION_BEFORE_PROJECT_SUCCESS=NO")
PY

LIVE_PROVIDER_DIGEST_AFTER="$(sha256sum "$LIVE_PROVIDER_REGISTRY" | awk '{print $1}')"
LIVE_CAPABILITY_DIGEST_AFTER="$(sha256sum "$LIVE_CAPABILITY_REGISTRY" | awk '{print $1}')"
[ "$LIVE_PROVIDER_DIGEST_BEFORE" = "$LIVE_PROVIDER_DIGEST_AFTER" ] || {
  echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=live_provider_registry_mutated_during_pilot"; exit 21;
}
[ "$LIVE_CAPABILITY_DIGEST_BEFORE" = "$LIVE_CAPABILITY_DIGEST_AFTER" ] || {
  echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=live_capability_registry_mutated_during_pilot"; exit 22;
}
echo "CHACHA_DEV_V641_REAL_SYNTHETIC_REGISTRY_POLLUTION=NO"
echo "CHACHA_DEV_V641_REAL_SYNTHETIC_ADAPTER_DURABLE_INSTALL=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ] || { echo "CHACHA_DEV_V641_INSTALL=BLOCKED reason=activation_symlink_failed"; exit 23; }
echo "CHACHA_DEV_V641_RELEASE_ACTIVATED=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py" \
  --repo-root "$CURRENT" \
  --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json" \
  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  --client "$CURRENT/dev-hub/bin/guardian-client.py" \
  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json \
  >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V641_GUARDIAN_COVERAGE=PASS"

stage post-activation
(
  cd "$CURRENT"
  PYTHONPATH="$CURRENT/dev-hub/bin" python3 dev-hub/tests/test_v641_capability_build_loop.py
) >"$WORK/post-activation.out" 2>"$WORK/post-activation.stderr"
grep -Fq 'CHACHA_DEV_V641_BUILD_REQUIRED_TO_SAFE_ADAPTER=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V641_ORCHESTRATOR_POST_COUNCIL_BUILD=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V641_EXPLICIT_BUILD_HINT_PROPAGATION=PASS' "$WORK/post-activation.out"
echo "CHACHA_DEV_V641_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v641-capability-build-loop-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v641-capability-build-loop-evidence/v1",
  "revision":"$REV",
  "observed_at":"$STAMP",
  "v640_real_baseline":"PASS",
  "functional_build_hint":"PASS",
  "technology_watch_consulted":"PASS",
  "v640_build_required":"PASS",
  "council_boundary":"PASS",
  "governed_build_request":"PASS",
  "safe_adapter_build":"PASS",
  "contract_ok":"PASS",
  "sandbox_pilot":"PASS",
  "repeatable_runs":3,
  "sandbox_enabled":"PASS",
  "same_project_resume":"PASS",
  "durable_adoption_before_project_success":false,
  "synthetic_live_registry_pollution":false,
  "synthetic_adapter_durable_install":false,
  "guardian_coverage":"PASS",
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V641_CAPABILITY_BUILD_LOOP=PASS"
echo "CHACHA_DEV_V641_FUNCTIONAL_HINT_TO_BUILD_REQUIRED=PASS"
echo "CHACHA_DEV_V641_TECHNOLOGY_WATCH_REQUIRED=YES"
echo "CHACHA_DEV_V641_ARCHITECTURE_COUNCIL_BUILD_BOUNDARY=PASS"
echo "CHACHA_DEV_V641_SAFE_ADAPTER_BUILD=PASS"
echo "CHACHA_DEV_V641_OFFICIAL_PROVISIONING_AND_PROMOTION=PASS"
echo "CHACHA_DEV_V641_REPEATABLE_ENABLEMENT=PASS"
echo "CHACHA_DEV_V641_SAME_PROJECT_RESUME=PASS"
echo "CHACHA_DEV_V641_DURABLE_ADOPTION_BEFORE_PROJECT_SUCCESS=NO"
echo "CHACHA_DEV_V641_PRODUCTION_BUILD_AUTOMATION=BLOCKED"
echo "CHACHA_DEV_V641_CREDENTIAL_BUILD_AUTOMATION=BLOCKED"
echo "CHACHA_DEV_V641_NETWORK_BUILD_AUTOMATION=BLOCKED"
echo "CHACHA_DEV_V641_REAL_REGISTRY_SYNTHETIC_MUTATION=NO"
echo "CHACHA_DEV_V641_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V641_INSTALL=PASS"

trap - EXIT
cleanup
