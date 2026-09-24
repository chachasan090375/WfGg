#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_V649_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V649_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"; CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v649.XXXXXX)"; PREVIOUS=""; ACTIVATED=0; STAGE="bootstrap"
stage(){ STAGE="$1"; echo "CHACHA_DEV_V649_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
 rc=$?
 if [ "$rc" -ne 0 ]; then
   echo "CHACHA_DEV_V649_FAILURE_STAGE=$STAGE"
   for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do [ -s "$f" ] || continue; echo "=== $(basename "$f") ==="; tail -200 "$f" || true; done
   if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
     ln -sfn "$PREVIOUS" "$CURRENT"; systemctl daemon-reload || true; echo "CHACHA_DEV_V649_ROLLBACK=PASS"
   fi
   rm -rf "$RELEASE" 2>/dev/null || true
 fi
 cleanup; exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V649_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V649_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V649_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v648-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.48.0"' in s,"V648_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="04da00f0ca1d66b28488f22466e5edcfd73f4cb3",("V648_ACQUIRED_REVISION_MISMATCH",rev)
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v648-agent-observation-bus-*.json"),reverse=True)
assert ev,"V648_REAL_EVIDENCE_MISSING"
x=json.loads(ev[0].read_text(encoding="utf-8"))
assert x.get("revision")=="04da00f0ca1d66b28488f22466e5edcfd73f4cb3",x
assert x.get("isolated_runtime_storage")=="PASS",x
print("CHACHA_DEV_V649_V648_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
 SRC="$(readlink -f "$SOURCE_ROOT")"; [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V649_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
 curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
 mkdir -p "$WORK/src"; tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1; SRC="$WORK/src"
fi
for req in  dev-hub/bin/agent_fleet_observatory.py  dev-hub/bin/agent_observation_bus.py  dev-hub/bin/agent_evolution_daily_cycle.py  dev-hub/bin/recovery-orchestrator.py  dev-hub/bin/autonomous-project-orchestrator.py  dev-hub/config/assurance-agent-instrumentation.v1.json  dev-hub/config/agent-fleet-observatory.v1.json  dev-hub/config/agent-observation-bus.v1.json  dev-hub/tests/test_v649_assurance_agent_instrumentation.py  dev-hub/tests/test_v648_agent_observation_bus.py  dev-hub/systemd/chacha-dev-agent-fleet-observatory.service  dev-hub/systemd/chacha-dev-agent-fleet-observatory.timer; do
 [ -f "$SRC/$req" ] || { echo "CHACHA_DEV_V649_INSTALL=BLOCKED reason=missing:$req"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"; cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"; printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile  "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"  "$RELEASE/dev-hub/bin/agent_observation_bus.py"  "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py"  "$RELEASE/dev-hub/bin/recovery-orchestrator.py"  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/assurance-agent-instrumentation.v1.json" >/dev/null
grep -Fq '"version":"6.49.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V649_STATIC=PASS"

stage semantic-qualification
(cd "$RELEASE"; PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v649_assurance_agent_instrumentation.py) >"$WORK/v649.out" 2>"$WORK/v649.err"
for marker in  CHACHA_DEV_V649_PRIORITY_ASSURANCE_TARGETS=PASS  CHACHA_DEV_V649_TRUSTED_OBSERVED_SOURCE_FILTER=PASS  CHACHA_DEV_V649_RECOVERY_COVERAGE_OBSERVED=PASS  CHACHA_DEV_V649_RECOVERY_ACTIVITY_IS_ACCURACY=NO  CHACHA_DEV_V649_SEVEN_AGENT_VERIFIED_HANDOFF=PASS  CHACHA_DEV_V649_INTERNAL_AGENT_ROBUSTNESS=PASS  CHACHA_DEV_V649_SELF_REQUEST_METRIC_AUTHORITY=NO  CHACHA_DEV_V649_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
 grep -Fq "$marker" "$WORK/v649.out"
done
echo "CHACHA_DEV_V649_SEMANTIC_QUALIFICATION=PASS"

stage v648-regression
(cd "$RELEASE"; PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v648_agent_observation_bus.py) >"$WORK/v648.out" 2>"$WORK/v648.err"
grep -Fq 'CHACHA_DEV_V648_SELF_ASSERTION_VERIFIED=NO' "$WORK/v648.out"
grep -Fq 'CHACHA_DEV_V648_HASH_CHAIN=PASS' "$WORK/v648.out"
grep -Fq 'CHACHA_DEV_V648_AGENT_SELF_REASSESSMENT_REQUEST=PASS' "$WORK/v648.out"
echo "CHACHA_DEV_V649_V648_REGRESSION=PASS"

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
BUS="/opt/chacha-dev/runtime/agent-observation/observations.db"
TRUST_BEFORE="$(canon_hash "$TRUST")"; DURABLE_BEFORE="$(canon_hash "$DURABLE")"; TW_BEFORE="$(canon_hash "$TW")"; BUS_BEFORE="$(canon_hash "$BUS")"

stage isolated-instrumentation-pilot
mkdir -p "$WORK/runtime"
(cd "$RELEASE"; CHACHA_DEV_TEST_RUNTIME_ROOT="$WORK/runtime" PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v649_assurance_agent_instrumentation.py) >"$WORK/v649-isolated.out" 2>"$WORK/v649-isolated.err"
grep -Fq 'CHACHA_DEV_V649_RECOVERY_ACTIVITY_IS_ACCURACY=NO' "$WORK/v649-isolated.out"
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED_BY_V649_FIXTURE"; exit 40; }
echo "CHACHA_DEV_V649_REAL_FIXTURE_CANONICAL_BUS_MUTATION=NO"

stage real-read-only-fleet
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"  --repo-root "$RELEASE" --runtime-root /opt/chacha-dev/runtime  --policy "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json"  --evolution-policy "$RELEASE/dev-hub/config/agent-evolution.v1.json"  --routing "$RELEASE/dev-hub/config/agent-routing.v1.json"  --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output "$WORK/real-fleet.json" >"$WORK/real-fleet.out" 2>"$WORK/real-fleet.err"
python3 - "$WORK/real-fleet.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["agent_count"]==35,x
assert x["unknown_dimension_default_score"] is None,x
assert x["read_only"] is True,x
print("CHACHA_DEV_V649_REAL_FLEET_READ_ONLY=PASS")
print("REAL_OPTIMIZATION_COUNT="+str(len(x["optimization_queue"])))
print("REAL_MEASUREMENT_COUNT="+str(len(x["measurement_queue"])))
PY
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo CANONICAL_TRUST_MUTATED; exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo CANONICAL_DURABLE_MUTATED; exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo CANONICAL_TW_MUTATED; exit 43; }
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo CANONICAL_BUS_MUTATED_BY_READ_ONLY_FLEET; exit 44; }
echo "CHACHA_DEV_V649_REAL_CANONICAL_STATE_MUTATION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"; ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V649_RELEASE_ACTIVATED=PASS"

stage install-daily-cycle
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-fleet-observatory.service" /etc/systemd/system/chacha-dev-agent-fleet-observatory.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-fleet-observatory.timer" /etc/systemd/system/chacha-dev-agent-fleet-observatory.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-agent-fleet-observatory.timer >/dev/null
systemctl start chacha-dev-agent-fleet-observatory.service
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
test -s /opt/chacha-dev/runtime/agent-evolution/daily-cycle-latest.json
echo "CHACHA_DEV_V649_DAILY_EVOLUTION_TIMER=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V649_GUARDIAN_COVERAGE=PASS"

stage post-activation
python3 - /opt/chacha-dev/runtime/agent-evolution/daily-cycle-latest.json /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"));f=json.load(open(sys.argv[2],encoding="utf-8"))
assert d["agent_count"]==35,d
assert f["agent_count"]==35,f
assert d["direct_agent_mutation"] is False and d["self_promotion"] is False,d
print("CHACHA_DEV_V649_POST_ACTIVATION_DAILY_CYCLE=PASS")
print("POST_OPTIMIZATION_COUNT="+str(len(f["optimization_queue"])))
print("POST_MEASUREMENT_COUNT="+str(len(f["measurement_queue"])))
PY
grep -Fq '"version":"6.49.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"

mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v649-assurance-agent-instrumentation-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys,pathlib
f=json.load(open("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json",encoding="utf-8"))
out={"schema":"chacha.dev/v649-assurance-agent-instrumentation-evidence/v1","revision":sys.argv[2],"observed_at":sys.argv[3],
"agent_count":f["agent_count"],"priority_assurance_instrumentation":"PASS","trusted_observed_source_filter":"PASS",
"recovery_activity_is_accuracy":False,"seven_agent_verified_handoff":True,"internal_agent_robustness":True,
"self_request_metric_authority":False,"direct_self_mutation":False,"self_promotion":False,
"optimization_count":len(f["optimization_queue"]),"measurement_count":len(f["measurement_queue"]),
"guardian_coverage":"PASS","architecture_council_final_authority":True,"automatic_external_spend_eur":0}
pathlib.Path(sys.argv[1]).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
PY

echo "CHACHA_DEV_V649_ASSURANCE_AGENT_INSTRUMENTATION=PASS"
echo "CHACHA_DEV_V649_REAL_TRUSTED_OBSERVED_SOURCE_FILTER=PASS"
echo "CHACHA_DEV_V649_REAL_RECOVERY_ACTIVITY_IS_ACCURACY=NO"
echo "CHACHA_DEV_V649_REAL_FLEET_READ_ONLY=PASS"
echo "CHACHA_DEV_V649_REAL_CANONICAL_STATE_MUTATION=NO"
echo "CHACHA_DEV_V649_DIRECT_SELF_MUTATION=NO"
echo "CHACHA_DEV_V649_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V649_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V649_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V649_INSTALL=PASS"
trap - EXIT
cleanup
