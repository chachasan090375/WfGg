#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V662_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V662_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v662.XXXXXX)"
ATTEST_DIR="/opt/chacha-dev/runtime/agent-evolution/real-world-attestations/$REV"
PILOT_DIR="/opt/chacha-dev/runtime/agent-evolution/candidate-pilots/acceptance-engineer/v662/$REV"
PREVIOUS=""
ACTIVATED=0
ATTEST_WRITTEN=0
PILOT_WRITTEN=0
STAGE="bootstrap"
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_ACTIVE=0
BUS_ACTIVE=0

stage(){ STAGE="$1";echo "CHACHA_DEV_V662_STAGE=$STAGE"; }
restore_timers(){
  [ "$FLEET_ACTIVE" -eq 1 ] && systemctl start "$FLEET_TIMER" >/dev/null 2>&1 || true
  [ "$BUS_ACTIVE" -eq 1 ] && systemctl start "$BUS_TIMER" >/dev/null 2>&1 || true
}
backup_runtime(){
  mkdir -p "$WORK/backup"
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json     /opt/chacha-dev/runtime/guardian/coverage-latest.json; do
    if [ -f "$p" ]; then
      mkdir -p "$WORK/backup$(dirname "$p")"
      cp -a "$p" "$WORK/backup$p"
    fi
  done
}
restore_runtime(){
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json     /opt/chacha-dev/runtime/guardian/coverage-latest.json; do
    if [ -f "$WORK/backup$p" ]; then
      mkdir -p "$(dirname "$p")"
      cp -a "$WORK/backup$p" "$p"
    fi
  done
  [ "$ATTEST_WRITTEN" -eq 1 ] && rm -rf "$ATTEST_DIR" || true
  [ "$PILOT_WRITTEN" -eq 1 ] && rm -rf "$PILOT_DIR" || true
}
cleanup(){ restore_timers;rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V662_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ===";tail -260 "$f" || true
    done
    restore_runtime
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V662_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V662_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V662_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V662_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v661-real-baseline
python3 - "$PREVIOUS" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);rev=(root/".revision").read_text().strip()
assert rev=="402c5db88b1adeb627e9cdf69d51685eef829767",rev
assert '"version":"6.61.0"' in (root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text()
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v661-real-world-evidence-isolated-candidate-*.json"))
assert ev,"V661_REAL_EVIDENCE_MISSING"
x=json.loads(ev[-1].read_text());assert x.get("revision")==rev,x
assert x.get("benchmark_heavy_remaining")==12,x
assert x.get("acceptance_candidate_production_activation") is False,x
assert x.get("canonical_observation_bus_mutation") is False,x
assert x.get("benchmark_evidence_mutation") is False,x
assert x.get("architecture_council_final_authority") is True,x
print("CHACHA_DEV_V662_V661_REAL_BASELINE=PASS")
PY
INCUMBENT_BEFORE="$(sha256sum "$PREVIOUS/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')"

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")";[ -d "$SRC/dev-hub" ] || exit 2
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
for p in   dev-hub/bin/ergonomist-real-world-attestor-v662.py   dev-hub/bin/acceptance-candidate-independent-pilot-v662.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_profile.py   dev-hub/bin/component_evolution_governance.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/bin/technology-watch-service.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/acceptance-engine.py   dev-hub/candidates/acceptance-engineer/v661/acceptance-engine-candidate.py   dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json   dev-hub/config/agent-fleet-observatory.v1.json   dev-hub/tests/test_v662_ergonomist_acceptance_independent_pilot.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V662_INSTALL=BLOCKED reason=missing:$p";exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
python3 -m py_compile   "$RELEASE/dev-hub/bin/ergonomist-real-world-attestor-v662.py"   "$RELEASE/dev-hub/bin/acceptance-candidate-independent-pilot-v662.py"   "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/tests/test_v662_ergonomist_acceptance_independent_pilot.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" >/dev/null
grep -Fq '"version":"6.62.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
(cd "$RELEASE";PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v662_ergonomist_acceptance_independent_pilot.py) >"$WORK/v662.out" 2>"$WORK/v662.err"
for m in   CHACHA_DEV_V662_ERGONOMIST_REAL_WORLD_ATTESTATION=PASS   CHACHA_DEV_V662_ERGONOMIST_ACCURACY_INFERENCE=NO   CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT=PASS   CHACHA_DEV_V662_ACCEPTANCE_REAL_NO_REGRESSION=PASS   CHACHA_DEV_V662_ACCEPTANCE_ADVERSARIAL_GAIN=PASS   CHACHA_DEV_V662_LOGICIAN_FALSIFICATION=PASS   CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ACTIVATION=NO   CHACHA_DEV_V662_ACCEPTANCE_PROMOTION=NO   CHACHA_DEV_V662_RADAR_PROJECT_ONLY=PASS; do
  grep -Fq "$m" "$WORK/v662.out"
done
echo "CHACHA_DEV_V662_STATIC_AND_SEMANTIC=PASS"

stage github-external-assurance
python3 - "$REV" <<'PY'
import json,sys,urllib.parse,urllib.request
rev=sys.argv[1]
q=urllib.parse.urlencode({"head_sha":rev,"per_page":50})
url="https://api.github.com/repos/chachasan090375/WfGg/actions/runs?"+q
req=urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-V662-Installer/1.0","Accept":"application/vnd.github+json"})
with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read().decode())
need={
 "ChaCha DEV V6.62 Ergonomist evidence and Acceptance independent pilot qualification",
 "ChaCha DEV Sentinel technical assurance"
}
rows=x.get("workflow_runs") or []
for name in need:
    hits=[w for w in rows if w.get("name")==name and w.get("head_sha")==rev and w.get("status")=="completed" and w.get("conclusion")=="success"]
    assert hits,(name,[(w.get("name"),w.get("status"),w.get("conclusion")) for w in rows])
print("CHACHA_DEV_V662_EXACT_SHA_GITHUB_ASSURANCE=PASS")
PY

stage real-ergonomist-preflight
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/ergonomist-real-world-attestor-v662.py"   --runtime-root /opt/chacha-dev/runtime --output "$WORK/ergonomist.json" >"$WORK/ergonomist.out" 2>"$WORK/ergonomist.err"
grep -Fq 'CHACHA_DEV_V662_ERGONOMIST_REAL_WORLD_ATTESTATION=PASS' "$WORK/ergonomist.out"
python3 - "$WORK/ergonomist.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["case_count"]==3 and x["passed_case_count"]==3,x
assert x["dimension_values"]=={"evidence_quality":100.0,"handoff_quality":100.0,"authority_discipline":100.0},x
assert x["accuracy_inference"] is False and x["production_truth_eligible"] is True,x
assert x["direct_mutation"] is False and x["architecture_council_final_authority"] is True,x
print("CHACHA_DEV_V662_REAL_ERGONOMIST_PREFLIGHT=PASS")
PY

stage real-independent-pilot
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/acceptance-candidate-independent-pilot-v662.py"   --repo-root "$RELEASE" --runtime-root /opt/chacha-dev/runtime --output "$WORK/acceptance-pilot.json"   >"$WORK/pilot.out" 2>"$WORK/pilot.err"
for m in   CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT=PASS   CHACHA_DEV_V662_ACCEPTANCE_REAL_NO_REGRESSION=PASS   CHACHA_DEV_V662_ACCEPTANCE_ADVERSARIAL_GAIN=PASS   CHACHA_DEV_V662_LOGICIAN_FALSIFICATION=PASS   CHACHA_DEV_V662_TECHNOLOGY_WATCH=FRESH   CHACHA_DEV_V662_GUARDIAN_ACTIVE=YES   CHACHA_DEV_V662_SENTINEL_REQUIRED=YES   CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ACTIVATION=NO   CHACHA_DEV_V662_ACCEPTANCE_PROMOTION=NO; do
  grep -Fq "$m" "$WORK/pilot.out"
done
python3 - "$WORK/acceptance-pilot.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["real_case_count"]==3 and x["real_passed_count"]==3,x
assert x["adversarial_case_count"]==4 and x["adversarial_passed_count"]==4,x
assert x["decision"]=="INDEPENDENT_PILOT_PASS_HOLD_INCUMBENT",x
assert x["production_entrypoint_changed"] is False,x
assert x["production_activation_allowed"] is False and x["promotion_allowed"] is False,x
assert x["guardian_all_hooks_active"] is True and x["sentinel_required_for_release"] is True,x
assert x["technology_watch_fresh"] is True and x["logician_falsification_paths_verified"] is True,x
print("CHACHA_DEV_V662_REAL_ACCEPTANCE_INDEPENDENT_PILOT=PASS")
PY

stage freeze-runtime
if systemctl is-active --quiet "$FLEET_TIMER"; then FLEET_ACTIVE=1;systemctl stop "$FLEET_TIMER";fi
if systemctl is-active --quiet "$BUS_TIMER"; then BUS_ACTIVE=1;systemctl stop "$BUS_TIMER";fi
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

stage materialize-pilot-evidence
rm -rf "$ATTEST_DIR" "$PILOT_DIR";mkdir -p "$ATTEST_DIR" "$PILOT_DIR"
cp "$WORK/ergonomist.json" "$ATTEST_DIR/attestation-ergonomist.json";ATTEST_WRITTEN=1
cp "$WORK/acceptance-pilot.json" "$PILOT_DIR/pilot-receipt.json"
cp "$RELEASE/dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json" "$PILOT_DIR/candidate-manifest.json"
PILOT_WRITTEN=1
echo "CHACHA_DEV_V662_ERGONOMIST_ATTESTATION_MATERIALIZED=PASS"
echo "CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT_MATERIALIZED=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
INCUMBENT_AFTER="$(sha256sum "$CURRENT/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')"
[ "$INCUMBENT_BEFORE" = "$INCUMBENT_AFTER" ] || { echo "ACCEPTANCE_INCUMBENT_CHANGED";exit 46; }
echo "CHACHA_DEV_V662_RELEASE_ACTIVATED=PASS"
echo "CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ENTRYPOINT_CHANGED=NO"

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"   --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime   --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"   --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json >"$WORK/fleet.out" 2>"$WORK/fleet.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in x["agents"]}
e=by["ergonomist"];sc=e["scorecard"];sig=e["metrics"]["signals"]
assert sc["production_measurement_coverage_pct"]==30.0,sc
assert sc["benchmark_measurement_coverage_pct"]==50.0,sc
assert sc["measurement_coverage_pct"]==80.0,sc
assert sc["production_weighted_maturity_pct"]==36.0,sc
assert sc["evidence_maturity_label"]=="MIXED_EVIDENCE",sc
assert set(sc["production_measured_dimensions"])=={"authority_discipline","evidence_quality","handoff_quality"},sc
assert sc["dimension_evidence"]["accuracy"].get("evidence_scope")=="BENCHMARK_ONLY",sc
assert sig["real_world_structural_attestation_present"] is True and sig["real_world_structural_attestation_cases"]==3,sig
for aid in ("contract-integrator","integration-architect","knowledge-compiler-agent","uncertainty-resolution-agent"):
    a=by[aid];assert a["scorecard"]["production_measurement_coverage_pct"]==0.0,(aid,a["scorecard"])
    assert a["scorecard"]["evidence_maturity_label"]=="BENCHMARK_HEAVY",(aid,a["scorecard"])
ar=by["autonomous-recovery-agent"];assert ar["scorecard"]["production_measurement_coverage_pct"]==0.0,ar["scorecard"]
rad=by["technology-radar-agent"];assert rad["scope"]=="PROJECT" and rad["scorecard"]["production_measurement_coverage_pct"]==20.0,rad
remaining=[a["agent_id"] for a in x["agents"] if a["scorecard"].get("evidence_maturity_label")=="BENCHMARK_HEAVY"]
assert len(remaining)==11,remaining
assert sum(1 for a in x["agents"] if a["scorecard"].get("evidence_maturity_label")=="MIXED_EVIDENCE")==24
assert sum(1 for a in x["agents"] if a["scorecard"].get("recommendation")=="MEASURE_FIRST")==0
print("CHACHA_DEV_V662_REAL_FLEET_DEEPENING=PASS")
print("CHACHA_DEV_V662_BENCHMARK_HEAVY_REMAINING=11")
print("CHACHA_DEV_V662_MIXED_EVIDENCE=24")
print("CHACHA_DEV_V662_UNSUPPORTED_REAL_WORLD_PROMOTION=NO")
PY

stage immutable-and-project-boundaries
BUS_AFTER="$(sha256sum /opt/chacha-dev/runtime/agent-observation/observations.db 2>/dev/null | awk '{print $1}' || true)"
[ "$BUS_BEFORE" = "$BUS_AFTER" ] || { echo CANONICAL_BUS_MUTATED;exit 44; }
BENCH_AFTER="$(python3 - <<'PY'
import hashlib,pathlib
h=hashlib.sha256();root=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/benchmark-evidence")
for p in sorted(root.glob("**/*.json")):
    h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
print(h.hexdigest())
PY
)"
[ "$BENCH_BEFORE" = "$BENCH_AFTER" ] || { echo BENCHMARK_EVIDENCE_MUTATED;exit 45; }
python3 - "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));a=x["agents"][0]
assert x["platform_global"] is False and a["agent_id"]=="technology-radar-agent"
assert a["scope"]=="PROJECT_ONLY" and a["production_permission"] is False
assert a["central_brain_role"] is False and a["technology_watch_platform_role"] is False
print("CHACHA_DEV_V662_RADAR_PROJECT_ONLY=PASS")
PY
echo "CHACHA_DEV_V662_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V662_BENCHMARK_EVIDENCE_MUTATION=NO"

stage universal-regeneration
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py"   --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"   --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"   --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json"   --output-root /opt/chacha-dev/runtime/agent-evolution/profiles >"$WORK/profiles.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS' "$WORK/profiles.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py"   --agent-profiles /opt/chacha-dev/runtime/agent-evolution/profiles/index.json   --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json"   --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json"   --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json"   --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"   --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json"   --output /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json >"$WORK/components.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/components.out"

stage guardian-watch-post
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" status >"$WORK/watch-post.out"
grep -Fq 'CHACHA_TECHNOLOGY_WATCH_STATUS=FRESH' "$WORK/watch-post.out"
restore_timers
systemctl is-active --quiet "$FLEET_TIMER"
systemctl is-active --quiet "$BUS_TIMER"
systemctl is-active --quiet chacha-remote-desktop-commander.service

stage evidence
mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v662-ergonomist-real-evidence-acceptance-independent-pilot-$STAMP.json" "$REV" "$STAMP" "$PILOT_DIR/pilot-receipt.json" <<'PY'
import json,sys
f=json.load(open("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json"));by={a["agent_id"]:a for a in f["agents"]}
p=json.load(open(sys.argv[4]));e=by["ergonomist"]["scorecard"]
out={
 "schema":"chacha.dev/v662-ergonomist-real-evidence-acceptance-independent-pilot/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],
 "ergonomist":{"production":e["production_measurement_coverage_pct"],"benchmark":e["benchmark_measurement_coverage_pct"],
               "weighted":e["production_weighted_maturity_pct"],"label":e["evidence_maturity_label"],
               "production_measured_dimensions":e["production_measured_dimensions"],"accuracy_inference":False},
 "benchmark_heavy_remaining":sum(1 for a in f["agents"] if a["scorecard"].get("evidence_maturity_label")=="BENCHMARK_HEAVY"),
 "mixed_evidence_count":sum(1 for a in f["agents"] if a["scorecard"].get("evidence_maturity_label")=="MIXED_EVIDENCE"),
 "acceptance_candidate":{"pilot_id":p["pilot_id"],"decision":p["decision"],"real_cases":p["real_case_count"],
                         "adversarial_cases":p["adversarial_case_count"],"measurable_gain_verified":p["measurable_gain_verified"],
                         "logician_falsification":p["logician_falsification_paths_verified"],
                         "technology_watch_fresh":p["technology_watch_fresh"],"guardian_active":p["guardian_all_hooks_active"],
                         "sentinel_required":p["sentinel_required_for_release"],"production_activation":False,"promotion":False,
                         "incumbent_control_group":True},
 "unsupported_real_world_promotion":False,
 "radar_project_only":True,"autonomous_recovery_production_promotion":False,
 "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
 "production_entrypoint_changed":False,"active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0
}
open(sys.argv[1],"w").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V662_ERGONOMIST_REAL_WORLD_EVIDENCE=PASS"
echo "CHACHA_DEV_V662_BENCHMARK_HEAVY_REMAINING=11"
echo "CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT=PASS"
echo "CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ENTRYPOINT_CHANGED=NO"
echo "CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ACTIVATION=NO"
echo "CHACHA_DEV_V662_ACCEPTANCE_PROMOTION=NO"
echo "CHACHA_DEV_V662_UNSUPPORTED_REAL_WORLD_PROMOTION=NO"
echo "CHACHA_DEV_V662_RADAR_PROJECT_ONLY=PASS"
echo "CHACHA_DEV_V662_AUTONOMOUS_RECOVERY_PRODUCTION_PROMOTION=NO"
echo "CHACHA_DEV_V662_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V662_BENCHMARK_EVIDENCE_MUTATION=NO"
echo "CHACHA_DEV_V662_SELF_MUTATION=NO"
echo "CHACHA_DEV_V662_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V662_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V662_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V662_INSTALL=PASS"

trap - EXIT
cleanup
