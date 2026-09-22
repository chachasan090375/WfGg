#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V620_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v620.XXXXXX)"
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
    systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
    systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V620_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink openssl base64 grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V620_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/guardian-client.py   dev-hub/bin/guardian-remediation-controller.py   dev-hub/bin/guardian_remediation_runtime.py   dev-hub/bin/run-controller.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/technology_watch_runtime.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/worker-learning-central-identity.v1.json   dev-hub/systemd/chacha-dev-guardian-remediation.service   dev-hub/systemd/chacha-dev-guardian-remediation.timer; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/guardian/remediations /opt/chacha-dev/runtime/control /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/guardian-client.py"   "$RELEASE/dev-hub/bin/guardian-remediation-controller.py"   "$RELEASE/dev-hub/bin/guardian_remediation_runtime.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/technology_watch_runtime.py"   "$RELEASE/dev-hub/bin/guardian-coverage-heartbeat.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/dev-hub/config/worker-learning-central-identity.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V620_CENTRAL_KEY_MATCH=PASS"

curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"external_governance_plane":true' "$WORK/guardian-health.json"
grep -Fq '"corrective_enforcement":true' "$WORK/guardian-health.json"
grep -Fq '"remediation_holds":true' "$WORK/guardian-health.json"
grep -Fq '"remediation_retry_limit":3' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V620_EXTERNAL_GUARDIAN_HEALTH=PASS"
echo "CHACHA_DEV_V620_CORRECTIVE_ENFORCEMENT_ENDPOINTS=PASS"

ln -sfn "$RELEASE" "$CURRENT"

install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-guardian-remediation.service" /etc/systemd/system/chacha-dev-guardian-remediation.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-guardian-remediation.timer" /etc/systemd/system/chacha-dev-guardian-remediation.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-guardian-remediation.timer
systemctl is-active --quiet chacha-dev-guardian-remediation.timer
echo "CHACHA_DEV_V620_REMEDIATION_TIMER=PASS"

BAD_EVENT="v620-bad-$STAMP"
cat >"$WORK/bad.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"$BAD_EVENT","action_id":"v620-bad-action-$STAMP","phase":"PRE_ACTION","actor":"technology-watch","subject_role":"technology-watch","action":"DISPATCH_TASK","task_kind":"v620-corrective-pilot","permission":"read","project_id":"platform-global","run_id":"v620-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","deadline_seconds":120}}
JSON
set +e
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/bad.json" >"$WORK/bad.out"
BAD_RC=$?
set -e
[ "$BAD_RC" -eq 20 ] || { cat "$WORK/bad.out"; echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=synthetic_violation_not_blocked"; exit 2; }
grep -Fq '"remediation_required": true' "$WORK/bad.out" || grep -Fq '"remediation_required":true' "$WORK/bad.out"
DIRECTIVE_ID="$(python3 - "$WORK/bad.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
print(x.get("remediation_directive_id") or "")
PY
)"
[ -n "$DIRECTIVE_ID" ] || { echo "CHACHA_DEV_V620_INSTALL=BLOCKED reason=directive_not_issued"; exit 2; }
echo "CHACHA_DEV_V620_VIOLATION_BLOCK_AND_DIRECTIVE=PASS"

python3 "$CURRENT/dev-hub/bin/guardian-remediation-controller.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py" >"$WORK/remediation-pull.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_REMEDIATION_PULL=PASS' "$WORK/remediation-pull.out"
python3 - "$DIRECTIVE_ID" <<'PY'
import json,sys
p="/opt/chacha-dev/runtime/guardian/remediation-index.json"
x=json.load(open(p,encoding="utf-8"))
did=sys.argv[1]
assert any(str(d.get("directive_id"))==did for d in x.get("items") or []),(did,x)
PY
echo "CHACHA_DEV_V620_RULE_REMINDER_DELIVERED=PASS"

cat >"$WORK/good-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v620-good-pre-$STAMP","action_id":"v620-good-action-$STAMP","phase":"PRE_ACTION","actor":"technology-watch","subject_role":"technology-watch","action":"OBSERVE_TECHNOLOGY","task_kind":"v620-corrective-pilot","permission":"read","project_id":"platform-global","run_id":"v620-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","deadline_seconds":120,"remediation_directive_id":"$DIRECTIVE_ID"}}
JSON
cat >"$WORK/good-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v620-good-post-$STAMP","action_id":"v620-good-action-$STAMP","phase":"POST_ACTION","actor":"technology-watch","subject_role":"technology-watch","action":"OBSERVE_TECHNOLOGY","task_kind":"v620-corrective-pilot","permission":"read","project_id":"platform-global","run_id":"v620-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","deadline_seconds":120,"remediation_directive_id":"$DIRECTIVE_ID"}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/good-pre.json" >"$WORK/good-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/good-pre.out"
grep -Eq '"remediation_applied"[[:space:]]*:[[:space:]]*true' "$WORK/good-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/good-post.json" >"$WORK/good-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/good-post.out"
echo "CHACHA_DEV_V620_CORRECTED_ACTION_ACCEPTED=PASS"

python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" remediations --status APPLIED --limit 100 >"$WORK/applied.json"
grep -Fq "$DIRECTIVE_ID" "$WORK/applied.json"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" ack --alert-id "alert-$BAD_EVENT" >/dev/null
python3 "$CURRENT/dev-hub/bin/guardian-remediation-controller.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py" >/dev/null
python3 - "$DIRECTIVE_ID" <<'PY'
import json,sys
p="/opt/chacha-dev/runtime/guardian/remediation-index.json"
x=json.load(open(p,encoding="utf-8"))
did=sys.argv[1]
assert not any(str(d.get("directive_id"))==did for d in x.get("items") or []),(did,x)
PY
echo "CHACHA_DEV_V620_REMEDIATION_HOLD_CLEARED_AFTER_COMPLIANCE=PASS"

python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V620_GUARDIAN_COVERAGE_WITH_REMEDIATION=PASS"

systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true

cat >"/opt/chacha-dev/evidence/v620-guardian-corrective-enforcement-$STAMP.json" <<JSON
{"schema":"chacha.dev/v620-guardian-corrective-enforcement-evidence/v1","revision":"$REV","observed_at":"$STAMP","directive_issued":"PASS","rule_reminder_delivered":"PASS","corrected_action_accepted":"PASS","hold_cleared":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V620_GUARDIAN_POLICE_MODE=CORRECTIVE_ENFORCEMENT"
echo "CHACHA_DEV_V620_GUARDIAN_BLOCKS_NONCOMPLIANCE=YES"
echo "CHACHA_DEV_V620_GUARDIAN_ORDERS_CORRECTION=YES"
echo "CHACHA_DEV_V620_RESPONSIBLE_COMPONENT_MUST_APPLY_RULES=YES"
echo "CHACHA_DEV_V620_CORRECTED_ACTION_MUST_RETURN_TO_GUARDIAN=YES"
echo "CHACHA_DEV_V620_MAX_FAILED_CORRECTION_ATTEMPTS=3"
echo "CHACHA_DEV_V620_CRITICAL_ESCALATION_STOP_REQUIRED=YES"
echo "CHACHA_DEV_V620_GUARDIAN_REWRITES_ARCHITECTURE=NO"
echo "CHACHA_DEV_V620_GUARDIAN_EXPANDS_PERMISSIONS=NO"
echo "CHACHA_DEV_V620_GUARDIAN_AUTO_STOP=NO"
echo "CHACHA_DEV_V620_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V620_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V620_INSTALL=PASS"

trap - EXIT
cleanup
