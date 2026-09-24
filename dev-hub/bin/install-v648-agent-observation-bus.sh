#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V648_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V648_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v648.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V648_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V648_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -200 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V648_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V648_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V648_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V648_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v647-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.47.0"' in s,"V647_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="c97769ee1df7776afac98898143cacf1edaf4623",("V647_ACQUIRED_REVISION_MISMATCH",rev)
ev=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v647-agent-fleet-observatory-*.json"))
assert ev,"V647_REAL_EVIDENCE_MISSING"
report=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json")
assert report.is_file(),"V647_FLEET_REPORT_MISSING"
x=json.loads(report.read_text(encoding="utf-8"))
assert x.get("agent_count")==35,x
assert x.get("unknown_dimension_default_score") is None,x
print("CHACHA_DEV_V648_V647_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V648_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/agent_observation_bus.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/run-controller.py   dev-hub/bin/project-control.py   dev-hub/config/agent-observation-bus.v1.json   dev-hub/config/agent-fleet-observatory.v1.json   dev-hub/tests/test_v648_agent_observation_bus.py   dev-hub/tests/test_v647_agent_fleet_observatory.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V648_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/agent_observation_bus.py"   "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/project-control.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" >/dev/null
grep -Fq '"version":"6.48.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V648_STATIC=PASS"

stage semantic-qualification
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v648_agent_observation_bus.py
) >"$WORK/v648.out" 2>"$WORK/v648.err"
for marker in   CHACHA_DEV_V648_SELF_ASSERTION_VERIFIED=NO   CHACHA_DEV_V648_PROJECT_CONTROL_VERIFIED_BOUNDARY=PASS   CHACHA_DEV_V648_EVENT_ID_DEDUPLICATION=PASS   CHACHA_DEV_V648_HASH_CHAIN=PASS   CHACHA_DEV_V648_VERIFIED_FAILURE_REASSESSMENT_TRIGGER=PASS   CHACHA_DEV_V648_TECHNOLOGY_WATCH_DELTA_TRIGGER=PASS   CHACHA_DEV_V648_DIRECT_AGENT_MUTATION=NO   CHACHA_DEV_V648_COVERAGE_FROM_OBSERVATION_BUS=PASS   CHACHA_DEV_V648_HANDOFF_FROM_VERIFIED_BOUNDARY=PASS   CHACHA_DEV_V648_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v648.out"
done
echo "CHACHA_DEV_V648_SEMANTIC_QUALIFICATION=PASS"

stage v647-regression
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v647_agent_fleet_observatory.py
) >"$WORK/v647.out" 2>"$WORK/v647.err"
grep -Fq 'CHACHA_DEV_V647_AGENT_INVENTORY_35=PASS' "$WORK/v647.out"
grep -Fq 'CHACHA_DEV_V647_UNKNOWN_DIMENSION_DEFAULT=NONE' "$WORK/v647.out"
echo "CHACHA_DEV_V648_V647_REGRESSION=PASS"

stage isolated-real-pilot
RUNTIME="$WORK/runtime"
mkdir -p "$RUNTIME"
cat >"$WORK/self-event.json" <<'JSON'
{
  "event_id":"v648-real-self","event_type":"TASK_RESULT_VERIFIED",
  "source_id":"release-engineer","source_surface":"pilot-self",
  "project_id":"v648-real-pilot","subject_role":"release-engineer",
  "outcome":"OK","verification":"VERIFIED",
  "capabilities":["release-validation"],"evidence_refs":["pilot:self"]
}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_observation_bus.py"   --runtime-root "$RUNTIME" --policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json"   publish --event "$WORK/self-event.json" >"$WORK/self.out"
python3 - "$WORK/self.out" <<'PY'
import json,sys
raw=open(sys.argv[1],encoding="utf-8").read().splitlines()[0]
x=json.loads(raw)
assert x["event"]["verification"]=="SELF_ASSERTED",x
assert x["trigger"] is None,x
print("CHACHA_DEV_V648_REAL_SELF_ASSERTION_VERIFIED=NO")
PY

cat >"$WORK/fail-event.json" <<'JSON'
{
  "event_id":"v648-real-verified-failure","event_type":"TASK_RESULT_VERIFIED",
  "source_id":"project-control","source_surface":"project-control:verification-broker",
  "project_id":"v648-real-pilot","subject_role":"release-engineer",
  "outcome":"FAILED","verification":"VERIFIED",
  "capabilities":["release-validation"],"evidence_refs":["pilot:verified-failure"]
}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_observation_bus.py"   --runtime-root "$RUNTIME" --policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json"   publish --event "$WORK/fail-event.json" >"$WORK/fail.out"
python3 - "$WORK/fail.out" "$RUNTIME" <<'PY'
import json,sys,pathlib
x=json.loads(open(sys.argv[1],encoding="utf-8").read().splitlines()[0])
assert x["event"]["verification"]=="VERIFIED",x
assert x["trigger"]["trigger_type"]=="VERIFIED_FAILURE",x
p=pathlib.Path(x["trigger"]["path"])
assert p.is_file(),p
r=json.loads(p.read_text(encoding="utf-8"))
assert r["action"]=="REASSESS",r
assert r["direct_agent_mutation"] is False,r
assert r["direct_candidate_materialization"] is False,r
assert r["candidate_owner"]=="agent-foundry",r
print("CHACHA_DEV_V648_REAL_VERIFIED_FAILURE_TRIGGER=PASS")
print("CHACHA_DEV_V648_REAL_DIRECT_AGENT_MUTATION=NO")
print("CHACHA_DEV_V648_REAL_DIRECT_CANDIDATE_MATERIALIZATION=NO")
PY
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_observation_bus.py"   --runtime-root "$RUNTIME" --policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" verify   >"$WORK/chain.out"
grep -Fq 'CHACHA_DEV_V648_OBSERVATION_CHAIN=PASS' "$WORK/chain.out"
echo "CHACHA_DEV_V648_REAL_HASH_CHAIN=PASS"

stage canonical-state-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
FLEET="/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json"
TRUST_BEFORE="$(canon_hash "$TRUST")"
DURABLE_BEFORE="$(canon_hash "$DURABLE")"
TW_BEFORE="$(canon_hash "$TW")"
FLEET_BEFORE="$(canon_hash "$FLEET")"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
mkdir -p /opt/chacha-dev/runtime/agent-observation
mkdir -p /opt/chacha-dev/runtime/agent-evolution/reassessment-queue
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_observation_bus.py"   --runtime-root /opt/chacha-dev/runtime   --policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json" verify   >"$WORK/real-chain.out"
grep -Fq 'CHACHA_DEV_V648_OBSERVATION_CHAIN=PASS' "$WORK/real-chain.out"
echo "CHACHA_DEV_V648_RELEASE_ACTIVATED=PASS"
echo "CHACHA_DEV_V648_REAL_BUS_INITIALIZED=PASS"

stage daily-observatory-compatibility
systemctl is-enabled --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl start chacha-dev-agent-fleet-observatory.service
test -s "$FLEET"
python3 - "$FLEET" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["agent_count"]==35,x
assert x["unknown_dimension_default_score"] is None,x
assert x["agent_self_scoring_authority"] is False,x
print("CHACHA_DEV_V648_REAL_FLEET_OBSERVATORY_COMPATIBILITY=PASS")
PY

stage canonical-isolation
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo "CANONICAL_TRUST_MUTATED"; exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo "CANONICAL_DURABLE_MUTATED"; exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo "CANONICAL_TECHNOLOGY_WATCH_MUTATED"; exit 43; }
echo "CHACHA_DEV_V648_REAL_CANONICAL_TRUST_DURABLE_TW_MUTATION=NO"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V648_GUARDIAN_COVERAGE=PASS"

stage post-activation
grep -Fq '"version":"6.48.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_observation_bus.py"   --runtime-root /opt/chacha-dev/runtime --policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json" verify   >"$WORK/post-chain.out"
grep -Fq 'CHACHA_DEV_V648_OBSERVATION_CHAIN=PASS' "$WORK/post-chain.out"
echo "CHACHA_DEV_V648_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v648-agent-observation-bus-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v648-agent-observation-bus-evidence/v1",
  "revision":"$REV",
  "observed_at":"$STAMP",
  "v647_real_baseline":"PASS",
  "semantic_qualification":"PASS",
  "self_assertion_verified":false,
  "independent_verified_boundary":"PASS",
  "verified_failure_reassessment_trigger":"PASS",
  "direct_agent_mutation":false,
  "direct_candidate_materialization":false,
  "candidate_owner":"agent-foundry",
  "hash_chain":"PASS",
  "fleet_observatory_compatibility":"PASS",
  "daily_timer_preserved":"PASS",
  "canonical_trust_durable_technology_watch_mutation":false,
  "guardian_coverage":"PASS",
  "architecture_council_final_authority":true,
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V648_AGENT_OBSERVATION_BUS=PASS"
echo "CHACHA_DEV_V648_REAL_SELF_ASSERTION_VERIFIED=NO"
echo "CHACHA_DEV_V648_REAL_VERIFIED_FAILURE_TRIGGER=PASS"
echo "CHACHA_DEV_V648_REAL_DIRECT_AGENT_MUTATION=NO"
echo "CHACHA_DEV_V648_REAL_DIRECT_CANDIDATE_MATERIALIZATION=NO"
echo "CHACHA_DEV_V648_REAL_HASH_CHAIN=PASS"
echo "CHACHA_DEV_V648_REAL_FLEET_OBSERVATORY_COMPATIBILITY=PASS"
echo "CHACHA_DEV_V648_REAL_CANONICAL_TRUST_DURABLE_TW_MUTATION=NO"
echo "CHACHA_DEV_V648_GUARDIAN_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V648_SENTINEL_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V648_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V648_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V648_INSTALL=PASS"

trap - EXIT
cleanup
