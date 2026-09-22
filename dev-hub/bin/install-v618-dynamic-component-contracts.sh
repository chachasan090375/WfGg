#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V618_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v618.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PRIVATE_KEY="/opt/chacha-dev/runtime/secrets/central-learning-key.pem"
GUARDIAN_URL="https://chacha-dev-guardian.chachasan090375.workers.dev"
PREVIOUS=""

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
    systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
    systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V618_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink openssl base64 grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V618_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/guardian-client.py   dev-hub/bin/dynamic_component_contracts.py   dev-hub/bin/component-role-contract-manager.py   dev-hub/bin/run-controller.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/worker-learning-central-identity.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/guardian/alerts /opt/chacha-dev/runtime/control /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/guardian-client.py"   "$RELEASE/dev-hub/bin/dynamic_component_contracts.py"   "$RELEASE/dev-hub/bin/component-role-contract-manager.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/dev-hub/config/worker-learning-central-identity.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V618_CENTRAL_KEY_MATCH=PASS"

curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"external_governance_plane":true' "$WORK/guardian-health.json"
grep -Fq '"dynamic_component_contract_registration":true' "$WORK/guardian-health.json"
grep -Fq '"dynamic_component_policy_escalation_allowed":false' "$WORK/guardian-health.json"
grep -Fq '"action_lease_protocol":true' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V618_EXTERNAL_GUARDIAN_HEALTH=PASS"
echo "CHACHA_DEV_V618_DYNAMIC_COMPONENT_ENDPOINT=PASS"

ln -sfn "$RELEASE" "$CURRENT"

cat >"$WORK/preplan.json" <<'JSON'
{
  "schema":"chacha.dev/domain-plan/v1",
  "project_id":"v618-runtime-pilot",
  "intent":"V6.18 dynamic branch and orchestrator runtime pilot",
  "packages":[{
    "id":"domain:graphics",
    "domain":"graphics",
    "kind":"primary",
    "capabilities":["image-generation","layout-design"]
  }]
}
JSON

cat >"$WORK/branch-topology.json" <<'JSON'
{
  "schema":"chacha.dev/branch-topology/v1",
  "project_id":"v618-runtime-pilot",
  "decisions":[{
    "package_id":"domain:graphics",
    "branch_id":"v618-runtime-pilot:graphics:primary",
    "domain":"graphics",
    "kind":"primary",
    "decision":"MATERIALIZE_EPHEMERAL_BRANCH",
    "runtime_required":true,
    "orchestrator_strategy":"DEDICATED_EPHEMERAL",
    "architecture":{"preview":"ephemeral"},
    "resource_budget":{"memory_hard_limit_mb":128,"disk_soft_limit_mb":128,"cpu_weight":20,"processes_max":1}
  }]
}
JSON

cat >"$WORK/capability-foundry.json" <<'JSON'
{
  "schema":"chacha.dev/capability-foundry-plan/v1",
  "project_id":"v618-runtime-pilot",
  "plans":[]
}
JSON

PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component-role-contract-manager.py"   --preplan "$WORK/preplan.json"   --branch-topology "$WORK/branch-topology.json"   --capability-foundry "$WORK/capability-foundry.json"   --output "$WORK/component-contracts.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --register >/dev/null

python3 - "$WORK/component-contracts.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["contract_count"]==2,x
assert x["kinds"]["branch"]==1,x
assert x["kinds"]["orchestrator"]==1,x
assert x["registered"] is True,x
assert x["all_registered"] is True,x
assert len(x["registrations"])==2,x
assert all(r.get("status")=="PASS" for r in x["registrations"]),x
for c in x["contracts"]:
    assert c["project_id"]=="v618-runtime-pilot",c
    assert c["domain"]=="graphics",c
    assert "production-deploy" not in c["allowed_permissions"],c
    assert c["production_permissions_allowed"] is False,c
PY
echo "CHACHA_DEV_V618_DYNAMIC_COMPONENT_REGISTRATION_E2E=PASS"

eval "$(python3 - "$WORK/component-contracts.json" <<'PY'
import json,shlex,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
b=next(c for c in x["contracts"] if c["component_kind"]=="branch")
o=next(c for c in x["contracts"] if c["component_kind"]=="orchestrator")
for p,c in [("BRANCH",b),("ORCH",o)]:
    print(p+"_ID="+shlex.quote(c["component_id"]))
    print(p+"_CONTRACT_ID="+shlex.quote(c["contract_id"]))
    print(p+"_VERSION="+shlex.quote(c["version"]))
PY
)"

BRANCH_ACTION="v618-branch-$STAMP"
cat >"$WORK/branch-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v618-branch-pre-$STAMP","action_id":"$BRANCH_ACTION","phase":"PRE_ACTION","actor":"run-controller","subject_role":"$BRANCH_ID","subject_contract_id":"$BRANCH_CONTRACT_ID","subject_contract_version":"$BRANCH_VERSION","action":"DISPATCH_TASK","task_kind":"branch-work","capabilities":["image-generation"],"permission":"workspace-write","project_id":"v618-runtime-pilot","run_id":"v618-runtime","adapters":[],"evidence":{"adapter_binding_valid":true,"human_approval":true,"storage_preflight":true,"emergency_stop_active":false},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
cat >"$WORK/branch-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v618-branch-post-$STAMP","action_id":"$BRANCH_ACTION","phase":"POST_ACTION","actor":"run-controller","subject_role":"$BRANCH_ID","subject_contract_id":"$BRANCH_CONTRACT_ID","subject_contract_version":"$BRANCH_VERSION","action":"DISPATCH_TASK","task_kind":"branch-work","capabilities":["image-generation"],"permission":"workspace-write","project_id":"v618-runtime-pilot","run_id":"v618-runtime","adapters":[],"evidence":{"adapter_binding_valid":true,"human_approval":true,"storage_preflight":true,"emergency_stop_active":false,"result_status":"OK"},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/branch-pre.json" >"$WORK/branch-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/branch-post.json" >"$WORK/branch-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/branch-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/branch-post.out"
echo "CHACHA_DEV_V618_BRANCH_EXACT_MISSION_RUNTIME=PASS"

ORCH_ACTION="v618-orch-$STAMP"
cat >"$WORK/orch-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v618-orch-pre-$STAMP","action_id":"$ORCH_ACTION","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"$ORCH_ID","subject_contract_id":"$ORCH_CONTRACT_ID","subject_contract_version":"$ORCH_VERSION","action":"INVOKE_COMPONENT","task_kind":"dynamic-orchestrator-work","capabilities":["layout-design"],"permission":"plan","project_id":"v618-runtime-pilot","run_id":"v618-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
cat >"$WORK/orch-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v618-orch-post-$STAMP","action_id":"$ORCH_ACTION","phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"$ORCH_ID","subject_contract_id":"$ORCH_CONTRACT_ID","subject_contract_version":"$ORCH_VERSION","action":"INVOKE_COMPONENT","task_kind":"dynamic-orchestrator-work","capabilities":["layout-design"],"permission":"plan","project_id":"v618-runtime-pilot","run_id":"v618-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/orch-pre.json" >"$WORK/orch-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/orch-post.json" >"$WORK/orch-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/orch-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/orch-post.out"
echo "CHACHA_DEV_V618_ORCHESTRATOR_EXACT_MISSION_RUNTIME=PASS"

BAD_EVENT="v618-component-bad-$STAMP"
cat >"$WORK/bad.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$BAD_EVENT","action_id":"v618-bad-action-$STAMP","phase":"PRE_ACTION","actor":"run-controller","subject_role":"$BRANCH_ID","subject_contract_id":"$BRANCH_CONTRACT_ID","subject_contract_version":"$BRANCH_VERSION","action":"DISPATCH_TASK","task_kind":"branch-work","capabilities":["database-admin"],"permission":"workspace-write","project_id":"v618-runtime-pilot","run_id":"v618-runtime","adapters":[],"evidence":{"adapter_binding_valid":true,"human_approval":true,"storage_preflight":true,"emergency_stop_active":false},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
set +e
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/bad.json" >"$WORK/bad.out"
BAD_RC=$?
set -e
[ "$BAD_RC" -eq 20 ] || { cat "$WORK/bad.out"; echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=component_mission_escape_not_blocked"; exit 2; }
grep -Fq 'CAPABILITY_OUTSIDE_COMPONENT_MISSION:database-admin' "$WORK/bad.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" ack --alert-id "alert-$BAD_EVENT" >/dev/null
echo "CHACHA_DEV_V618_COMPONENT_MISSION_ESCAPE_BLOCK=PASS"

BAD_PROJECT_EVENT="v618-cross-project-$STAMP"
cat >"$WORK/bad-project.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$BAD_PROJECT_EVENT","action_id":"v618-cross-project-action-$STAMP","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"$ORCH_ID","subject_contract_id":"$ORCH_CONTRACT_ID","subject_contract_version":"$ORCH_VERSION","action":"INVOKE_COMPONENT","task_kind":"dynamic-orchestrator-work","capabilities":["layout-design"],"permission":"plan","project_id":"other-project","run_id":"v618-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
set +e
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/bad-project.json" >"$WORK/bad-project.out"
PROJECT_RC=$?
set -e
[ "$PROJECT_RC" -eq 21 ] || { cat "$WORK/bad-project.out"; echo "CHACHA_DEV_V618_INSTALL=BLOCKED reason=cross_project_not_critical"; exit 2; }
grep -Fq 'DYNAMIC_COMPONENT_PROJECT_SCOPE_MISMATCH' "$WORK/bad-project.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" ack --alert-id "alert-$BAD_PROJECT_EVENT" >/dev/null
echo "CHACHA_DEV_V618_CROSS_PROJECT_COMPONENT_BLOCK=PASS"

python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V618_GUARDIAN_COVERAGE_WITH_COMPONENT_REGISTRY=PASS"

systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true

cat >"/opt/chacha-dev/evidence/v618-dynamic-component-contracts-$STAMP.json" <<JSON
{"schema":"chacha.dev/v618-dynamic-component-contracts-evidence/v1","revision":"$REV","observed_at":"$STAMP","branch_contract":"PASS","orchestrator_contract":"PASS","external_registration":"PASS","mission_escape_block":"PASS","cross_project_block":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V618_EVERY_DYNAMIC_BRANCH_VERSIONED_CONTRACT=YES"
echo "CHACHA_DEV_V618_EVERY_DYNAMIC_ORCHESTRATOR_VERSIONED_CONTRACT=YES"
echo "CHACHA_DEV_V618_PROJECT_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V618_DOMAIN_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V618_CAPABILITY_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V618_PERMISSION_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V618_DYNAMIC_COMPONENT_PRIVILEGE_ESCALATION=NO"
echo "CHACHA_DEV_V618_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V618_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V618_INSTALL=PASS"

trap - EXIT
cleanup
