#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V658_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V658_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v658.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_TIMER_WAS_ACTIVE=0
BUS_TIMER_WAS_ACTIVE=0
STAGE="bootstrap"

stage(){ STAGE="$1";echo "CHACHA_DEV_V658_STAGE=$STAGE"; }
restore_timers(){
  [ "$FLEET_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$FLEET_TIMER" >/dev/null 2>&1 || true
  [ "$BUS_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$BUS_TIMER" >/dev/null 2>&1 || true
}
cleanup_candidate_evidence(){
  python3 - "$REV" <<'PY'
from pathlib import Path
import sys
rev=sys.argv[1];root=Path("/opt/chacha-dev/runtime/agent-evolution")
for aid in ("graphics-specialist","animation-specialist","ui-layout-specialist","translation-specialist","publication-specialist","technology-radar-agent"):
    p=root/"benchmark-evidence"/aid/(rev+".json")
    if p.is_file():p.unlink()
raw=root/"benchmark-results"/"raw"
if raw.is_dir():
    for p in raw.glob("*-"+rev+".json"):p.unlink()
pilot=root/"v658-pilot-benchmark-run.json"
if pilot.is_file():pilot.unlink()
PY
}
backup_runtime_state(){
  mkdir -p "$WORK/runtime-backup"
  for p in /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json /opt/chacha-dev/runtime/agent-evolution/profiles/index.json /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json; do
    if [ -f "$p" ]; then mkdir -p "$WORK/runtime-backup$(dirname "$p")";cp -a "$p" "$WORK/runtime-backup$p";fi
  done
}
restore_runtime_state(){
  for p in /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json /opt/chacha-dev/runtime/agent-evolution/profiles/index.json /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json; do
    if [ -f "$WORK/runtime-backup$p" ]; then mkdir -p "$(dirname "$p")";cp -a "$WORK/runtime-backup$p" "$p"
    elif [ "$ACTIVATED" -eq 1 ]; then rm -f "$p";fi
  done
  cleanup_candidate_evidence
}
cleanup(){ restore_timers;rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V658_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do [ -s "$f" ] || continue;echo "=== $(basename "$f") ===";tail -260 "$f" || true;done
    restore_runtime_state
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT";echo "CHACHA_DEV_V658_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V658_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V658_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V658_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v657-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1]);src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.57.0"' in src,"V657_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="253ce8e058bb1eb034c26a6829e8acbf13c67e7b",("V657_ACQUIRED_REVISION_MISMATCH",rev)
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v657-seventh-adapter-authority-specialist-*.json"))
assert ev,"V657_REAL_EVIDENCE_MISSING";x=json.loads(ev[-1].read_text(encoding="utf-8"))
assert x.get("revision")==rev,x
assert x.get("canonical_observation_bus_mutation") is False,x
print("CHACHA_DEV_V658_V657_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then SRC="$(readlink -f "$SOURCE_ROOT")";[ -d "$SRC/dev-hub" ] || exit 2
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1;SRC="$WORK/src"
fi
for required in dev-hub/bin/agent_benchmark_adapters.py dev-hub/bin/agent_benchmark_oracles.py dev-hub/bin/agent_benchmark_campaign_runner.py dev-hub/bin/agent_fleet_observatory.py dev-hub/bin/agent_evolution_controller.py dev-hub/bin/agent_evolution_profile.py dev-hub/bin/component_evolution_governance.py dev-hub/bin/domain-provider-resolver.py dev-hub/adapters/radar-runtime-adapter.py dev-hub/bin/autonomous-project-orchestrator.py dev-hub/config/agent-benchmark-adapters.v1.json dev-hub/config/agent-fleet-observatory.v1.json dev-hub/config/domain-orchestration.v1.json dev-hub/tests/test_v658_visual_content_project_radar_evidence.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V658_INSTALL=BLOCKED reason=missing:$required";exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile "$RELEASE/dev-hub/bin/agent_benchmark_adapters.py" "$RELEASE/dev-hub/bin/agent_benchmark_oracles.py" "$RELEASE/dev-hub/bin/agent_fleet_observatory.py" "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py" "$RELEASE/dev-hub/tests/test_v658_visual_content_project_radar_evidence.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/domain-orchestration.v1.json" >/dev/null
grep -Fq '"version":"6.58.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V658_STATIC=PASS"

stage semantic-qualification
(cd "$RELEASE";PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v658_visual_content_project_radar_evidence.py) >"$WORK/v658.out" 2>"$WORK/v658.err"
for marker in CHACHA_DEV_V658_GRAPHICS_EXECUTABLE_CONTRACT=PASS CHACHA_DEV_V658_ANIMATION_EXECUTABLE_CONTRACT=PASS CHACHA_DEV_V658_UI_LAYOUT_ROLE_ALIGNMENT=PASS CHACHA_DEV_V658_TRANSLATION_EXECUTABLE_CONTRACT=PASS CHACHA_DEV_V658_PUBLICATION_EXECUTABLE_CONTRACT=PASS CHACHA_DEV_V658_PROJECT_LOCAL_RADAR_READONLY_ADAPTER=PASS CHACHA_DEV_V658_RADAR_STRUCTURAL_PRODUCTION_EVIDENCE=PASS CHACHA_DEV_V658_RADAR_ACCURACY_FROM_PROMOTION=NO CHACHA_DEV_V658_PLATFORM_ROUTING_FOR_RADAR=FORBIDDEN CHACHA_DEV_V658_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do grep -Fq "$marker" "$WORK/v658.out";done
echo "CHACHA_DEV_V658_SEMANTIC_QUALIFICATION=PASS"

stage real-radar-production-preflight
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_fleet_observatory.py" --repo-root "$RELEASE" --runtime-root /opt/chacha-dev/runtime --policy "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" --evolution-policy "$RELEASE/dev-hub/config/agent-evolution.v1.json" --routing "$RELEASE/dev-hub/config/agent-routing.v1.json" --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json" --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" --output "$WORK/preflight-fleet.json" >"$WORK/preflight.out"
python3 - "$WORK/preflight-fleet.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in x["agents"]};r=by["technology-radar-agent"]
assert r["scorecard"]["production_measurement_coverage_pct"]==20.0,r
assert set(r["scorecard"]["production_measured_dimensions"])=={"authority_discipline","evidence_quality"},r
assert int(r["metrics"]["signals"].get("project_adapter_evidence") or 0)>=1,r
print("CHACHA_DEV_V658_REAL_RADAR_STRUCTURAL_PREFLIGHT=PASS")
PY

stage freeze-runtime-writers
if systemctl is-active --quiet "$FLEET_TIMER"; then FLEET_TIMER_WAS_ACTIVE=1;systemctl stop "$FLEET_TIMER";fi
if systemctl is-active --quiet "$BUS_TIMER"; then BUS_TIMER_WAS_ACTIVE=1;systemctl stop "$BUS_TIMER";fi
backup_runtime_state;cleanup_candidate_evidence
BUS_BEFORE="$(sha256sum /opt/chacha-dev/runtime/agent-observation/observations.db 2>/dev/null | awk '{print $1}' || true)"
echo "CHACHA_DEV_V658_RUNTIME_WRITERS_FROZEN=PASS"

stage isolated-eighth-wave
mkdir -p "$WORK/runtime"
cat >"$WORK/campaign.json" <<'JSON'
{"schema":"chacha.dev/agent-benchmark-campaign/v1","contracts":[
 {"agent_id":"graphics-specialist"},{"agent_id":"animation-specialist"},{"agent_id":"ui-layout-specialist"},
 {"agent_id":"translation-specialist"},{"agent_id":"publication-specialist"},{"agent_id":"technology-radar-agent"}
]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py" --campaign "$WORK/campaign.json" --repo-root "$RELEASE" --runtime-root "$WORK/runtime" --revision "$REV" --config "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" --output "$WORK/isolated-run.json" >"$WORK/isolated.out" 2>"$WORK/isolated.err"
python3 - "$WORK/isolated-run.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x["promoted_count"]==6,x
assert x["benchmark_fixture_is_production_truth"] is False and x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V658_REAL_ISOLATED_EIGHTH_WAVE=PASS")
PY

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V658_RELEASE_ACTIVATED=PASS"

stage canonical-eighth-wave
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_benchmark_campaign_runner.py" --campaign "$WORK/campaign.json" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime --revision "$REV" --config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json" --output /opt/chacha-dev/runtime/agent-evolution/v658-pilot-benchmark-run.json >"$WORK/canonical.out" 2>"$WORK/canonical.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/v658-pilot-benchmark-run.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x["promoted_count"]==6,x
assert x["benchmark_fixture_is_production_truth"] is False and x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V658_REAL_EIGHTH_WAVE_BENCHMARK_PROMOTED=6")
PY

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json" --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json" --routing "$CURRENT/dev-hub/config/agent-routing.v1.json" --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json" --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json >"$WORK/fleet.out" 2>"$WORK/fleet.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in x["agents"]}
visual=("graphics-specialist","animation-specialist","ui-layout-specialist","translation-specialist","publication-specialist")
for aid in visual:
    sc=by[aid]["scorecard"];pl=by[aid]["plan"]
    assert sc["production_measurement_coverage_pct"]==0.0,(aid,sc)
    assert sc["benchmark_measurement_coverage_pct"]==80.0 and sc["measurement_coverage_pct"]==80.0,(aid,sc)
    assert sc["production_weighted_maturity_pct"]==24.0 and sc["evidence_maturity_label"]=="BENCHMARK_HEAVY",(aid,sc)
    assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)
    assert pl["evidence_maturity"]["candidate_evidence_mature"] is False and pl["candidate"]["owner"] is None,(aid,pl)
r=by["technology-radar-agent"];sc=r["scorecard"];pl=r["plan"]
assert sc["production_measurement_coverage_pct"]==20.0 and sc["benchmark_measurement_coverage_pct"]==60.0,sc
assert sc["measurement_coverage_pct"]==80.0 and sc["production_weighted_maturity_pct"]==32.0,sc
assert set(sc["production_measured_dimensions"])=={"authority_discipline","evidence_quality"},sc
assert sc["recommendation"]!="MEASURE_FIRST" and pl["candidate"]["owner"] is None,(sc,pl)
remaining=[a["agent_id"] for a in x["agents"] if a["scorecard"].get("recommendation")=="MEASURE_FIRST"]
assert remaining==[],remaining
print("CHACHA_DEV_V658_REAL_WEIGHTED_EVIDENCE=PASS")
print("CHACHA_DEV_V658_REAL_MEASURE_FIRST_REMAINING=0")
PY

stage bus-readonly-check
BUS_AFTER="$(sha256sum /opt/chacha-dev/runtime/agent-observation/observations.db 2>/dev/null | awk '{print $1}' || true)"
[ "$BUS_BEFORE" = "$BUS_AFTER" ] || { echo "CANONICAL_BUS_MUTATED";exit 44; }
echo "CHACHA_DEV_V658_REAL_CANONICAL_BUS_MUTATION=NO"

stage universal-regeneration
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py" --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json --routing "$CURRENT/dev-hub/config/agent-routing.v1.json" --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json" --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json" --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json" --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json" --output-root /opt/chacha-dev/runtime/agent-evolution/profiles >"$WORK/profiles.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS' "$WORK/profiles.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py" --agent-profiles /opt/chacha-dev/runtime/agent-evolution/profiles/index.json --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json" --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json" --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json" --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json" --output /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json >"$WORK/components.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/components.out"

stage guardian-and-post
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py" --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" --client "$CURRENT/dev-hub/bin/guardian-client.py" --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
grep -Fq '"version":"6.58.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
restore_timers
systemctl is-active --quiet "$FLEET_TIMER";systemctl is-active --quiet "$BUS_TIMER";systemctl is-active --quiet chacha-remote-desktop-commander.service
echo "CHACHA_DEV_V658_GUARDIAN_COVERAGE=PASS"

stage evidence
mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v658-visual-content-project-radar-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
fl=json.load(open("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json"));by={a["agent_id"]:a for a in fl["agents"]}
targets=["graphics-specialist","animation-specialist","ui-layout-specialist","translation-specialist","publication-specialist","technology-radar-agent"]
out={"schema":"chacha.dev/v658-visual-content-project-radar-evidence/v1","revision":sys.argv[2],"observed_at":sys.argv[3],
 "targets":{aid:{"total":by[aid]["scorecard"]["measurement_coverage_pct"],"production":by[aid]["scorecard"]["production_measurement_coverage_pct"],
 "benchmark":by[aid]["scorecard"]["benchmark_measurement_coverage_pct"],"weighted":by[aid]["scorecard"]["production_weighted_maturity_pct"],
 "label":by[aid]["scorecard"]["evidence_maturity_label"]} for aid in targets},
 "measure_first_remaining":0,"ui_layout_specialist_domain_owner":True,"technology_radar_scope":"PROJECT_ONLY",
 "radar_accuracy_from_adapter_promotion":False,"benchmark_production_truth":False,"canonical_observation_bus_mutation":False,
 "production_measurement_precedence":True,"architecture_council_final_authority":True,"automatic_external_spend_eur":0}
open(sys.argv[1],"w").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V658_VISUAL_CONTENT_PROJECT_RADAR=PASS"
echo "CHACHA_DEV_V658_REAL_EIGHTH_WAVE_BENCHMARK_PROMOTED=6"
echo "CHACHA_DEV_V658_REAL_RADAR_STRUCTURAL_PRODUCTION_EVIDENCE=PASS"
echo "CHACHA_DEV_V658_REAL_MEASURE_FIRST_REMAINING=0"
echo "CHACHA_DEV_V658_REAL_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V658_PLATFORM_GLOBAL_RADAR_PROMOTION=FORBIDDEN"
echo "CHACHA_DEV_V658_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V658_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V658_INSTALL=PASS"

trap - EXIT
cleanup
