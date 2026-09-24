#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V659_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V659_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v659.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_TIMER_WAS_ACTIVE=0
BUS_TIMER_WAS_ACTIVE=0
STAGE="bootstrap"

stage(){ STAGE="$1";echo "CHACHA_DEV_V659_STAGE=$STAGE"; }
restore_timers(){
  [ "$FLEET_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$FLEET_TIMER" >/dev/null 2>&1 || true
  [ "$BUS_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$BUS_TIMER" >/dev/null 2>&1 || true
}
backup_runtime(){
  mkdir -p "$WORK/backup"
  for p in /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json /opt/chacha-dev/runtime/agent-evolution/profiles/index.json /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json /opt/chacha-dev/runtime/guardian/coverage-latest.json; do
    if [ -f "$p" ]; then mkdir -p "$WORK/backup$(dirname "$p")";cp -a "$p" "$WORK/backup$p";fi
  done
}
restore_runtime(){
  for p in /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json /opt/chacha-dev/runtime/agent-evolution/profiles/index.json /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json /opt/chacha-dev/runtime/guardian/coverage-latest.json; do
    if [ -f "$WORK/backup$p" ]; then mkdir -p "$(dirname "$p")";cp -a "$WORK/backup$p" "$p";fi
  done
}
cleanup(){ restore_timers;rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V659_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do [ -s "$f" ] || continue;echo "=== $(basename "$f") ===";tail -220 "$f" || true;done
    restore_runtime
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT";echo "CHACHA_DEV_V659_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V659_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V659_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V659_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v658-real-baseline
python3 - "$PREVIOUS" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1])
assert '"version":"6.58.0"' in (root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text()
rev=(root/".revision").read_text().strip()
assert rev=="c50c54de0fd81bf7bb362c5d855d6e7184d17355",rev
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v658-visual-content-project-radar-*.json"))
assert ev
x=json.loads(ev[-1].read_text())
assert x.get("revision")==rev and x.get("canonical_observation_bus_mutation") is False,x
print("CHACHA_DEV_V659_V658_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then SRC="$(readlink -f "$SOURCE_ROOT")";[ -d "$SRC/dev-hub" ] || exit 2
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1;SRC="$WORK/src"
fi
for p in dev-hub/bin/agent_fleet_observatory.py dev-hub/bin/agent_evolution_controller.py dev-hub/bin/agent_evolution_profile.py dev-hub/bin/component_evolution_governance.py dev-hub/bin/autonomous-project-orchestrator.py dev-hub/config/agent-fleet-observatory.v1.json dev-hub/tests/test_v659_production_evidence_operational_maturity.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V659_INSTALL=BLOCKED reason=missing:$p";exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
python3 -m py_compile "$RELEASE/dev-hub/bin/agent_fleet_observatory.py" "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py" "$RELEASE/dev-hub/tests/test_v659_production_evidence_operational_maturity.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" >/dev/null
grep -Fq '"version":"6.59.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
(cd "$RELEASE";PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v659_production_evidence_operational_maturity.py) >"$WORK/v659.out" 2>"$WORK/v659.err"
grep -Fq 'CHACHA_DEV_V659_GUARDIAN_ACCURACY_INFERENCE=NO' "$WORK/v659.out"
grep -Fq 'CHACHA_DEV_V659_SENTINEL_ACCURACY_INFERENCE=NO' "$WORK/v659.out"
grep -Fq 'CHACHA_DEV_V659_ACCEPTANCE_ACCURACY_INFERENCE=NO' "$WORK/v659.out"
echo "CHACHA_DEV_V659_STATIC_AND_SEMANTIC=PASS"

stage real-operational-preflight
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_fleet_observatory.py" --repo-root "$RELEASE" --runtime-root /opt/chacha-dev/runtime --policy "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" --evolution-policy "$RELEASE/dev-hub/config/agent-evolution.v1.json" --routing "$RELEASE/dev-hub/config/agent-routing.v1.json" --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json" --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" --output "$WORK/preflight.json" >"$WORK/preflight.out"
python3 - "$WORK/preflight.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in x["agents"]}
mins={"guardian":2,"sentinel":2,"acceptance-engineer":2}
for aid,n in mins.items():
    a=by[aid];sc=a["scorecard"];sig=a["metrics"]["signals"]
    assert sig["operational_accuracy_evidence"]==0,(aid,sig)
    assert sig["operational_structural_evidence"]>=n,(aid,sig)
    assert sc["production_measurement_coverage_pct"]==30.0,(aid,sc)
    assert sc["benchmark_measurement_coverage_pct"]==50.0,(aid,sc)
    assert sc["measurement_coverage_pct"]==80.0 and sc["production_weighted_maturity_pct"]==36.0,(aid,sc)
    assert set(sc["production_measured_dimensions"])=={"authority_discipline","evidence_quality","handoff_quality"},(aid,sc)
    assert sc["dimension_evidence"]["accuracy"].get("evidence_scope")=="BENCHMARK_ONLY",(aid,sc)
print("CHACHA_DEV_V659_REAL_OPERATIONAL_PREFLIGHT=PASS")
PY

stage freeze-runtime
if systemctl is-active --quiet "$FLEET_TIMER"; then FLEET_TIMER_WAS_ACTIVE=1;systemctl stop "$FLEET_TIMER";fi
if systemctl is-active --quiet "$BUS_TIMER"; then BUS_TIMER_WAS_ACTIVE=1;systemctl stop "$BUS_TIMER";fi
backup_runtime
BUS_BEFORE="$(sha256sum /opt/chacha-dev/runtime/agent-observation/observations.db 2>/dev/null | awk '{print $1}' || true)"
BENCH_BEFORE="$(python3 - <<'PY'
import hashlib,pathlib
h=hashlib.sha256();root=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/benchmark-evidence")
for p in sorted(root.glob("**/*.json")):
    h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
print(h.hexdigest())
PY
)"
echo "CHACHA_DEV_V659_RUNTIME_WRITERS_FROZEN=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V659_RELEASE_ACTIVATED=PASS"

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json" --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json" --routing "$CURRENT/dev-hub/config/agent-routing.v1.json" --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json" --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json >"$WORK/fleet.out"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in x["agents"]}
for aid in ("guardian","sentinel","acceptance-engineer"):
    a=by[aid];sc=a["scorecard"];pl=a["plan"]
    assert sc["production_measurement_coverage_pct"]==30.0,(aid,sc)
    assert sc["benchmark_measurement_coverage_pct"]==50.0,(aid,sc)
    assert sc["measurement_coverage_pct"]==80.0 and sc["production_weighted_maturity_pct"]==36.0,(aid,sc)
    assert sc["dimension_evidence"]["accuracy"].get("evidence_scope")=="BENCHMARK_ONLY",(aid,sc)
    assert pl["evidence_maturity"]["candidate_evidence_mature"] is False,(aid,pl)
print("CHACHA_DEV_V659_REAL_WEIGHTED_EVIDENCE=PASS")
PY

stage immutability-checks
BUS_AFTER="$(sha256sum /opt/chacha-dev/runtime/agent-observation/observations.db 2>/dev/null | awk '{print $1}' || true)"
[ "$BUS_BEFORE" = "$BUS_AFTER" ] || { echo "CANONICAL_BUS_MUTATED";exit 44; }
BENCH_AFTER="$(python3 - <<'PY'
import hashlib,pathlib
h=hashlib.sha256();root=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/benchmark-evidence")
for p in sorted(root.glob("**/*.json")):
    h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
print(h.hexdigest())
PY
)"
[ "$BENCH_BEFORE" = "$BENCH_AFTER" ] || { echo "BENCHMARK_EVIDENCE_MUTATED";exit 45; }
echo "CHACHA_DEV_V659_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V659_BENCHMARK_EVIDENCE_MUTATION=NO"

stage universal-regeneration
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py" --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json --routing "$CURRENT/dev-hub/config/agent-routing.v1.json" --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json" --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json" --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json" --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json" --output-root /opt/chacha-dev/runtime/agent-evolution/profiles >"$WORK/profiles.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py" --agent-profiles /opt/chacha-dev/runtime/agent-evolution/profiles/index.json --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json" --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json" --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json" --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json" --output /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json >"$WORK/components.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/components.out"

stage guardian-post
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py" --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" --client "$CURRENT/dev-hub/bin/guardian-client.py" --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
restore_timers
systemctl is-active --quiet "$FLEET_TIMER";systemctl is-active --quiet "$BUS_TIMER";systemctl is-active --quiet chacha-remote-desktop-commander.service
echo "CHACHA_DEV_V659_GUARDIAN_COVERAGE=PASS"

stage evidence
mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v659-production-evidence-operational-maturity-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
f=json.load(open("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json"));by={a["agent_id"]:a for a in f["agents"]}
targets=("guardian","sentinel","acceptance-engineer")
out={"schema":"chacha.dev/v659-production-evidence-operational-maturity/v1","revision":sys.argv[2],"observed_at":sys.argv[3],
 "targets":{aid:{"production":by[aid]["scorecard"]["production_measurement_coverage_pct"],"benchmark":by[aid]["scorecard"]["benchmark_measurement_coverage_pct"],"weighted":by[aid]["scorecard"]["production_weighted_maturity_pct"],"label":by[aid]["scorecard"]["evidence_maturity_label"],"accuracy_scope":(by[aid]["scorecard"]["dimension_evidence"]["accuracy"] or {}).get("evidence_scope")} for aid in targets},
 "guardian_accuracy_inference":False,"sentinel_accuracy_inference":False,"acceptance_accuracy_inference":False,
 "benchmark_evidence_mutation":False,"canonical_observation_bus_mutation":False,"production_measurement_precedence":True,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
open(sys.argv[1],"w").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V659_PRODUCTION_EVIDENCE_OPERATIONAL_MATURITY=PASS"
echo "CHACHA_DEV_V659_GUARDIAN_STRUCTURAL_PRODUCTION_EVIDENCE=PASS"
echo "CHACHA_DEV_V659_SENTINEL_STRUCTURAL_PRODUCTION_EVIDENCE=PASS"
echo "CHACHA_DEV_V659_ACCEPTANCE_STRUCTURAL_PRODUCTION_EVIDENCE=PASS"
echo "CHACHA_DEV_V659_ALL_THREE_ACCURACY_INFERENCE=NO"
echo "CHACHA_DEV_V659_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V659_BENCHMARK_EVIDENCE_MUTATION=NO"
echo "CHACHA_DEV_V659_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V659_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V659_INSTALL=PASS"

trap - EXIT
cleanup
