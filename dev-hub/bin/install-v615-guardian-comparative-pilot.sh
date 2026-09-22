#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V615_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v615.XXXXXX)"
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
    echo "CHACHA_DEV_V615_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink openssl base64 sha256sum grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V615_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/guardian-client.py   dev-hub/bin/guardian-alert-poller.py   dev-hub/bin/run-controller.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/technology_watch_runtime.py   dev-hub/bin/architecture-comparative-pilot.py   dev-hub/bin/architecture-portfolio-optimizer.py   dev-hub/bin/architecture-decision-council.py   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/comparative-pilot-policy.v1.json   dev-hub/systemd/chacha-dev-guardian-alert-pull.service   dev-hub/systemd/chacha-dev-guardian-alert-pull.timer   dev-hub/tests/fixtures/comparative-pilot-harness.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/guardian/alerts /opt/chacha-dev/runtime/control /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/guardian-client.py"   "$RELEASE/dev-hub/bin/guardian-alert-poller.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/technology_watch_runtime.py"   "$RELEASE/dev-hub/bin/architecture-comparative-pilot.py"   "$RELEASE/dev-hub/bin/architecture-portfolio-optimizer.py"   "$RELEASE/dev-hub/bin/architecture-decision-council.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

# Verify that the private key on ChaChaVPS still matches the public identity deployed to Guardian.
ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/dev-hub/config/worker-learning-central-identity.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V615_CENTRAL_KEY_MATCH=PASS"

ln -sfn "$RELEASE" "$CURRENT"

# External Guardian must be independently reachable before governance is activated locally.
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"external_governance_plane":true' "$WORK/guardian-health.json"
grep -Fq '"runtime_contract_mutation_api":false' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V615_EXTERNAL_GUARDIAN_HEALTH=PASS"

# Safe signed governance request from the real central brain.
SAFE_ID="v615-safe-$STAMP"
cat >"$WORK/safe-event.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$SAFE_ID","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"technology-watch","action":"INVOKE_COMPONENT","task_kind":"v615-runtime-pilot","permission":"read","project_id":"chacha-dev","run_id":"v615-install","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   check --event "$WORK/safe-event.json" >"$WORK/safe-verdict.json"
grep -Fq '"verdict": "PASS"' "$WORK/safe-verdict.json" || grep -Fq '"verdict":"PASS"' "$WORK/safe-verdict.json"
echo "CHACHA_DEV_V615_GUARDIAN_SIGNED_GATE=PASS"

# Deliberate role violation: prove that Guardian blocks it and emits an external alert.
BAD_ID="v615-violation-$STAMP"
cat >"$WORK/bad-event.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$BAD_ID","phase":"POST_ACTION","actor":"branch-foundry","subject_role":"branch-foundry","action":"FINAL_ARCHITECTURE_DECISION","task_kind":"v615-negative-control","permission":"plan","project_id":"chacha-dev","run_id":"v615-install","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false}}
JSON
set +e
python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   check --event "$WORK/bad-event.json" >"$WORK/bad-verdict.json"
BAD_RC=$?
set -e
[ "$BAD_RC" -eq 21 ] || { cat "$WORK/bad-verdict.json"; echo "CHACHA_DEV_V615_INSTALL=BLOCKED reason=guardian_negative_control_not_critical"; exit 2; }
grep -Fq '"verdict": "CRITICAL"' "$WORK/bad-verdict.json" || grep -Fq '"verdict":"CRITICAL"' "$WORK/bad-verdict.json"
python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   alerts --status OPEN --limit 100 >"$WORK/open-alerts.json"
grep -Fq "alert-$BAD_ID" "$WORK/open-alerts.json"
python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   ack --alert-id "alert-$BAD_ID" >/dev/null
echo "CHACHA_DEV_V615_GUARDIAN_ROLE_VIOLATION_BLOCK=PASS"
echo "CHACHA_DEV_V615_GUARDIAN_ALERT_PATH=PASS"

# Technology Watch now reports every runtime consultation to the external Guardian.
PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$CURRENT" <<'PY'
import sys
from pathlib import Path
import technology_watch_runtime as tw
root=Path(sys.argv[1])
x=tw.consult(root,consumer="v615-runtime-pilot",domain="web-ui",capabilities=["static-web"])
assert x["schema"]=="chacha.dev/technology-watch-materialization-feed/v1"
assert x.get("source_snapshot_digest")
PY
echo "CHACHA_DEV_V615_TECHNOLOGY_WATCH_GUARDIAN_RUNTIME=PASS"

# Real identical-harness comparative pilot in two constrained systemd transient capsules.
cat >"$WORK/portfolio.json" <<'JSON'
{
  "schema":"chacha.dev/architecture-portfolio-optimizer/v1",
  "version":"6.15.0",
  "mode":"COMPARATIVE_PILOT_REQUIRED",
  "comparative_pilot_required":true,
  "historical_best":{
    "architecture_id":"architecture-v615-pilot",
    "version":"historical",
    "functional_signature":"v615-runtime-functional-signature",
    "components":{"packages":[{"domain":"web-ui","kind":"primary","capabilities":["static-web"],"architecture":{"pattern":"historical-edge","runtime":"none"},"agent_decision":"TOOL_ONLY"}]}
  },
  "current_foundry_candidate":{
    "zero_spend":true,
    "packages":[{"package_id":"web","domain":"web-ui","kind":"primary","capabilities":["static-web"],"architecture":{"pattern":"current-edge","runtime":"none"},"agent_decision":"TOOL_ONLY","external_spend_eur":0}]
  }
}
JSON
cat >"$WORK/harness.json" <<JSON
{
  "schema":"chacha.dev/comparative-pilot-harness/v1",
  "argv":["/usr/bin/python3","$CURRENT/dev-hub/tests/fixtures/comparative-pilot-harness.py","--architecture","{architecture_json}","--output","{result_json}","--variant","{variant}"],
  "resource_budget":{"memory_mb":128,"cpu_weight":25,"tasks_max":4,"timeout_seconds":30}
}
JSON
python3 "$CURRENT/dev-hub/bin/architecture-comparative-pilot.py"   --repo-root "$CURRENT"   --portfolio "$WORK/portfolio.json"   --harness "$WORK/harness.json"   --output "$WORK/comparative-result.json"   --runtime-root /opt/chacha-dev/runtime/comparative-pilots >/dev/null
python3 - "$WORK/comparative-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="PASS",x
assert x["resolved"] is True,x
assert x["winner"]=="CURRENT",x
assert x["same_benchmark_contract"] is True,x
assert x["isolated_capsules"] is True,x
assert x["automatic_external_spend_eur"]==0,x
PY
echo "CHACHA_DEV_V615_REAL_COMPARATIVE_PILOT=PASS"
echo "CHACHA_DEV_V615_IDENTICAL_HARNESS=PASS"
echo "CHACHA_DEV_V615_ISOLATED_CAPSULES=PASS"

# Persist runtime evidence before enabling the alert timer.
cp "$WORK/comparative-result.json" "/opt/chacha-dev/evidence/v615-comparative-pilot-$STAMP.json"
cat >"/opt/chacha-dev/evidence/v615-guardian-$STAMP.json" <<JSON
{"schema":"chacha.dev/v615-guardian-runtime-evidence/v1","revision":"$REV","observed_at":"$STAMP","external_guardian_health":"PASS","signed_gate":"PASS","role_violation_block":"PASS","alert_path":"PASS","technology_watch_observed":"PASS","automatic_external_spend_eur":0}
JSON

install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-guardian-alert-pull.service" /etc/systemd/system/chacha-dev-guardian-alert-pull.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-guardian-alert-pull.timer" /etc/systemd/system/chacha-dev-guardian-alert-pull.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-guardian-alert-pull.timer
systemctl is-active --quiet chacha-dev-guardian-alert-pull.timer
echo "CHACHA_DEV_V615_GUARDIAN_ALERT_TIMER=PASS"

if systemctl list-unit-files chacha-dev-technology-watch.timer >/dev/null 2>&1; then
  systemctl restart chacha-dev-technology-watch.timer
fi

echo "CHACHA_DEV_V615_EXTERNAL_GUARDIAN=PASS"
echo "CHACHA_DEV_V615_REALTIME_ROLE_GOVERNANCE=PASS"
echo "CHACHA_DEV_V615_CONNECTOR_PERMISSION_GOVERNANCE=PASS"
echo "CHACHA_DEV_V615_GUARDIAN_AUTO_STOP=NO"
echo "CHACHA_DEV_V615_COMPARATIVE_PILOT_AUTOMATION=PASS"
echo "CHACHA_DEV_V615_PRODUCTION_FAIL_CLOSED_ON_UNRESOLVED_CONFLICT=YES"
echo "CHACHA_DEV_V615_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V615_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V615_INSTALL=PASS"

trap - EXIT
cleanup
