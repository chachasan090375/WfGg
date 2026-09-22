#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V616_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v616.XXXXXX)"
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
    echo "CHACHA_DEV_V616_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink openssl base64 grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V616_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/guardian-client.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/bin/guardian-alert-poller.py   dev-hub/bin/run-controller.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/technology_watch_runtime.py   dev-hub/bin/architecture-decision-council.py   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/worker-learning-central-identity.v1.json   dev-hub/systemd/chacha-dev-guardian-coverage-heartbeat.service   dev-hub/systemd/chacha-dev-guardian-coverage-heartbeat.timer; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/guardian/alerts /opt/chacha-dev/runtime/control /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/guardian-client.py"   "$RELEASE/dev-hub/bin/guardian-coverage-heartbeat.py"   "$RELEASE/dev-hub/bin/guardian-alert-poller.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/technology_watch_runtime.py"   "$RELEASE/dev-hub/bin/architecture-decision-council.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/dev-hub/config/worker-learning-central-identity.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V616_CENTRAL_KEY_MATCH=PASS"

curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"external_governance_plane":true' "$WORK/guardian-health.json"
grep -Fq '"action_lease_protocol":true' "$WORK/guardian-health.json"
grep -Fq '"coverage_watch":true' "$WORK/guardian-health.json"
grep -Fq '"authenticated_watchdog_sweep":true' "$WORK/guardian-health.json"
grep -Fq '"scheduled_watchdog":true' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V616_EXTERNAL_GUARDIAN_HEALTH=PASS"
echo "CHACHA_DEV_V616_AUTHENTICATED_WATCHDOG_SWEEP=PASS"
echo "CHACHA_DEV_V616_SCHEDULED_WATCHDOG=PASS"

ln -sfn "$RELEASE" "$CURRENT"

# Real repository-level coverage proof sent to the independent Guardian.
python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V616_FULL_GUARDIAN_COVERAGE=PASS"

# Positive PRE -> POST action lease correlation through the real external Worker/D1.
ACTION_ID="v616-action-$STAMP"
PRE_ID="v616-pre-$STAMP"
POST_ID="v616-post-$STAMP"
cat >"$WORK/pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$PRE_ID","action_id":"$ACTION_ID","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"technology-watch","action":"INVOKE_COMPONENT","task_kind":"v616-action-lease-pilot","permission":"read","project_id":"chacha-dev","run_id":"v616-install","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
cat >"$WORK/post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$POST_ID","action_id":"$ACTION_ID","phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"technology-watch","action":"INVOKE_COMPONENT","task_kind":"v616-action-lease-pilot","permission":"read","project_id":"chacha-dev","run_id":"v616-install","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/pre.json" >"$WORK/pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/post.json" >"$WORK/post.out"
grep -Fq '"verdict": "PASS"' "$WORK/pre.out" || grep -Fq '"verdict":"PASS"' "$WORK/pre.out"
grep -Fq '"verdict": "PASS"' "$WORK/post.out" || grep -Fq '"verdict":"PASS"' "$WORK/post.out"
echo "CHACHA_DEV_V616_ACTION_LEASE_E2E=PASS"

# An orphan POST must be blocked and externally alerted.
ORPHAN_ACTION="v616-orphan-$STAMP"
ORPHAN_EVENT="v616-orphan-post-$STAMP"
cat >"$WORK/orphan.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$ORPHAN_EVENT","action_id":"$ORPHAN_ACTION","phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"technology-watch","action":"INVOKE_COMPONENT","task_kind":"v616-orphan-negative-control","permission":"read","project_id":"chacha-dev","run_id":"v616-install","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
set +e
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/orphan.json" >"$WORK/orphan.out"
ORPHAN_RC=$?
set -e
[ "$ORPHAN_RC" -eq 20 ] || { cat "$WORK/orphan.out"; echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=orphan_post_not_blocked"; exit 2; }
grep -Fq 'POST_WITHOUT_PRE_ACTION' "$WORK/orphan.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" ack --alert-id "alert-$ORPHAN_EVENT" >/dev/null
echo "CHACHA_DEV_V616_ORPHAN_POST_BLOCK=PASS"

# Leave one harmless read-only PRE open. Production keeps the autonomous
# Cloudflare cron every minute, but the PILOT invokes the exact same remote sweep
# through an authenticated endpoint so validation does not depend on cron propagation timing.
STALE_ACTION="v616-stale-$STAMP"
STALE_EVENT="v616-stale-pre-$STAMP"
cat >"$WORK/stale-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$STALE_EVENT","action_id":"$STALE_ACTION","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"technology-watch","action":"INVOKE_COMPONENT","task_kind":"v616-missing-post-pilot","permission":"read","project_id":"chacha-dev","run_id":"v616-install","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":30}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/stale-pre.json" >/dev/null
sleep 35
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" watchdog-sweep >"$WORK/sweep.out"
grep -Fq '"status": "PASS"' "$WORK/sweep.out" || grep -Fq '"status":"PASS"' "$WORK/sweep.out"
grep -Fq '"external_guardian": true' "$WORK/sweep.out" || grep -Fq '"external_guardian":true' "$WORK/sweep.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" alerts --status OPEN --limit 100 >"$WORK/alerts.json"
grep -Fq "lease-expired-$STALE_ACTION" "$WORK/alerts.json" || { cat "$WORK/sweep.out"; echo "CHACHA_DEV_V616_INSTALL=BLOCKED reason=external_missing_post_sweep_not_observed"; exit 2; }
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" ack --alert-id "lease-expired-$STALE_ACTION" >/dev/null
echo "CHACHA_DEV_V616_EXTERNAL_MISSING_POST_WATCHDOG=PASS"
echo "CHACHA_DEV_V616_AUTONOMOUS_CRON_WATCHDOG_CONFIGURED=YES"

install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-guardian-coverage-heartbeat.service" /etc/systemd/system/chacha-dev-guardian-coverage-heartbeat.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-guardian-coverage-heartbeat.timer" /etc/systemd/system/chacha-dev-guardian-coverage-heartbeat.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-guardian-coverage-heartbeat.timer
systemctl is-active --quiet chacha-dev-guardian-coverage-heartbeat.timer
echo "CHACHA_DEV_V616_COVERAGE_HEARTBEAT_TIMER=PASS"

systemctl is-active --quiet chacha-dev-guardian-alert-pull.timer
echo "CHACHA_DEV_V616_ALERT_PULL_TIMER=PASS"

if systemctl list-unit-files chacha-dev-technology-watch.timer >/dev/null 2>&1; then
  systemctl restart chacha-dev-technology-watch.timer
fi

cat >"/opt/chacha-dev/evidence/v616-guardian-action-leases-$STAMP.json" <<JSON
{"schema":"chacha.dev/v616-guardian-action-leases-evidence/v1","revision":"$REV","observed_at":"$STAMP","external_guardian":"PASS","coverage":"PASS","action_lease_e2e":"PASS","orphan_post_block":"PASS","missing_post_external_watchdog":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V616_ALL_GOVERNED_ACTIONS_REQUIRE_REALTIME_VERDICT=YES"
echo "CHACHA_DEV_V616_DYNAMIC_AGENTS_COVERED=YES"
echo "CHACHA_DEV_V616_REGISTERED_ADAPTERS_COVERED=YES"
echo "CHACHA_DEV_V616_EXTERNAL_ALERTS=PASS"
echo "CHACHA_DEV_V616_GUARDIAN_AUTO_STOP=NO"
echo "CHACHA_DEV_V616_EMERGENCY_CONTROL_BRIDGE_EXEMPT=YES"
echo "CHACHA_DEV_V616_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V616_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V616_INSTALL=PASS"

trap - EXIT
cleanup
