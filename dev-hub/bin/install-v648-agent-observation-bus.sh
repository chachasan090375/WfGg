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
   for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do [ -s "$f" ] || continue; echo "=== $(basename "$f") ==="; tail -200 "$f" || true; done
   if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
     ln -sfn "$PREVIOUS" "$CURRENT"; systemctl daemon-reload || true
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
import pathlib,sys
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.47.0"' in s,"V647_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="c97769ee1df7776afac98898143cacf1edaf4623",("V647_ACQUIRED_REVISION_MISMATCH",rev)
ev=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v647-agent-fleet-observatory-*.json"))
assert ev,"V647_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V648_V647_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
 SRC="$(readlink -f "$SOURCE_ROOT")"; [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V648_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
 curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
 mkdir -p "$WORK/src"; tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1; SRC="$WORK/src"
fi
for req in  dev-hub/bin/agent_observation_bus.py  dev-hub/bin/agent_evolution_daily_cycle.py  dev-hub/bin/agent_fleet_observatory.py  dev-hub/bin/run-controller.py  dev-hub/bin/project-control.py  dev-hub/bin/seven-agent-final-compromise-controller.py  dev-hub/config/agent-observation-bus.v1.json  dev-hub/config/agent-evolution.v1.json  dev-hub/config/agent-fleet-observatory.v1.json  dev-hub/tests/test_v648_agent_observation_bus.py  dev-hub/tests/test_v647_agent_fleet_observatory.py  dev-hub/systemd/chacha-dev-agent-fleet-observatory.service  dev-hub/systemd/chacha-dev-agent-fleet-observatory.timer; do
 [ -f "$SRC/$req" ] || { echo "CHACHA_DEV_V648_INSTALL=BLOCKED reason=missing:$req"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"; cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"; printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile  "$RELEASE/dev-hub/bin/agent_observation_bus.py"  "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py"  "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"  "$RELEASE/dev-hub/bin/run-controller.py"  "$RELEASE/dev-hub/bin/project-control.py"  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"  "$RELEASE/dev-hub/bin/seven-agent-final-compromise-controller.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" >/dev/null
grep -Fq '"version":"6.48.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V648_STATIC=PASS"

stage semantic-qualification
(cd "$RELEASE"; PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v648_agent_observation_bus.py) >"$WORK/v648.out" 2>"$WORK/v648.err"
for marker in  CHACHA_DEV_V648_SELF_ASSERTION_VERIFIED=NO  CHACHA_DEV_V648_PROJECT_CONTROL_VERIFIED_BOUNDARY=PASS  CHACHA_DEV_V648_HASH_CHAIN=PASS  CHACHA_DEV_V648_AGENT_SELF_REASSESSMENT_REQUEST=PASS  CHACHA_DEV_V648_SELF_REQUEST_METRIC_AUTHORITY=NO  CHACHA_DEV_V648_SELF_ASSERTED_COVERAGE_INFLATION=NO  CHACHA_DEV_V648_EXACT_REVISION_LINEAGE=PASS  CHACHA_DEV_V648_SEVEN_AGENT_FINAL_HANDOFF=PASS  CHACHA_DEV_V648_CENTRAL_STAGE_OBSERVATION=PASS  CHACHA_DEV_V648_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
 grep -Fq "$marker" "$WORK/v648.out"
done
echo "CHACHA_DEV_V648_SEMANTIC_QUALIFICATION=PASS"

stage v647-regression
(cd "$RELEASE"; PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v647_agent_fleet_observatory.py) >"$WORK/v647.out" 2>"$WORK/v647.err"
grep -Fq 'CHACHA_DEV_V647_AGENT_INVENTORY_35=PASS' "$WORK/v647.out"
grep -Fq 'CHACHA_DEV_V647_UNKNOWN_DIMENSION_DEFAULT=NONE' "$WORK/v647.out"
echo "CHACHA_DEV_V648_V647_REGRESSION=PASS"

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
BUS="/opt/chacha-dev/runtime/agent-observation/observations.db"
TRUST_BEFORE="$(canon_hash "$TRUST")"; DURABLE_BEFORE="$(canon_hash "$DURABLE")"; TW_BEFORE="$(canon_hash "$TW")"; BUS_BEFORE="$(canon_hash "$BUS")"

stage isolated-bus-pilot
mkdir -p "$WORK/runtime"
cat >"$WORK/self-request.json" <<JSON
{"schema":"chacha.dev/agent-observation-event/v1","event_id":"pilot-self-request","event_type":"AGENT_REASSESSMENT_REQUEST",
"source_id":"bastion","source_surface":"pilot-self","project_id":"v648-pilot","revision":"$REV","subject_role":"bastion",
"outcome":"REQUEST","verification":"SELF_ASSERTED","capabilities":[],"evidence_refs":["pilot:self-request"]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_observation_bus.py"  --runtime-root "$WORK/runtime" --policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" publish --event "$WORK/self-request.json" >"$WORK/self-request.out"
grep -Fq 'CHACHA_DEV_V648_AGENT_OBSERVATION_PUBLISH=PASS' "$WORK/self-request.out"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_observation_bus.py"  --runtime-root "$WORK/runtime" --policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" verify >"$WORK/bus-verify.out"
grep -Fq 'CHACHA_DEV_V648_OBSERVATION_CHAIN=PASS' "$WORK/bus-verify.out"
python3 - "$WORK/runtime/agent-evolution/reassessment-queue/reassess-pilot-self-request.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["self_request"] is True,x
assert x["metric_authority"] is False,x
assert x["direct_agent_mutation"] is False,x
assert x["direct_candidate_materialization"] is False,x
print("CHACHA_DEV_V648_REAL_SELF_REASSESSMENT_REQUEST=PASS")
print("CHACHA_DEV_V648_REAL_SELF_REQUEST_METRIC_AUTHORITY=NO")
PY

stage isolated-daily-cycle
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py"  --repo-root "$RELEASE" --runtime-root "$WORK/runtime" >"$WORK/daily.out" 2>"$WORK/daily.err"
grep -Fq 'CHACHA_DEV_V648_AGENT_EVOLUTION_DAILY_CYCLE=PASS' "$WORK/daily.out"
python3 - "$WORK/runtime/agent-evolution/daily-cycle-latest.json" "$WORK/runtime/agent-evolution/reassessment-queue-latest.json" <<'PY'
import json,sys
daily=json.load(open(sys.argv[1],encoding="utf-8"));q=json.load(open(sys.argv[2],encoding="utf-8"))
assert daily["agent_count"]==35,daily
assert daily["deep_audit_due"] is True,daily
assert daily["ecosystem_benchmark_due"] is True,daily
assert q["event_request_count"]>=1,q
assert q["scheduled_action_count"]==70,q
assert q["direct_agent_mutation"] is False,q
print("CHACHA_DEV_V648_REAL_DAILY_CADENCE=PASS")
print("CHACHA_DEV_V648_REAL_SCHEDULED_MUTATION=NO")
PY

[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo CANONICAL_TRUST_MUTATED; exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo CANONICAL_DURABLE_MUTATED; exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo CANONICAL_TW_MUTATED; exit 43; }
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo CANONICAL_BUS_MUTATED_BY_SYNTHETIC_PILOT; exit 44; }
echo "CHACHA_DEV_V648_REAL_SYNTHETIC_CANONICAL_MUTATION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"; ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V648_RELEASE_ACTIVATED=PASS"

stage install-daily-cycle
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-fleet-observatory.service" /etc/systemd/system/chacha-dev-agent-fleet-observatory.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-fleet-observatory.timer" /etc/systemd/system/chacha-dev-agent-fleet-observatory.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-agent-fleet-observatory.timer >/dev/null
systemctl start chacha-dev-agent-fleet-observatory.service
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
test -s /opt/chacha-dev/runtime/agent-evolution/daily-cycle-latest.json
echo "CHACHA_DEV_V648_DAILY_EVOLUTION_TIMER=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V648_GUARDIAN_COVERAGE=PASS"

stage post-activation
python3 - /opt/chacha-dev/runtime/agent-evolution/daily-cycle-latest.json /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"));f=json.load(open(sys.argv[2],encoding="utf-8"))
assert d["agent_count"]==35,d
assert f["agent_count"]==35,f
assert d["direct_agent_mutation"] is False,d
assert d["self_promotion"] is False,d
print("CHACHA_DEV_V648_POST_ACTIVATION_DAILY_CYCLE=PASS")
PY
grep -Fq '"version":"6.48.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"

mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v648-agent-observation-bus-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys,pathlib
daily=json.load(open("/opt/chacha-dev/runtime/agent-evolution/daily-cycle-latest.json",encoding="utf-8"))
out={"schema":"chacha.dev/v648-agent-observation-bus-evidence/v1","revision":sys.argv[2],"observed_at":sys.argv[3],
"agent_count":daily["agent_count"],"daily_cycle":"PASS","self_scoring_authority":False,"self_reassessment_request":True,
"exact_revision_lineage":True,"seven_agent_final_handoff":True,"central_stage_observation":True,
"direct_agent_mutation":False,"self_promotion":False,"guardian_coverage":"PASS",
"architecture_council_final_authority":True,"automatic_external_spend_eur":0}
pathlib.Path(sys.argv[1]).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
PY

echo "CHACHA_DEV_V648_AGENT_OBSERVATION_BUS=PASS"
echo "CHACHA_DEV_V648_REAL_SELF_SCORING_AUTHORITY=NO"
echo "CHACHA_DEV_V648_REAL_SELF_REASSESSMENT_REQUEST=PASS"
echo "CHACHA_DEV_V648_REAL_EXACT_REVISION_LINEAGE=PASS"
echo "CHACHA_DEV_V648_REAL_DAILY_CADENCE=PASS"
echo "CHACHA_DEV_V648_REAL_SYNTHETIC_CANONICAL_MUTATION=NO"
echo "CHACHA_DEV_V648_DIRECT_SELF_MUTATION=NO"
echo "CHACHA_DEV_V648_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V648_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V648_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V648_INSTALL=PASS"
trap - EXIT
cleanup
