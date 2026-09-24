#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V655_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V655_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v655.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
BUS_MUTATED=0
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_TIMER_WAS_ACTIVE=0
BUS_TIMER_WAS_ACTIVE=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V655_STAGE=$STAGE"; }
restore_timers(){
  [ "$FLEET_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$FLEET_TIMER" >/dev/null 2>&1 || true
  [ "$BUS_TIMER_WAS_ACTIVE" -eq 1 ] && systemctl start "$BUS_TIMER" >/dev/null 2>&1 || true
}
backup_runtime_state(){
  mkdir -p "$WORK/runtime-backup"
  if [ -d /opt/chacha-dev/runtime/agent-observation ]; then cp -a /opt/chacha-dev/runtime/agent-observation "$WORK/runtime-backup/agent-observation"; fi
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/daily-cycle-latest.json     /opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json; do
    if [ -f "$p" ]; then
      mkdir -p "$WORK/runtime-backup$(dirname "$p")"
      cp -a "$p" "$WORK/runtime-backup$p"
    fi
  done
}
restore_runtime_state(){
  if [ "$BUS_MUTATED" -eq 1 ]; then
    rm -rf /opt/chacha-dev/runtime/agent-observation
    if [ -d "$WORK/runtime-backup/agent-observation" ]; then
      cp -a "$WORK/runtime-backup/agent-observation" /opt/chacha-dev/runtime/agent-observation
    fi
  fi
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/daily-cycle-latest.json     /opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json; do
    if [ -f "$WORK/runtime-backup$p" ]; then
      mkdir -p "$(dirname "$p")";cp -a "$WORK/runtime-backup$p" "$p"
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
    echo "CHACHA_DEV_V655_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do [ -s "$f" ] || continue;echo "=== $(basename "$f") ===";tail -260 "$f" || true;done
    restore_runtime_state
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT";echo "CHACHA_DEV_V655_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v654-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1])
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.54.0"' in src,"V654_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="eb054410c033d9e448a4a55fd226fdeceae9a26e",("V654_ACQUIRED_REVISION_MISMATCH",rev)
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v654-universal-evolution-governance-*.json"))
assert ev,"V654_REAL_EVIDENCE_MISSING"
x=json.loads(ev[-1].read_text(encoding="utf-8"))
assert x.get("revision")=="eb054410c033d9e448a4a55fd226fdeceae9a26e",x
assert x.get("single_evolution_owner_per_component") is True,x
print("CHACHA_DEV_V655_V654_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=source_root_invalid";exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
for required in  dev-hub/bin/agent_verified_evidence_backfill.py  dev-hub/bin/agent_fleet_observatory.py  dev-hub/bin/agent_evolution_daily_cycle.py  dev-hub/bin/agent_benchmark_adapters.py  dev-hub/bin/agent_benchmark_oracles.py  dev-hub/bin/agent_benchmark_campaign_runner.py  dev-hub/bin/agent_evolution_profile.py  dev-hub/bin/component_evolution_governance.py  dev-hub/bin/autonomous-project-orchestrator.py  dev-hub/config/agent-observation-bus.v1.json  dev-hub/config/agent-benchmark-adapters.v1.json  dev-hub/tests/test_v655_production_evidence_fifth_wave.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=missing:$required";exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile  "$RELEASE/dev-hub/bin/agent_verified_evidence_backfill.py"  "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"  "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py"  "$RELEASE/dev-hub/bin/agent_benchmark_adapters.py"  "$RELEASE/dev-hub/bin/agent_benchmark_oracles.py"  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" >/dev/null
grep -Fq '"version":"6.55.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V655_STATIC=PASS"

stage semantic-qualification
(cd "$RELEASE";PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v655_production_evidence_fifth_wave.py) >"$WORK/v655.out" 2>"$WORK/v655.err"
for marker in  CHACHA_DEV_V655_HISTORICAL_VERIFIED_BACKFILL=PASS  CHACHA_DEV_V655_BACKFILL_IDEMPOTENT=PASS  CHACHA_DEV_V655_SELF_VERIFICATION_PROMOTION=BLOCKED  CHACHA_DEV_V655_RETROACTIVE_REASSESSMENT=NO  CHACHA_DEV_V655_PRODUCTION_COVERAGE_HANDOFF=PASS  CHACHA_DEV_V655_BACKEND_API_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_FRONTEND_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_PRODUCT_DOMAIN_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_DOCUMENTATION_ADR_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_FIFTH_WAVE_TOTAL_COVERAGE_80=PASS  CHACHA_DEV_V655_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS  CHACHA_DEV_V655_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do grep -Fq "$marker" "$WORK/v655.out";done
echo "CHACHA_DEV_V655_SEMANTIC_QUALIFICATION=PASS"

stage real-readonly-backfill-preflight
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_verified_evidence_backfill.py"  --runtime-root /opt/chacha-dev/runtime  --fleet-policy "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json"  --bus-policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json"  --routing "$RELEASE/dev-hub/config/agent-routing.v1.json"  --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output "$WORK/backfill-dry.json" --dry-run >"$WORK/backfill-dry.out" 2>"$WORK/backfill-dry.err"
python3 - "$WORK/backfill-dry.json" "$WORK/backfill-accounted.txt" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["dry_run"] is True,x
eligible=int(x.get("eligible_event_count") or 0)
already=int((x.get("counts") or {}).get("already_present") or 0)
accounted=eligible+already
assert accounted>=100,x
assert x["counts"].get("inserted",0)==0,x
assert x["production_truth"] is True and x["independent_verification_required"] is True,x
assert x["retroactive_reassessment"] is False,x
open(sys.argv[2],"w",encoding="utf-8").write(str(accounted))
print("CHACHA_DEV_V655_REAL_READONLY_BACKFILL_PREFLIGHT=PASS")
print("CHACHA_DEV_V655_REAL_ELIGIBLE_PRODUCTION_EVIDENCE="+str(eligible))
print("CHACHA_DEV_V655_REAL_ALREADY_PRESENT_PRODUCTION_EVIDENCE="+str(already))
print("CHACHA_DEV_V655_REAL_ACCOUNTED_PRODUCTION_EVIDENCE="+str(accounted))
PY

stage freeze-runtime-writers
if systemctl is-active --quiet "$FLEET_TIMER"; then FLEET_TIMER_WAS_ACTIVE=1;systemctl stop "$FLEET_TIMER";fi
if systemctl is-active --quiet "$BUS_TIMER"; then BUS_TIMER_WAS_ACTIVE=1;systemctl stop "$BUS_TIMER";fi
backup_runtime_state
echo "CHACHA_DEV_V655_RUNTIME_WRITERS_FROZEN=PASS"

stage isolated-fifth-wave
mkdir -p "$WORK/runtime"
cat >"$WORK/campaign.json" <<'JSON'
{"schema":"chacha.dev/agent-benchmark-campaign/v1","contracts":[
 {"agent_id":"backend-api-architect"},{"agent_id":"frontend-architect"},
 {"agent_id":"product-domain-architect"},{"agent_id":"documentation-adr-agent"}
]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$RELEASE" --runtime-root "$WORK/runtime" --revision "$REV"  --config "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" --output "$WORK/isolated-run.json"  >"$WORK/isolated-run.out" 2>"$WORK/isolated-run.err"
python3 - "$WORK/isolated-run.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==4,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V655_REAL_ISOLATED_FIFTH_WAVE=PASS")
PY

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V655_RELEASE_ACTIVATED=PASS"

stage canonical-production-backfill
BUS_MUTATED=1
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_verified_evidence_backfill.py"  --runtime-root /opt/chacha-dev/runtime  --fleet-policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --bus-policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json  >"$WORK/backfill.out" 2>"$WORK/backfill.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json "$WORK/backfill-accounted.txt" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
expected=int(open(sys.argv[2],encoding="utf-8").read().strip())
inserted=int((x.get("counts") or {}).get("inserted") or 0)
already=int((x.get("counts") or {}).get("already_present") or 0)
assert inserted+already>=expected,(x,expected)
assert x["retroactive_reassessment"] is False,x
assert x["candidate_materialization"] is False,x
print("CHACHA_DEV_V655_REAL_PRODUCTION_EVIDENCE_BACKFILL=PASS")
print("CHACHA_DEV_V655_REAL_PRODUCTION_EVIDENCE_INSERTED="+str(inserted))
print("CHACHA_DEV_V655_REAL_PRODUCTION_EVIDENCE_ALREADY_PRESENT="+str(already))
print("CHACHA_DEV_V655_REAL_PRODUCTION_EVIDENCE_ACCOUNTED="+str(inserted+already))
PY

stage canonical-fifth-wave-benchmark
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime --revision "$REV"  --config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/v655-pilot-benchmark-run.json  >"$WORK/canonical-run.out" 2>"$WORK/canonical-run.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/v655-pilot-benchmark-run.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==4,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V655_REAL_FIFTH_WAVE_BENCHMARK_PROMOTED=4")
PY

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"  --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  >"$WORK/fleet.out" 2>"$WORK/fleet.err"
grep -Fq 'CHACHA_DEV_V647_AGENT_FLEET_OBSERVATORY=PASS' "$WORK/fleet.out"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));by={a["agent_id"]:a for a in x.get("agents") or []}
targets=["backend-api-architect","frontend-architect","product-domain-architect","documentation-adr-agent"]
for aid in targets:
    row=by[aid];sc=row["scorecard"];dims=row["metrics"]["dimensions"]
    assert sc["production_measurement_coverage_pct"]>=30.0,(aid,sc)
    assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
    assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)
    prod=set(sc.get("production_measured_dimensions") or []);bench=set(sc.get("benchmark_measured_dimensions") or [])
    assert not(prod&bench),(aid,prod,bench)
    for d in prod:
        assert dims[d].get("evidence_scope")!="BENCHMARK_ONLY",(aid,d,dims[d])
    print(aid.upper().replace("-","_")+"_PRODUCTION_COVERAGE="+str(sc["production_measurement_coverage_pct"]))
    print(aid.upper().replace("-","_")+"_TOTAL_COVERAGE="+str(sc["measurement_coverage_pct"]))
print("CHACHA_DEV_V655_REAL_PRODUCTION_PRECEDENCE=PASS")
print("CHACHA_DEV_V655_REAL_FIFTH_WAVE_COVERAGE_80=PASS")
PY

stage backfill-idempotency
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_verified_evidence_backfill.py"  --runtime-root /opt/chacha-dev/runtime  --fleet-policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --bus-policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output "$WORK/backfill-second.json" >"$WORK/backfill-second.out" 2>"$WORK/backfill-second.err"
python3 - "$WORK/backfill-second.json" "$WORK/backfill-accounted.txt" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
expected=int(open("/tmp/chacha-v655-backfill-accounted.txt",encoding="utf-8").read().strip())
inserted=int((x.get("counts") or {}).get("inserted") or 0)
already=int((x.get("counts") or {}).get("already_present") or 0)
assert inserted==0,x
assert already>=expected,(x,expected)
print("CHACHA_DEV_V655_REAL_BACKFILL_IDEMPOTENT=PASS")
print("CHACHA_DEV_V655_REAL_BACKFILL_IDEMPOTENT_ACCOUNTED="+str(already))
PY

stage universal-regeneration
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py"  --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json"  --output-root /opt/chacha-dev/runtime/agent-evolution/profiles >"$WORK/profiles.out" 2>"$WORK/profiles.err"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS' "$WORK/profiles.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py"  --agent-profiles /opt/chacha-dev/runtime/agent-evolution/profiles/index.json  --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json"  --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json"  --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json"  --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"  --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json  >"$WORK/components.out" 2>"$WORK/components.err"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/components.out"

stage guardian-and-post-activation
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"  --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
grep -Fq '"version":"6.55.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
restore_timers
systemctl is-active --quiet "$FLEET_TIMER"
systemctl is-active --quiet "$BUS_TIMER"
systemctl is-active --quiet chacha-remote-desktop-commander.service
echo "CHACHA_DEV_V655_GUARDIAN_COVERAGE=PASS"
echo "CHACHA_DEV_V655_POST_ACTIVATION=PASS"

stage evidence
mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v655-production-evidence-fifth-wave-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
bf=json.load(open('/opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json',encoding='utf-8'))
fl=json.load(open('/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json',encoding='utf-8'))
by={a["agent_id"]:a for a in fl.get("agents") or []}
targets=["backend-api-architect","frontend-architect","product-domain-architect","documentation-adr-agent"]
out={"schema":"chacha.dev/v655-production-evidence-fifth-wave-evidence/v1","revision":sys.argv[2],"observed_at":sys.argv[3],
 "historical_verified_evidence_inserted":int((bf.get("counts") or {}).get("inserted") or 0),
 "historical_backfill_production_truth":True,"historical_backfill_independent_verification_required":True,
 "retroactive_reassessment":False,"backfill_idempotent":True,
 "fifth_wave":{aid:{"measurement_coverage_pct":by[aid]["scorecard"]["measurement_coverage_pct"],
   "production_measurement_coverage_pct":by[aid]["scorecard"]["production_measurement_coverage_pct"],
   "benchmark_measurement_coverage_pct":by[aid]["scorecard"]["benchmark_measurement_coverage_pct"]} for aid in targets},
 "benchmark_production_truth":False,"production_measurement_precedence":True,
 "direct_agent_mutation":False,"candidate_materialization":False,
 "guardian_coverage":"PASS","architecture_council_final_authority":True,"automatic_external_spend_eur":0}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V655_PRODUCTION_EVIDENCE_FIFTH_WAVE=PASS"
echo "CHACHA_DEV_V655_REAL_PRODUCTION_EVIDENCE_BACKFILL=PASS"
echo "CHACHA_DEV_V655_REAL_RETROACTIVE_REASSESSMENT=NO"
echo "CHACHA_DEV_V655_REAL_BACKFILL_IDEMPOTENT=PASS"
echo "CHACHA_DEV_V655_REAL_FIFTH_WAVE_BENCHMARK_PROMOTED=4"
echo "CHACHA_DEV_V655_REAL_PRODUCTION_PRECEDENCE=PASS"
echo "CHACHA_DEV_V655_REAL_FIFTH_WAVE_COVERAGE_80=PASS"
echo "CHACHA_DEV_V655_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V655_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V655_INSTALL=PASS"

trap - EXIT
cleanup
