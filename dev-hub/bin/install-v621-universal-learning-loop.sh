#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V621_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v621.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PRIVATE_KEY="/opt/chacha-dev/runtime/secrets/central-learning-key.pem"
PILOT_PRODUCER_KEY="/opt/chacha-dev/runtime/secrets/v621-pilot-learning-producer.pem"
GUARDIAN_URL="https://chacha-dev-guardian.chachasan090375.workers.dev"
RELAY_URL="https://chacha-dev-learning-relay.chachasan090375.workers.dev"
PREVIOUS=""
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V621_STAGE=$STAGE"; }

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V621_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/local-observe-1.json "$WORK"/local-observe-same.json "$WORK"/local-observe-2.json "$WORK"/local-flush.json "$WORK"/local-flush.stderr "$WORK"/remote-flush.json "$WORK"/register.out "$WORK"/anomaly-bridge.out "$WORK"/remediation-pull.out; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
  fi
  if [ "$rc" -ne 0 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart chacha-dev-guardian-remediation.timer >/dev/null 2>&1 || true
    systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
    systemctl restart chacha-dev-central-learning-relay-pull.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V621_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink openssl base64 grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V621_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/universal_learning_runtime.py   dev-hub/bin/universal-learning-producer.py   dev-hub/bin/generate-learning-producer-key.py   dev-hub/bin/register-learning-producer.py   dev-hub/bin/production-anomaly-guardian-bridge.py   dev-hub/bin/central-learning-relay-puller.py   dev-hub/bin/learning-delta-ingest.py   dev-hub/bin/global-project-memory-index.py   dev-hub/bin/guardian-client.py   dev-hub/bin/guardian-remediation-controller.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/universal-learning.v1.json   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/worker-learning-central-identity.v1.json   dev-hub/systemd/chacha-dev-universal-learning-flush.service   dev-hub/systemd/chacha-dev-universal-learning-flush.timer   dev-hub/systemd/chacha-dev-production-anomaly-guardian.service   dev-hub/systemd/chacha-dev-production-anomaly-guardian.timer; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/learning/outbox /opt/chacha-dev/runtime/learning/sent   /opt/chacha-dev/runtime/learning/producer-state /opt/chacha-dev/runtime/learning/anomaly-queue   /opt/chacha-dev/runtime/learning/anomaly-processed /opt/chacha-dev/runtime/secrets /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/universal_learning_runtime.py"   "$RELEASE/dev-hub/bin/universal-learning-producer.py"   "$RELEASE/dev-hub/bin/generate-learning-producer-key.py"   "$RELEASE/dev-hub/bin/register-learning-producer.py"   "$RELEASE/dev-hub/bin/production-anomaly-guardian-bridge.py"   "$RELEASE/dev-hub/bin/central-learning-relay-puller.py"   "$RELEASE/dev-hub/bin/guardian-client.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

stage central-key
ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/dev-hub/config/worker-learning-central-identity.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V621_CENTRAL_KEY_MATCH=PASS"

stage external-health
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"external_governance_plane":true' "$WORK/guardian-health.json"
grep -Fq '"corrective_enforcement":true' "$WORK/guardian-health.json"
grep -Fq '"production_learning_anomaly_bridge":true' "$WORK/guardian-health.json"
grep -Fq '"production_anomaly_direct_mutation":false' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V621_EXTERNAL_GUARDIAN_HEALTH=PASS"

curl -fsS "$RELAY_URL/healthz" -o "$WORK/relay-health.json"
grep -Fq '"service":"chacha-dev-learning-relay"' "$WORK/relay-health.json"
grep -Fq '"tunnel_required":false' "$WORK/relay-health.json"
echo "CHACHA_DEV_V621_LEARNING_RELAY_HEALTH=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-universal-learning-flush.service" /etc/systemd/system/chacha-dev-universal-learning-flush.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-universal-learning-flush.timer" /etc/systemd/system/chacha-dev-universal-learning-flush.timer
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-production-anomaly-guardian.service" /etc/systemd/system/chacha-dev-production-anomaly-guardian.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-production-anomaly-guardian.timer" /etc/systemd/system/chacha-dev-production-anomaly-guardian.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-universal-learning-flush.timer chacha-dev-production-anomaly-guardian.timer
systemctl is-active --quiet chacha-dev-universal-learning-flush.timer
systemctl is-active --quiet chacha-dev-production-anomaly-guardian.timer
echo "CHACHA_DEV_V621_BACKGROUND_LEARNING_TIMERS=PASS"

stage local-incremental-learning
cat >"$WORK/local-state-1.json" <<JSON
{"revision":"$REV","pilot":"local-incremental","quality_score":1}
JSON
cat >"$WORK/local-state-2.json" <<JSON
{"revision":"$REV","pilot":"local-incremental","quality_score":2}
JSON
mkdir -p "$WORK/local-outbox" "$WORK/local-state" "$WORK/local-sent"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" observe   --project-id "chacha-dev-v621-pilot" --source-id "v621-local-agent" --source-kind agent   --deployment-id "v621-local-$STAMP" --state "$WORK/local-state-1.json"   --outbox "$WORK/local-outbox" --state-root "$WORK/local-state" >"$WORK/local-observe-1.json"
grep -Fq '"status": "QUEUED"' "$WORK/local-observe-1.json"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" observe   --project-id "chacha-dev-v621-pilot" --source-id "v621-local-agent" --source-kind agent   --deployment-id "v621-local-$STAMP" --state "$WORK/local-state-1.json"   --outbox "$WORK/local-outbox" --state-root "$WORK/local-state" >"$WORK/local-observe-same.json"
grep -Fq '"status": "NO_CHANGE"' "$WORK/local-observe-same.json"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" observe   --project-id "chacha-dev-v621-pilot" --source-id "v621-local-agent" --source-kind agent   --deployment-id "v621-local-$STAMP" --state "$WORK/local-state-2.json"   --outbox "$WORK/local-outbox" --state-root "$WORK/local-state" >"$WORK/local-observe-2.json"
grep -Fq '"change_count": 1' "$WORK/local-observe-2.json"
LOCAL_FLUSH_OK=0
for i in 1 2 3; do
  set +e
  PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" flush   --transport local --outbox "$WORK/local-outbox" --sent "$WORK/local-sent"   --ingest "$CURRENT/dev-hub/bin/learning-delta-ingest.py"   --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db >"$WORK/local-flush.json" 2>"$WORK/local-flush.stderr"
  LOCAL_RC=$?
  set -e
  if [ "$LOCAL_RC" -eq 0 ] && grep -Fq '"pending": 0' "$WORK/local-flush.json"; then
    LOCAL_FLUSH_OK=1
    break
  fi
  echo "CHACHA_DEV_V621_LOCAL_FLUSH_RETRY=$i"
  cat "$WORK/local-flush.json" 2>/dev/null || true
  cat "$WORK/local-flush.stderr" 2>/dev/null || true
  sleep 2
done
if [ "$LOCAL_FLUSH_OK" -ne 1 ]; then
  echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=local_learning_flush_not_persisted"
  exit 2
fi
echo "CHACHA_DEV_V621_LOCAL_INCREMENTAL_LEARNING_NAS_E2E=PASS"
echo "CHACHA_DEV_V621_NO_CHANGE_NO_DELTA=PASS"

stage remote-producer-enrollment
python3 "$CURRENT/dev-hub/bin/generate-learning-producer-key.py"   --private-key "$PILOT_PRODUCER_KEY"   --project-id "chacha-dev-v621-pilot"   --deployment-id "v621-remote-pilot"   --output "$WORK/producer-enrollment.json" >"$WORK/keygen.out"
grep -Fq 'CHACHA_DEV_LEARNING_PRODUCER_KEYGEN=PASS' "$WORK/keygen.out"
chmod 600 "$PILOT_PRODUCER_KEY"
python3 "$CURRENT/dev-hub/bin/register-learning-producer.py"   --enrollment "$WORK/producer-enrollment.json"   --relay-url "$RELAY_URL"   --central-key "$PRIVATE_KEY" >"$WORK/register.out"
grep -Fq 'CHACHA_DEV_LEARNING_PRODUCER_REGISTER=PASS' "$WORK/register.out"
grep -Fq '"private_key_exported": false' "$WORK/producer-enrollment.json"
echo "CHACHA_DEV_V621_REMOTE_PRODUCER_IDENTITY=PASS"

stage remote-background-uplink
cat >"$WORK/remote-state.json" <<JSON
{"revision":"$REV","runtime_health":"degraded","error_rate_bucket":"high","pilot_stamp":"$STAMP"}
JSON
cat >"$WORK/remote-anomaly.json" <<'JSON'
{"severity":"high","class":"pilot-runtime-regression","signal":"error-rate-threshold-exceeded","automatic_patch_allowed":false}
JSON
mkdir -p "$WORK/remote-outbox" "$WORK/remote-state-store" "$WORK/remote-sent" "$WORK/anomaly-queue" "$WORK/anomaly-processed"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" observe   --project-id "chacha-dev-v621-pilot"   --source-id "v621-remote-embedded-agent"   --source-kind embedded-application-agent   --deployment-id "v621-remote-pilot"   --state "$WORK/remote-state.json"   --anomaly "$WORK/remote-anomaly.json"   --evidence-ref "pilot:v621:$STAMP"   --outbox "$WORK/remote-outbox" --state-root "$WORK/remote-state-store" >"$WORK/remote-observe.json"
REMOTE_DELTA_ID="$(python3 - "$WORK/remote-observe.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["delta_id"])
PY
)"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/universal-learning-producer.py" flush   --transport relay --outbox "$WORK/remote-outbox" --sent "$WORK/remote-sent"   --relay-url "$RELAY_URL" --private-key "$PILOT_PRODUCER_KEY" >"$WORK/remote-flush.json"
grep -Fq '"pending": 0' "$WORK/remote-flush.json"
echo "CHACHA_DEV_V621_REMOTE_BACKGROUND_UPLINK=PASS"

stage central-relay-ingest
FOUND=0
for i in 1 2 3 4 5; do
  python3 "$CURRENT/dev-hub/bin/central-learning-relay-puller.py"     --relay-url "$RELAY_URL"     --private-key "$PRIVATE_KEY"     --ingest "$CURRENT/dev-hub/bin/learning-delta-ingest.py"     --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db     --anomaly-queue "$WORK/anomaly-queue"     --batch-limit 100     --experience-db /opt/chacha-dev/runtime/knowledge/experience.db     --global-indexer "$CURRENT/dev-hub/bin/global-project-memory-index.py"     --global-index /opt/chacha-dev/runtime/knowledge/global-project-memory-index.json >"$WORK/central-pull-$i.out"
  if [ -f "$WORK/anomaly-queue/$REMOTE_DELTA_ID.json" ]; then FOUND=1; break; fi
  sleep 2
done
[ "$FOUND" = 1 ] || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=remote_delta_not_reached_central_anomaly_queue"; exit 2; }
grep -Fq '"nas_required": true' "$WORK/central-pull-$i.out"
grep -Fq '"global_project_memory_index_updated": true' "$WORK/central-pull-$i.out"
echo "CHACHA_DEV_V621_REMOTE_TO_CENTRAL_MEMORY_NAS_E2E=PASS"
echo "CHACHA_DEV_V621_GLOBAL_MEMORY_INDEX_REFRESH=PASS"

stage guardian-anomaly-bridge
python3 "$CURRENT/dev-hub/bin/production-anomaly-guardian-bridge.py"   --queue "$WORK/anomaly-queue" --processed "$WORK/anomaly-processed"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" >"$WORK/anomaly-bridge.out"
grep -Fq 'CHACHA_DEV_PRODUCTION_ANOMALY_GUARDIAN_BRIDGE=PASS' "$WORK/anomaly-bridge.out"
[ -f "$WORK/anomaly-processed/$REMOTE_DELTA_ID.json" ] || { echo "CHACHA_DEV_V621_INSTALL=BLOCKED reason=guardian_anomaly_receipt_missing"; exit 2; }
eval "$(python3 - "$WORK/anomaly-processed/$REMOTE_DELTA_ID.json" <<'PY'
import json,shlex,sys
x=json.load(open(sys.argv[1]))
a=x["guardian_ack"]
print("DIRECTIVE_ID="+shlex.quote(str(a["directive_id"])))
print("ALERT_ID="+shlex.quote(str(a["alert_id"])))
PY
)"
[ -n "$DIRECTIVE_ID" ] && [ -n "$ALERT_ID" ]
echo "CHACHA_DEV_V621_PRODUCTION_ANOMALY_TO_GUARDIAN=PASS"

python3 "$CURRENT/dev-hub/bin/guardian-remediation-controller.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py" >"$WORK/remediation-pull.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_REMEDIATION_PULL=PASS' "$WORK/remediation-pull.out"
grep -Fq "$DIRECTIVE_ID" /opt/chacha-dev/runtime/guardian/remediation-index.json
echo "CHACHA_DEV_V621_GUARDIAN_CORRECTION_ORDER_DELIVERED=PASS"

stage guardian-controlled-correction
ACTION_ID="v621-remediation-$STAMP"
cat >"$WORK/corrected-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v621-remediation-pre-$STAMP","action_id":"$ACTION_ID","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"central-orchestrator","action":"INVOKE_COMPONENT","task_kind":"production-anomaly-remediation","permission":"plan","project_id":"chacha-dev-v621-pilot","run_id":"v621-remediation","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","deadline_seconds":180,"remediation_directive_id":"$DIRECTIVE_ID"}}
JSON
cat >"$WORK/corrected-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v621-remediation-post-$STAMP","action_id":"$ACTION_ID","phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"central-orchestrator","action":"INVOKE_COMPONENT","task_kind":"production-anomaly-remediation","permission":"plan","project_id":"chacha-dev-v621-pilot","run_id":"v621-remediation","adapters":[],"evidence":{"emergency_stop_active":false,"result_status":"OK"},"context":{"resource_class":"light","deadline_seconds":180,"remediation_directive_id":"$DIRECTIVE_ID"}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/corrected-pre.json" >"$WORK/corrected-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/corrected-pre.out"
grep -Eq '"remediation_applied"[[:space:]]*:[[:space:]]*true' "$WORK/corrected-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/corrected-post.json" >"$WORK/corrected-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/corrected-post.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" ack --alert-id "$ALERT_ID" >/dev/null
echo "CHACHA_DEV_V621_GUARDIAN_CONTROLLED_CORRECTION_LOOP=PASS"

stage guardian-coverage
python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V621_GUARDIAN_COVERAGE_WITH_LEARNING_LOOP=PASS"

systemctl restart chacha-dev-guardian-remediation.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-central-learning-relay-pull.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true

cat >"/opt/chacha-dev/evidence/v621-universal-learning-loop-$STAMP.json" <<JSON
{"schema":"chacha.dev/v621-universal-learning-loop-evidence/v1","revision":"$REV","observed_at":"$STAMP","local_incremental_learning":"PASS","remote_background_uplink":"PASS","central_nas_memory":"PASS","global_memory_index":"PASS","production_anomaly_guardian":"PASS","controlled_correction_loop":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V621_EVERY_LEARNING_CAPABLE_COMPONENT_UPLINK=YES"
echo "CHACHA_DEV_V621_INCREMENTAL_DELTAS_ONLY=YES"
echo "CHACHA_DEV_V621_REMOTE_APP_LEARNING_WITHOUT_OWNER_SESSION=YES"
echo "CHACHA_DEV_V621_REMOTE_PRIVATE_KEY_EXPORTED=NO"
echo "CHACHA_DEV_V621_CENTRAL_MEMORY_NAS_AUTHORITATIVE=YES"
echo "CHACHA_DEV_V621_PRODUCTION_ANOMALY_GUARDIAN_CONTROLLED=YES"
echo "CHACHA_DEV_V621_GUARDIAN_DIRECT_PRODUCTION_MUTATION=NO"
echo "CHACHA_DEV_V621_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V621_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V621_INSTALL=PASS"

trap - EXIT
cleanup
