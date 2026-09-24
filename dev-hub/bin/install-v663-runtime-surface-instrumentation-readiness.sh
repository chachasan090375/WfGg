#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V663_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V663_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v663.XXXXXX)"
READINESS_DIR="/opt/chacha-dev/runtime/agent-evolution/candidate-readiness/acceptance-engineer/v663/$REV"
PREVIOUS=""
ACTIVATED=0
READINESS_WRITTEN=0
STAGE="bootstrap"
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_ACTIVE=0
BUS_ACTIVE=0

stage(){ STAGE="$1";echo "CHACHA_DEV_V663_STAGE=$STAGE"; }
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
  [ "$READINESS_WRITTEN" -eq 1 ] && rm -rf "$READINESS_DIR" || true
}
cleanup(){ restore_timers;rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V663_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -260 "$f" || true
    done
    restore_runtime
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V663_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V663_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V663_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V663_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v662-real-baseline
python3 - "$PREVIOUS" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1])
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="9e333786d55898d2b6d0a0997fc66fc1c6413dad",rev
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.62.0"' in src
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v662-remaining-real-world-acceptance-independent-pilot-*.json"))
assert ev,"V662_REAL_EVIDENCE_MISSING"
x=json.loads(ev[-1].read_text(encoding="utf-8"))
assert x.get("revision")==rev,x
assert x.get("canonical_observation_bus_mutation") is False,x
assert x.get("benchmark_evidence_mutation") is False,x
assert x.get("acceptance_candidate_production_activation") is False,x
assert x.get("acceptance_candidate_promotion") is False,x
print("CHACHA_DEV_V663_V662_REAL_BASELINE=PASS")
PY
ACCEPT_BEFORE="$(sha256sum "$PREVIOUS/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')"

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || exit 2
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
for p in   dev-hub/bin/install-v663-runtime-surface-instrumentation-readiness.sh   dev-hub/bin/contract-registry.py   dev-hub/bin/integration-architecture-review.py   dev-hub/bin/acceptance-candidate-promotion-readiness-v663.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_profile.py   dev-hub/bin/component_evolution_governance.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/bin/technology-watch-service.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/acceptance-engine.py   dev-hub/config/agent-fleet-observatory.v1.json   dev-hub/config/assurance-agent-instrumentation.v1.json   dev-hub/projects/wfgg-radar/project-agent-registry.v1.json   dev-hub/tests/test_v663_runtime_surface_instrumentation_readiness.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V663_INSTALL=BLOCKED reason=missing:$p";exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
bash -n "$RELEASE/dev-hub/bin/install-v663-runtime-surface-instrumentation-readiness.sh"
python3 -m py_compile   "$RELEASE/dev-hub/bin/contract-registry.py"   "$RELEASE/dev-hub/bin/integration-architecture-review.py"   "$RELEASE/dev-hub/bin/acceptance-candidate-promotion-readiness-v663.py"   "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/tests/test_v663_runtime_surface_instrumentation_readiness.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/assurance-agent-instrumentation.v1.json" >/dev/null
grep -Fq '"version":"6.63.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
[ "$ACCEPT_BEFORE" = "$(sha256sum "$RELEASE/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')" ] || { echo "PRODUCTION_ACCEPTANCE_ENTRYPOINT_CHANGED";exit 46; }
(cd "$RELEASE";PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v663_runtime_surface_instrumentation_readiness.py) >"$WORK/v663.out" 2>"$WORK/v663.err"
for m in   CHACHA_DEV_V663_RADAR_PROJECT_ATTRIBUTION_GUARD=PASS   CHACHA_DEV_V663_RADAR_SRE_RELEASE_CREDIT=NO   CHACHA_DEV_V663_CONTRACT_INTEGRATOR_RUNTIME_STAGE=PASS   CHACHA_DEV_V663_INTEGRATION_ARCHITECT_RUNTIME_STAGE=PASS   CHACHA_DEV_V663_MISSING_SURFACE_INSTRUMENTATION=PASS   CHACHA_DEV_V663_HISTORICAL_SURFACE_BACKFILL=NO   CHACHA_DEV_V663_ACCEPTANCE_READINESS=PASS   CHACHA_DEV_V663_ACCEPTANCE_PRODUCTION_ACTIVATION=NO   CHACHA_DEV_V663_ACCEPTANCE_PROMOTION=NO; do
  grep -Fq "$m" "$WORK/v663.out"
done
echo "CHACHA_DEV_V663_STATIC_AND_SEMANTIC=PASS"

stage github-external-assurance
python3 - "$REV" <<'PY'
import json,sys,urllib.parse,urllib.request
rev=sys.argv[1]
q=urllib.parse.urlencode({"head_sha":rev,"per_page":50})
url="https://api.github.com/repos/chachasan090375/WfGg/actions/runs?"+q
req=urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-V663-Installer/1.0","Accept":"application/vnd.github+json"})
with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read().decode())
need={
 "ChaCha DEV V6.63 runtime surface instrumentation and Acceptance readiness qualification",
 "ChaCha DEV Sentinel technical assurance"
}
rows=x.get("workflow_runs") or []
for name in need:
    hits=[w for w in rows if w.get("name")==name and w.get("head_sha")==rev and w.get("status")=="completed" and w.get("conclusion")=="success"]
    assert hits,(name,[(w.get("name"),w.get("status"),w.get("conclusion")) for w in rows])
print("CHACHA_DEV_V663_EXACT_SHA_GITHUB_ASSURANCE=PASS")
PY

stage real-radar-attribution-preflight
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   --repo-root "$RELEASE" --runtime-root /opt/chacha-dev/runtime   --policy "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json"   --evolution-policy "$RELEASE/dev-hub/config/agent-evolution.v1.json"   --routing "$RELEASE/dev-hub/config/agent-routing.v1.json"   --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output "$WORK/fleet-preflight.json" >"$WORK/fleet-preflight.out" 2>"$WORK/fleet-preflight.err"
python3 - "$WORK/fleet-preflight.json" <<'PY'
import json,sys
f=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in f["agents"]}
r=by["technology-radar-agent"];sc=r["scorecard"];sig=r["metrics"]["signals"]
assert sc["production_measurement_coverage_pct"]==20.0,sc
assert sc["benchmark_measurement_coverage_pct"]==60.0,sc
assert sc["production_weighted_maturity_pct"]==32.0,sc
assert sc["evidence_maturity_label"]=="BENCHMARK_HEAVY",sc
assert set(sc["production_measured_dimensions"])=={"authority_discipline","evidence_quality"},sc
assert sig["project_local_runtime_coverage_present"] is False,sig
assert sig["project_local_runtime_coverage_capabilities"]==[],sig
e=by["ergonomist"]["scorecard"]
assert e["production_measurement_coverage_pct"]==30.0 and e["benchmark_measurement_coverage_pct"]==50.0,e
for aid in ("contract-integrator","integration-architect","knowledge-compiler-agent","uncertainty-resolution-agent"):
    a=by[aid]
    assert a["scorecard"]["production_measurement_coverage_pct"]==0.0,(aid,a["scorecard"])
print("CHACHA_DEV_V663_REAL_RADAR_ATTRIBUTION_CORRECTION=PASS")
print("CHACHA_DEV_V663_NO_HISTORICAL_SURFACE_BACKFILL=PASS")
PY

stage real-stage-preflight
python3 - "$RELEASE" "$WORK" <<'PY'
import pathlib,subprocess,sys,json
release=pathlib.Path(sys.argv[1]);work=pathlib.Path(sys.argv[2])
root=pathlib.Path("/opt/chacha-dev/runtime/golden-path-runs")
candidates=[]
for run in sorted(root.iterdir() if root.is_dir() else []):
    p=run/"planning"
    required=(p/"final-plan.json",p/"component-role-contracts.json",p/"architecture-decision-council.json")
    if all(x.is_file() for x in required):candidates.append(p)
assert candidates,"NO_REAL_GOLDEN_PATH_FOR_V663_STAGE_PREFLIGHT"
p=candidates[-1]
rec=work/"contract-reconciliation.json";irev=work/"integration-review.json"
subprocess.run([sys.executable,str(release/"dev-hub/bin/contract-registry.py"),
 "--plan",str(p/"final-plan.json"),"--component-contracts",str(p/"component-role-contracts.json"),"--output",str(rec)],check=True)
r=json.load(open(rec));assert r["compatible"] is True and r["assembly_allowed"] is True,r
subprocess.run([sys.executable,str(release/"dev-hub/bin/integration-architecture-review.py"),
 "--plan",str(p/"final-plan.json"),"--contract-reconciliation",str(rec),
 "--component-contracts",str(p/"component-role-contracts.json"),
 "--architecture-council",str(p/"architecture-decision-council.json"),"--output",str(irev)],check=True)
x=json.load(open(irev));assert x["integration_ready"] is True,x
print("CHACHA_DEV_V663_REAL_CONTRACT_INTEGRATION_PREFLIGHT=PASS")
PY

stage acceptance-readiness-preflight
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/acceptance-candidate-promotion-readiness-v663.py"   --repo-root "$RELEASE" --runtime-root /opt/chacha-dev/runtime --revision "$REV"   --output "$WORK/acceptance-readiness.json" >"$WORK/readiness.out" 2>"$WORK/readiness.err"
grep -Fq 'CHACHA_DEV_V663_ACCEPTANCE_READINESS=PASS' "$WORK/readiness.out"
grep -Fq 'CHACHA_DEV_V663_ACCEPTANCE_ARCHITECTURE_COUNCIL_APPROVAL_PRESENT=NO' "$WORK/readiness.out"
grep -Fq 'CHACHA_DEV_V663_ACCEPTANCE_PRODUCTION_ACTIVATION=NO' "$WORK/readiness.out"
grep -Fq 'CHACHA_DEV_V663_ACCEPTANCE_PROMOTION=NO' "$WORK/readiness.out"
python3 - "$WORK/acceptance-readiness.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["evidence_complete_for_review"] is True,x
assert x["decision"]=="READY_FOR_ARCHITECTURE_COUNCIL_REVIEW_HOLD_INCUMBENT",x
assert x["architecture_council_approval_present"] is False,x
assert x["human_explicit_promotion_approval_present"] is False,x
assert x["production_activation_allowed"] is False and x["promotion_allowed"] is False,x
print("CHACHA_DEV_V663_REAL_ACCEPTANCE_READINESS=PASS")
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
TARGET_EVENTS_BEFORE="$(python3 - <<'PY'
import sqlite3
p="/opt/chacha-dev/runtime/agent-observation/observations.db"
con=sqlite3.connect(p)
ids=("contract-integrator","integration-architect","knowledge-compiler-agent","uncertainty-resolution-agent")
q="select count(*) from observations where subject_role in (?,?,?,?)"
print(con.execute(q,ids).fetchone()[0])
PY
)"

stage materialize-readiness
rm -rf "$READINESS_DIR"
mkdir -p "$READINESS_DIR"
cp "$WORK/acceptance-readiness.json" "$READINESS_DIR/readiness.json"
READINESS_WRITTEN=1
echo "CHACHA_DEV_V663_ACCEPTANCE_READINESS_MATERIALIZED=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
[ "$ACCEPT_BEFORE" = "$(sha256sum "$CURRENT/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')" ] || { echo "ACCEPTANCE_PRODUCTION_ENTRYPOINT_CHANGED";exit 47; }
echo "CHACHA_DEV_V663_RELEASE_ACTIVATED=PASS"
echo "CHACHA_DEV_V663_ACCEPTANCE_PRODUCTION_ENTRYPOINT_CHANGED=NO"

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"   --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime   --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"   --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json >"$WORK/fleet.out" 2>"$WORK/fleet.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in x["agents"]}
r=by["technology-radar-agent"];sc=r["scorecard"];sig=r["metrics"]["signals"]
assert sc["production_measurement_coverage_pct"]==20.0,sc
assert sc["benchmark_measurement_coverage_pct"]==60.0,sc
assert sc["production_weighted_maturity_pct"]==32.0,sc
assert sc["evidence_maturity_label"]=="BENCHMARK_HEAVY",sc
assert sig["project_local_runtime_coverage_present"] is False,sig
assert sig["project_local_runtime_coverage_capabilities"]==[],sig
e=by["ergonomist"]["scorecard"]
assert e["production_measurement_coverage_pct"]==30.0 and e["evidence_maturity_label"]=="MIXED_EVIDENCE",e
for aid in ("contract-integrator","integration-architect","knowledge-compiler-agent","uncertainty-resolution-agent"):
    a=by[aid]
    assert a["scorecard"]["production_measurement_coverage_pct"]==0.0,(aid,a["scorecard"])
    assert a["scorecard"]["evidence_maturity_label"]=="BENCHMARK_HEAVY",(aid,a["scorecard"])
labels={}
for a in x["agents"]:labels[a["scorecard"]["evidence_maturity_label"]]=labels.get(a["scorecard"]["evidence_maturity_label"],0)+1
assert labels=={"BENCHMARK_HEAVY":11,"MIXED_EVIDENCE":24},labels
assert sum(1 for a in x["agents"] if a["scorecard"].get("recommendation")=="MEASURE_FIRST")==0
print("CHACHA_DEV_V663_FLEET_CORRECTED=PASS")
print("CHACHA_DEV_V663_MIXED_EVIDENCE=24")
print("CHACHA_DEV_V663_BENCHMARK_HEAVY=11")
PY

stage no-synthetic-backfill
TARGET_EVENTS_AFTER="$(python3 - <<'PY'
import sqlite3
p="/opt/chacha-dev/runtime/agent-observation/observations.db"
con=sqlite3.connect(p)
ids=("contract-integrator","integration-architect","knowledge-compiler-agent","uncertainty-resolution-agent")
q="select count(*) from observations where subject_role in (?,?,?,?)"
print(con.execute(q,ids).fetchone()[0])
PY
)"
[ "$TARGET_EVENTS_BEFORE" = "$TARGET_EVENTS_AFTER" ] || { echo "V663_SYNTHETIC_BACKFILL_DETECTED";exit 48; }
echo "CHACHA_DEV_V663_HISTORICAL_SURFACE_BACKFILL=NO"

stage immutability
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
echo "CHACHA_DEV_V663_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V663_BENCHMARK_EVIDENCE_MUTATION=NO"

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
python3 - "/opt/chacha-dev/evidence/v663-runtime-surface-instrumentation-readiness-$STAMP.json" "$REV" "$STAMP" "$READINESS_DIR/readiness.json" <<'PY'
import json,sys
f=json.load(open("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json"));by={a["agent_id"]:a for a in f["agents"]}
r=by["technology-radar-agent"]["scorecard"];rd=json.load(open(sys.argv[4]))
out={
 "schema":"chacha.dev/v663-runtime-surface-instrumentation-readiness-evidence/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],
 "radar":{
   "scope":"PROJECT_ONLY","central_brain_role":False,
   "production":r["production_measurement_coverage_pct"],"benchmark":r["benchmark_measurement_coverage_pct"],
   "weighted":r["production_weighted_maturity_pct"],"label":r["evidence_maturity_label"],
   "sre_release_execution_credit":False,"explicit_subject_agent_binding_required":True
 },
 "future_runtime_surfaces":{
   "contract-integrator":"WIRED_REAL_STAGE",
   "integration-architect":"WIRED_REAL_STAGE",
   "knowledge-compiler-agent":"INSTRUMENTED_WHEN_REAL_STAGE_EXECUTES",
   "uncertainty-resolution-agent":"INSTRUMENTED_WHEN_REAL_STAGE_EXECUTES",
   "historical_backfill":False
 },
 "acceptance_readiness":{
   "decision":rd["decision"],"evidence_complete_for_review":rd["evidence_complete_for_review"],
   "architecture_council_approval_present":False,"human_explicit_promotion_approval_present":False,
   "production_activation":False,"promotion":False,"incumbent_control_group":True
 },
 "mixed_evidence_count":sum(1 for a in f["agents"] if a["scorecard"].get("evidence_maturity_label")=="MIXED_EVIDENCE"),
 "benchmark_heavy_count":sum(1 for a in f["agents"] if a["scorecard"].get("evidence_maturity_label")=="BENCHMARK_HEAVY"),
 "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
 "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0
}
open(sys.argv[1],"w").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V663_RADAR_PROJECT_ATTRIBUTION_GUARD=PASS"
echo "CHACHA_DEV_V663_RADAR_SRE_RELEASE_CREDIT=NO"
echo "CHACHA_DEV_V663_CONTRACT_INTEGRATOR_RUNTIME_STAGE=PASS"
echo "CHACHA_DEV_V663_INTEGRATION_ARCHITECT_RUNTIME_STAGE=PASS"
echo "CHACHA_DEV_V663_HISTORICAL_SURFACE_BACKFILL=NO"
echo "CHACHA_DEV_V663_ACCEPTANCE_READINESS=PASS"
echo "CHACHA_DEV_V663_ACCEPTANCE_ARCHITECTURE_COUNCIL_APPROVAL=NO"
echo "CHACHA_DEV_V663_ACCEPTANCE_PRODUCTION_ACTIVATION=NO"
echo "CHACHA_DEV_V663_ACCEPTANCE_PROMOTION=NO"
echo "CHACHA_DEV_V663_CANONICAL_BUS_MUTATION=NO"
echo "CHACHA_DEV_V663_BENCHMARK_EVIDENCE_MUTATION=NO"
echo "CHACHA_DEV_V663_SELF_MUTATION=NO"
echo "CHACHA_DEV_V663_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V663_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V663_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V663_INSTALL=PASS"

trap - EXIT
cleanup
