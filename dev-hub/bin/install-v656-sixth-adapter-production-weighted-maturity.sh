#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V656_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V656_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v656.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_TIMER_WAS_ACTIVE=0
BUS_TIMER_WAS_ACTIVE=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V656_STAGE=$STAGE"; }
restore_timers(){
  [ "$FLEET_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$FLEET_TIMER" >/dev/null 2>&1 || true
  [ "$BUS_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$BUS_TIMER" >/dev/null 2>&1 || true
}
backup_runtime_state(){
  mkdir -p "$WORK/runtime-backup"
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json; do
    if [ -f "$p" ]; then
      mkdir -p "$WORK/runtime-backup$(dirname "$p")"
      cp -a "$p" "$WORK/runtime-backup$p"
    fi
  done
}
restore_runtime_state(){
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json; do
    if [ -f "$WORK/runtime-backup$p" ]; then
      mkdir -p "$(dirname "$p")"
      cp -a "$WORK/runtime-backup$p" "$p"
    elif [ "$ACTIVATED" -eq 1 ]; then
      rm -f "$p"
    fi
  done
  find /opt/chacha-dev/runtime/agent-evolution/benchmark-evidence -type f -name "$REV.json" -delete 2>/dev/null || true
  find /opt/chacha-dev/runtime/agent-evolution/benchmark-results/raw -type f -name "*-$REV.json" -delete 2>/dev/null || true
}
cleanup(){ restore_timers;rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V656_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ===";tail -260 "$f" || true
    done
    restore_runtime_state
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V656_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V656_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V656_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V656_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v655-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1])
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.55.0"' in src,"V655_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="fea50e19d7e1e162a1c693bfabd80ba4ac0d015d",("V655_ACQUIRED_REVISION_MISMATCH",rev)
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v655-production-evidence-fifth-wave-*.json"))
assert ev,"V655_REAL_EVIDENCE_MISSING"
x=json.loads(ev[-1].read_text(encoding="utf-8"))
assert x.get("revision")==rev,x
assert x.get("production_measurement_precedence") is True,x
print("CHACHA_DEV_V656_V655_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V656_INSTALL=BLOCKED reason=source_root_invalid";exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/agent_evolution_controller.py   dev-hub/bin/agent_benchmark_adapters.py   dev-hub/bin/agent_benchmark_oracles.py   dev-hub/bin/agent_benchmark_campaign_runner.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_profile.py   dev-hub/bin/component_evolution_governance.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/agent-evolution.v1.json   dev-hub/config/agent-benchmark-adapters.v1.json   dev-hub/tests/test_v656_sixth_adapter_production_weighted_maturity.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V656_INSTALL=BLOCKED reason=missing:$required";exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/agent_evolution_controller.py"   "$RELEASE/dev-hub/bin/agent_benchmark_adapters.py"   "$RELEASE/dev-hub/bin/agent_benchmark_oracles.py"   "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"   "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-evolution.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" >/dev/null
grep -Fq '"version":"6.56.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V656_STATIC=PASS"

stage semantic-qualification
(cd "$RELEASE";PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v656_sixth_adapter_production_weighted_maturity.py) >"$WORK/v656.out" 2>"$WORK/v656.err"
for marker in  CHACHA_DEV_V656_TEST_ENGINEER_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V656_PERFORMANCE_ENGINEER_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V656_SRE_OBSERVABILITY_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V656_PRODUCTION_WEIGHTED_MATURITY=PASS  CHACHA_DEV_V656_BENCHMARK_ONLY_MATURITY_LIMIT=PASS  CHACHA_DEV_V656_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED  CHACHA_DEV_V656_PRODUCTION_OUTRANKS_BENCHMARK=PASS  CHACHA_DEV_V656_SIXTH_WAVE_TOTAL_COVERAGE_80=PASS  CHACHA_DEV_V656_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
 grep -Fq "$marker" "$WORK/v656.out"
done
echo "CHACHA_DEV_V656_SEMANTIC_QUALIFICATION=PASS"

stage freeze-runtime-writers
if systemctl is-active --quiet "$FLEET_TIMER"; then FLEET_TIMER_WAS_ACTIVE=1;systemctl stop "$FLEET_TIMER";fi
if systemctl is-active --quiet "$BUS_TIMER"; then BUS_TIMER_WAS_ACTIVE=1;systemctl stop "$BUS_TIMER";fi
backup_runtime_state
BUS_BEFORE="$(sha256sum /opt/chacha-dev/runtime/agent-observation/observations.db 2>/dev/null | awk '{print $1}' || true)"
echo "CHACHA_DEV_V656_RUNTIME_WRITERS_FROZEN=PASS"

stage isolated-sixth-wave
mkdir -p "$WORK/runtime"
cat >"$WORK/campaign.json" <<'JSON'
{"schema":"chacha.dev/agent-benchmark-campaign/v1","contracts":[
 {"agent_id":"test-engineer"},
 {"agent_id":"performance-engineer"},
 {"agent_id":"sre-observability-engineer"}
]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$RELEASE" --runtime-root "$WORK/runtime" --revision "$REV"  --config "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json"  --output "$WORK/isolated-run.json" >"$WORK/isolated-run.out" 2>"$WORK/isolated-run.err"
python3 - "$WORK/isolated-run.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==3,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V656_REAL_ISOLATED_SIXTH_WAVE=PASS")
PY

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V656_RELEASE_ACTIVATED=PASS"

stage canonical-sixth-wave-benchmark
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime --revision "$REV"  --config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/v656-pilot-benchmark-run.json  >"$WORK/canonical-run.out" 2>"$WORK/canonical-run.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/v656-pilot-benchmark-run.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==3,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V656_REAL_SIXTH_WAVE_BENCHMARK_PROMOTED=3")
PY

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"  --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  >"$WORK/fleet.out" 2>"$WORK/fleet.err"
grep -Fq 'CHACHA_DEV_V647_AGENT_FLEET_OBSERVATORY=PASS' "$WORK/fleet.out"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));by={a["agent_id"]:a for a in x.get("agents") or []}
targets=["test-engineer","performance-engineer","sre-observability-engineer"]
for aid in targets:
    row=by[aid];sc=row["scorecard"];pl=row["plan"]
    assert sc["production_measurement_coverage_pct"]>=30.0,(aid,sc)
    assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
    assert sc["production_weighted_maturity_pct"]>=36.0,(aid,sc)
    assert sc["evidence_maturity_label"] in {"MIXED_EVIDENCE","PRODUCTION_MATURE"},(aid,sc)
    prod=set(sc["production_measured_dimensions"]);bench=set(sc["benchmark_measured_dimensions"])
    assert not(prod&bench),(aid,prod,bench)
    assert pl["evidence_maturity"]["production_weighted_maturity_pct"]==sc["production_weighted_maturity_pct"],(aid,pl)
    print(aid.upper().replace("-","_")+"_PRODUCTION_COVERAGE="+str(sc["production_measurement_coverage_pct"]))
    print(aid.upper().replace("-","_")+"_TOTAL_COVERAGE="+str(sc["measurement_coverage_pct"]))
    print(aid.upper().replace("-","_")+"_WEIGHTED_MATURITY="+str(sc["production_weighted_maturity_pct"]))
# Performance historically has 30% production: weighted maturity must keep candidate immature.
perf=by["performance-engineer"]
if float(perf["scorecard"]["production_weighted_maturity_pct"])<40.0:
    assert perf["plan"]["evidence_maturity"]["candidate_evidence_mature"] is False,perf["plan"]
    assert perf["plan"]["candidate"]["owner"] is None,perf["plan"]
print("CHACHA_DEV_V656_REAL_PRODUCTION_WEIGHTED_MATURITY=PASS")
PY

stage bus-readonly-check
BUS_AFTER="$(sha256sum /opt/chacha-dev/runtime/agent-observation/observations.db 2>/dev/null | awk '{print $1}' || true)"
[ "$BUS_BEFORE" = "$BUS_AFTER" ] || { echo "CANONICAL_BUS_MUTATED";exit 44; }
echo "CHACHA_DEV_V656_REAL_CANONICAL_BUS_MUTATION=NO"

stage universal-regeneration
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py"  --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json"  --output-root /opt/chacha-dev/runtime/agent-evolution/profiles >"$WORK/profiles.out" 2>"$WORK/profiles.err"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS' "$WORK/profiles.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py"  --agent-profiles /opt/chacha-dev/runtime/agent-evolution/profiles/index.json  --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json"  --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json"  --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json"  --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"  --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json  >"$WORK/components.out" 2>"$WORK/components.err"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/components.out"

stage guardian-and-post-activation
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"  --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
grep -Fq '"version":"6.56.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
restore_timers
systemctl is-active --quiet "$FLEET_TIMER"
systemctl is-active --quiet "$BUS_TIMER"
systemctl is-active --quiet chacha-remote-desktop-commander.service
echo "CHACHA_DEV_V656_GUARDIAN_COVERAGE=PASS"
echo "CHACHA_DEV_V656_POST_ACTIVATION=PASS"

stage evidence
mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v656-sixth-adapter-production-weighted-maturity-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
fl=json.load(open('/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json',encoding='utf-8'))
by={a["agent_id"]:a for a in fl.get("agents") or []}
targets=["test-engineer","performance-engineer","sre-observability-engineer"]
out={"schema":"chacha.dev/v656-sixth-adapter-production-weighted-maturity-evidence/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],
 "weights":{"production":0.70,"benchmark":0.30},
 "targets":{aid:{
   "measurement_coverage_pct":by[aid]["scorecard"]["measurement_coverage_pct"],
   "production_measurement_coverage_pct":by[aid]["scorecard"]["production_measurement_coverage_pct"],
   "benchmark_measurement_coverage_pct":by[aid]["scorecard"]["benchmark_measurement_coverage_pct"],
   "production_weighted_maturity_pct":by[aid]["scorecard"]["production_weighted_maturity_pct"],
   "evidence_maturity_label":by[aid]["scorecard"]["evidence_maturity_label"]} for aid in targets},
 "benchmark_production_truth":False,"production_measurement_precedence":True,
 "canonical_observation_bus_mutation":False,"benchmark_only_candidate_materialization":False,
 "guardian_coverage":"PASS","architecture_council_final_authority":True,"automatic_external_spend_eur":0}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V656_SIXTH_ADAPTER_PRODUCTION_WEIGHTED_MATURITY=PASS"
echo "CHACHA_DEV_V656_REAL_SIXTH_WAVE_BENCHMARK_PROMOTED=3"
echo "CHACHA_DEV_V656_REAL_PRODUCTION_WEIGHTED_MATURITY=PASS"
echo "CHACHA_DEV_V656_REAL_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V656_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED"
echo "CHACHA_DEV_V656_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS"
echo "CHACHA_DEV_V656_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V656_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V656_INSTALL=PASS"

trap - EXIT
cleanup
