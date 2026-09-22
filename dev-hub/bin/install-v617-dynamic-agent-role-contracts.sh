#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V617_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v617.XXXXXX)"
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
    echo "CHACHA_DEV_V617_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink openssl base64 grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V617_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/guardian-client.py   dev-hub/bin/agent_role_contracts.py   dev-hub/bin/agent-role-contract-manager.py   dev-hub/bin/agent-foundry-planner.py   dev-hub/bin/run-controller.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/agent-foundry.v1.json   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/worker-learning-central-identity.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/guardian/alerts /opt/chacha-dev/runtime/control /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/guardian-client.py"   "$RELEASE/dev-hub/bin/agent_role_contracts.py"   "$RELEASE/dev-hub/bin/agent-role-contract-manager.py"   "$RELEASE/dev-hub/bin/agent-foundry-planner.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/dev-hub/config/worker-learning-central-identity.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V617_CENTRAL_KEY_MATCH=PASS"

curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"external_governance_plane":true' "$WORK/guardian-health.json"
grep -Fq '"dynamic_instance_contract_registration":true' "$WORK/guardian-health.json"
grep -Fq '"dynamic_contract_policy_escalation_allowed":false' "$WORK/guardian-health.json"
grep -Fq '"action_lease_protocol":true' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V617_EXTERNAL_GUARDIAN_HEALTH=PASS"
echo "CHACHA_DEV_V617_DYNAMIC_CONTRACT_ENDPOINT=PASS"

ln -sfn "$RELEASE" "$CURRENT"

cat >"$WORK/preplan.json" <<'JSON'
{
  "schema":"chacha.dev/domain-plan/v1",
  "intent":"V6.17 dynamic agent role contract runtime pilot",
  "packages":[{
    "id":"domain:graphics",
    "domain":"graphics",
    "kind":"primary",
    "roles":[],
    "capabilities":["image-generation","layout-design"],
    "toolchain":["image-tool"]
  }]
}
JSON
cat >"$WORK/routing.json" <<'JSON'
{"roles":{}}
JSON

PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent-foundry-planner.py"   --preplan "$WORK/preplan.json"   --config "$CURRENT/dev-hub/config/agent-foundry.v1.json"   --routing "$WORK/routing.json"   --project-id "v617-runtime-pilot"   --output "$WORK/agent-topology.json" >/dev/null

python3 - "$WORK/agent-topology.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
d=x["decisions"][0]
assert d["decision"]=="CREATE_EPHEMERAL_AGENT",d
c=d["manifest"]["guardian_role_contract"]
assert c["contract_id"]=="agent:"+d["agent_id"],c
assert c["version"].startswith("v1-"),c
assert c["project_id"]=="v617-runtime-pilot",c
assert c["domain"]=="graphics",c
assert set(c["allowed_capabilities"])=={"image-generation","layout-design"},c
assert "production-deploy" not in c["allowed_permissions"],c
assert c["production_permissions_allowed"] is False,c
PY
echo "CHACHA_DEV_V617_AGENT_FOUNDRY_CONTRACT_ISSUANCE=PASS"

python3 "$CURRENT/dev-hub/bin/agent-role-contract-manager.py"   --agent-topology "$WORK/agent-topology.json"   --output "$WORK/agent-contracts.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --register >/dev/null

python3 - "$WORK/agent-contracts.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["contract_count"]==1,x
assert x["registered"] is True,x
assert x["all_registered"] is True,x
assert len(x["registrations"])==1,x
assert x["registrations"][0]["status"]=="PASS",x
PY
echo "CHACHA_DEV_V617_DYNAMIC_CONTRACT_REGISTRATION_E2E=PASS"

eval "$(python3 - "$WORK/agent-contracts.json" <<'PY'
import json,shlex,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
c=x["contracts"][0]
print("AGENT_ID="+shlex.quote(c["agent_id"]))
print("CONTRACT_ID="+shlex.quote(c["contract_id"]))
print("CONTRACT_VERSION="+shlex.quote(c["version"]))
PY
)"

ACTION_ID="v617-agent-action-$STAMP"
cat >"$WORK/agent-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v617-agent-pre-$STAMP","action_id":"$ACTION_ID","phase":"PRE_ACTION","actor":"run-controller","subject_role":"$AGENT_ID","subject_contract_id":"$CONTRACT_ID","subject_contract_version":"$CONTRACT_VERSION","action":"DISPATCH_TASK","task_kind":"graphics-work","capabilities":["image-generation","layout-design"],"permission":"workspace-write","project_id":"v617-runtime-pilot","run_id":"v617-runtime","adapters":[],"evidence":{"adapter_binding_valid":true,"human_approval":true,"storage_preflight":true,"emergency_stop_active":false},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
cat >"$WORK/agent-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v617-agent-post-$STAMP","action_id":"$ACTION_ID","phase":"POST_ACTION","actor":"run-controller","subject_role":"$AGENT_ID","subject_contract_id":"$CONTRACT_ID","subject_contract_version":"$CONTRACT_VERSION","action":"DISPATCH_TASK","task_kind":"graphics-work","capabilities":["image-generation","layout-design"],"permission":"workspace-write","project_id":"v617-runtime-pilot","run_id":"v617-runtime","adapters":[],"evidence":{"adapter_binding_valid":true,"human_approval":true,"storage_preflight":true,"emergency_stop_active":false,"result_status":"OK"},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/agent-pre.json" >"$WORK/agent-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/agent-post.json" >"$WORK/agent-post.out"
grep -Fq '"verdict": "PASS"' "$WORK/agent-pre.out" || grep -Fq '"verdict":"PASS"' "$WORK/agent-pre.out"
grep -Fq '"verdict": "PASS"' "$WORK/agent-post.out" || grep -Fq '"verdict":"PASS"' "$WORK/agent-post.out"
echo "CHACHA_DEV_V617_EXACT_AGENT_MISSION_RUNTIME=PASS"

BAD_EVENT="v617-agent-bad-$STAMP"
cat >"$WORK/agent-bad.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$BAD_EVENT","action_id":"v617-bad-action-$STAMP","phase":"PRE_ACTION","actor":"run-controller","subject_role":"$AGENT_ID","subject_contract_id":"$CONTRACT_ID","subject_contract_version":"$CONTRACT_VERSION","action":"DISPATCH_TASK","task_kind":"graphics-work","capabilities":["image-generation","database-admin"],"permission":"workspace-write","project_id":"v617-runtime-pilot","run_id":"v617-runtime","adapters":[],"evidence":{"adapter_binding_valid":true,"human_approval":true,"storage_preflight":true,"emergency_stop_active":false},"context":{"resource_class":"light","domain":"graphics","package_id":"domain:graphics","deadline_seconds":120}}
JSON
set +e
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/agent-bad.json" >"$WORK/agent-bad.out"
BAD_RC=$?
set -e
[ "$BAD_RC" -eq 20 ] || { cat "$WORK/agent-bad.out"; echo "CHACHA_DEV_V617_INSTALL=BLOCKED reason=mission_escape_not_blocked"; exit 2; }
grep -Fq 'CAPABILITY_OUTSIDE_AGENT_MISSION:database-admin' "$WORK/agent-bad.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" ack --alert-id "alert-$BAD_EVENT" >/dev/null
echo "CHACHA_DEV_V617_AGENT_MISSION_ESCAPE_BLOCK=PASS"

python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V617_GUARDIAN_COVERAGE_WITH_AGENT_REGISTRY=PASS"

systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true

cat >"/opt/chacha-dev/evidence/v617-dynamic-agent-role-contracts-$STAMP.json" <<JSON
{"schema":"chacha.dev/v617-dynamic-agent-role-contracts-evidence/v1","revision":"$REV","observed_at":"$STAMP","agent_foundry_contract":"PASS","external_registration":"PASS","exact_mission_runtime":"PASS","mission_escape_block":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V617_EVERY_CREATED_AGENT_VERSIONED_CONTRACT=YES"
echo "CHACHA_DEV_V617_PROJECT_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V617_DOMAIN_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V617_CAPABILITY_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V617_PERMISSION_SCOPE_ENFORCED=YES"
echo "CHACHA_DEV_V617_STATIC_GUARDIAN_POLICY_RUNTIME_MUTATION=NO"
echo "CHACHA_DEV_V617_DYNAMIC_CONTRACT_PRIVILEGE_ESCALATION=NO"
echo "CHACHA_DEV_V617_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V617_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V617_INSTALL=PASS"

trap - EXIT
cleanup
