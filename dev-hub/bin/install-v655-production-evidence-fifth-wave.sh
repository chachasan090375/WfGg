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
STAGE="bootstrap"
COMPONENT_CONFIDENCE_TIMER="chacha-dev-component-confidence.timer"
COMPONENT_CONFIDENCE_SERVICE="chacha-dev-component-confidence.service"
COMPONENT_CONFIDENCE_TIMER_WAS_ACTIVE=0

stage(){ STAGE="$1"; echo "CHACHA_DEV_V655_STAGE=$STAGE"; }
restore_component_confidence_timer(){
  if [ "$COMPONENT_CONFIDENCE_TIMER_WAS_ACTIVE" -eq 1 ]; then
    systemctl start "$COMPONENT_CONFIDENCE_TIMER" >/dev/null 2>&1 || true
  fi
}
cleanup(){ restore_component_confidence_timer; rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V655_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -300 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V655_ROLLBACK=PASS"
      echo "CHACHA_DEV_V655_APPEND_ONLY_REAL_EVIDENCE_IF_ANY=PRESERVED"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v654-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1])
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.54.0"' in src,"V654_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="eb054410c033d9e448a4a55fd226fdeceae9a26e",("V654_ACQUIRED_REVISION_MISMATCH",rev)
ev=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v654-universal-evolution-governance-*.json"))
assert any(json.loads(p.read_text(encoding="utf-8")).get("revision")==rev for p in ev),"V654_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V655_V654_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/agent_verified_evidence_backfill.py   dev-hub/bin/agent_observation_bus.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_daily_cycle.py   dev-hub/bin/agent_benchmark_adapters.py   dev-hub/bin/agent_benchmark_oracles.py   dev-hub/bin/agent_benchmark_campaign_runner.py   dev-hub/bin/agent_benchmark_evidence_promoter.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/agent-observation-bus.v1.json   dev-hub/config/agent-benchmark-adapters.v1.json   dev-hub/tests/test_v655_production_evidence_fifth_wave.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/agent_verified_evidence_backfill.py"   "$RELEASE/dev-hub/bin/agent_observation_bus.py"   "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py"   "$RELEASE/dev-hub/bin/agent_benchmark_adapters.py"   "$RELEASE/dev-hub/bin/agent_benchmark_oracles.py"   "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"   "$RELEASE/dev-hub/bin/agent_benchmark_evidence_promoter.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" >/dev/null
grep -Fq '"version":"6.55.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V655_STATIC=PASS"

stage semantic-qualification
(
 cd "$RELEASE"
 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v655_production_evidence_fifth_wave.py
) >"$WORK/v655.out" 2>"$WORK/v655.err"
for marker in  CHACHA_DEV_V655_HISTORICAL_VERIFIED_BACKFILL=PASS  CHACHA_DEV_V655_BACKFILL_IDEMPOTENT=PASS  CHACHA_DEV_V655_SELF_VERIFICATION_PROMOTION=BLOCKED  CHACHA_DEV_V655_RETROACTIVE_REASSESSMENT=NO  CHACHA_DEV_V655_PRODUCTION_COVERAGE_HANDOFF=PASS  CHACHA_DEV_V655_BACKEND_API_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_FRONTEND_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_PRODUCT_DOMAIN_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_DOCUMENTATION_ADR_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V655_FIFTH_WAVE_TOTAL_COVERAGE_80=PASS  CHACHA_DEV_V655_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS  CHACHA_DEV_V655_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v655.out"
done
echo "CHACHA_DEV_V655_SEMANTIC_QUALIFICATION=PASS"

stage real-backfill-dry-run
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_verified_evidence_backfill.py"  --runtime-root /opt/chacha-dev/runtime  --fleet-policy "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json"  --bus-policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json"  --routing "$RELEASE/dev-hub/config/agent-routing.v1.json"  --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output "$WORK/backfill-dry.json" --dry-run >"$WORK/backfill-dry.out" 2>"$WORK/backfill-dry.err"
python3 - "$WORK/backfill-dry.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["dry_run"] is True,x
assert x["eligible_event_count"]>=100,x
assert int((x.get("counts") or {}).get("inserted") or 0)==0,x
assert x["retroactive_reassessment"] is False,x
print("CHACHA_DEV_V655_REAL_BACKFILL_DRY_RUN=PASS")
print("DRY_RUN_ELIGIBLE="+str(x["eligible_event_count"]))
PY

stage isolated-fifth-wave
mkdir -p "$WORK/runtime"
cat >"$WORK/campaign.json" <<'JSON'
{"schema":"chacha.dev/agent-benchmark-campaign/v1","contracts":[
 {"agent_id":"backend-api-architect"},{"agent_id":"frontend-architect"},
 {"agent_id":"product-domain-architect"},{"agent_id":"documentation-adr-agent"},
 {"agent_id":"translation-specialist"}
]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$RELEASE" --runtime-root "$WORK/runtime"  --revision "$REV" --config "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json"  --output "$WORK/isolated-run.json" >"$WORK/isolated-run.out" 2>"$WORK/isolated-run.err"
python3 - "$WORK/isolated-run.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==4,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
assert any(r["agent_id"]=="translation-specialist" and r["status"]=="NO_EXECUTABLE_ADAPTER" for r in x["results"]),x
print("CHACHA_DEV_V655_REAL_ISOLATED_FIFTH_WAVE=PASS")
PY

stage guardian-preactivation
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$RELEASE" --manifest "$RELEASE/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json" --client "$RELEASE/dev-hub/bin/guardian-client.py"  --output "$WORK/guardian-candidate.json" >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V655_GUARDIAN_PREACTIVATION=PASS"

stage freeze-component-confidence-refresh
if systemctl is-active --quiet "$COMPONENT_CONFIDENCE_TIMER"; then
  COMPONENT_CONFIDENCE_TIMER_WAS_ACTIVE=1
  systemctl stop "$COMPONENT_CONFIDENCE_TIMER"
fi
for _ in $(seq 1 30); do
  if ! systemctl is-active --quiet "$COMPONENT_CONFIDENCE_SERVICE"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$COMPONENT_CONFIDENCE_SERVICE"; then
  echo "CHACHA_DEV_V655_INSTALL=BLOCKED reason=component_confidence_refresh_did_not_quiesce";exit 46
fi
echo "CHACHA_DEV_V655_COMPONENT_CONFIDENCE_REFRESH_FROZEN=PASS"

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
BUS="/opt/chacha-dev/runtime/agent-observation/observations.db"
TRUST_BEFORE="$(canon_hash "$TRUST")";DURABLE_BEFORE="$(canon_hash "$DURABLE")";TW_BEFORE="$(canon_hash "$TW")";BUS_BEFORE="$(canon_hash "$BUS")"
QROOT="/opt/chacha-dev/runtime/agent-evolution/reassessment-queue"
QUEUE_BEFORE="$(find "$QROOT" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V655_RELEASE_ACTIVATED=PASS"

stage canonical-fifth-wave
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --revision "$REV" --config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/v655-pilot-benchmark-run.json  >"$WORK/canonical-run.out" 2>"$WORK/canonical-run.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/v655-pilot-benchmark-run.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==4,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V655_REAL_FIFTH_WAVE_EVIDENCE_PROMOTED=4")
PY

stage fleet-before-backfill
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"  --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output "$WORK/fleet-before.json" >"$WORK/fleet-before.out" 2>"$WORK/fleet-before.err"
python3 - "$WORK/fleet-before.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));by={a["agent_id"]:a for a in x["agents"]}
targets={"backend-api-architect","frontend-architect","product-domain-architect","documentation-adr-agent"}
for aid in targets:
 sc=by[aid]["scorecard"]
 assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
 assert sc["production_measurement_coverage_pct"]>=20.0,(aid,sc)
 assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)
print("CHACHA_DEV_V655_REAL_FIFTH_WAVE_PRE_BACKFILL=PASS")
PY

stage canonical-production-backfill
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_verified_evidence_backfill.py"  --runtime-root /opt/chacha-dev/runtime  --fleet-policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --bus-policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json  >"$WORK/backfill-real.out" 2>"$WORK/backfill-real.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert int((x.get("counts") or {}).get("inserted") or 0)>=100,x
assert x["retroactive_reassessment"] is False,x
print("CHACHA_DEV_V655_REAL_PRODUCTION_BACKFILL=PASS")
print("REAL_BACKFILL_INSERTED="+str((x.get("counts") or {}).get("inserted")))
PY
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_verified_evidence_backfill.py"  --runtime-root /opt/chacha-dev/runtime  --fleet-policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --bus-policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output "$WORK/backfill-second.json" >"$WORK/backfill-second.out" 2>"$WORK/backfill-second.err"
python3 - "$WORK/backfill-second.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert int((x.get("counts") or {}).get("inserted") or 0)==0,x
assert int((x.get("counts") or {}).get("already_present") or 0)>=100,x
print("CHACHA_DEV_V655_REAL_BACKFILL_IDEMPOTENT=PASS")
PY
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_observation_bus.py"  --runtime-root /opt/chacha-dev/runtime --policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json" verify  >"$WORK/bus-chain.out"
grep -Fq 'CHACHA_DEV_V648_OBSERVATION_CHAIN=PASS' "$WORK/bus-chain.out"

stage fleet-after-backfill
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"  --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  >"$WORK/fleet-after.out" 2>"$WORK/fleet-after.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));by={a["agent_id"]:a for a in x["agents"]}
targets={"backend-api-architect","frontend-architect","product-domain-architect","documentation-adr-agent"}
for aid in sorted(targets):
 row=by[aid];sc=row["scorecard"];dims=row["metrics"]["dimensions"]
 assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
 assert sc["production_measurement_coverage_pct"]>=30.0,(aid,sc)
 assert dims["handoff_quality"]["status"]=="MEASURED",(aid,dims["handoff_quality"])
 assert dims["handoff_quality"].get("evidence_scope")!="BENCHMARK_ONLY",(aid,dims["handoff_quality"])
 prod=set(sc.get("production_measured_dimensions") or []);bench=set(sc.get("benchmark_measured_dimensions") or [])
 assert not(prod&bench),(aid,prod,bench)
 print(aid.upper().replace("-","_")+"_TOTAL="+str(sc["measurement_coverage_pct"]))
 print(aid.upper().replace("-","_")+"_PRODUCTION="+str(sc["production_measurement_coverage_pct"]))
print("CHACHA_DEV_V655_REAL_FIFTH_WAVE_PRODUCTION_HANDOFF=PASS")
PY

stage no-retroactive-reassessment
QUEUE_AFTER="$(find "$QROOT" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
[ "$QUEUE_BEFORE" = "$QUEUE_AFTER" ] || { echo "RETROACTIVE_REASSESSMENT_QUEUE_MUTATED before=$QUEUE_BEFORE after=$QUEUE_AFTER";exit 47; }
echo "CHACHA_DEV_V655_REAL_RETROACTIVE_REASSESSMENT=NO"

stage canonical-isolation
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo "CANONICAL_TRUST_MUTATED";exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo "CANONICAL_DURABLE_MUTATED";exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo "CANONICAL_TW_MUTATED";exit 43; }
BUS_AFTER="$(canon_hash "$BUS")"
[ "$BUS_BEFORE" != "$BUS_AFTER" ] || { echo "CANONICAL_BUS_EXPECTED_BACKFILL_MISSING";exit 44; }
echo "CHACHA_DEV_V655_REAL_CANONICAL_TRUST_DURABLE_TW_MUTATION=NO"
echo "CHACHA_DEV_V655_REAL_CANONICAL_BUS_MUTATION=INTENTIONAL_VERIFIED_EVIDENCE_BACKFILL"

stage restore-background-controls
restore_component_confidence_timer
if [ "$COMPONENT_CONFIDENCE_TIMER_WAS_ACTIVE" -eq 1 ]; then
 systemctl is-active --quiet "$COMPONENT_CONFIDENCE_TIMER"
 echo "CHACHA_DEV_V655_COMPONENT_CONFIDENCE_TIMER_RESTORED=PASS"
fi

stage post-activation
grep -Fq '"version":"6.55.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
systemctl is-active --quiet chacha-remote-desktop-commander.service
echo "CHACHA_DEV_V655_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  /opt/chacha-dev/runtime/agent-evolution/verified-evidence-backfill-latest.json  "/opt/chacha-dev/evidence/v655-production-evidence-fifth-wave-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
fleet=json.load(open(sys.argv[1],encoding="utf-8"));backfill=json.load(open(sys.argv[2],encoding="utf-8"))
by={a["agent_id"]:a for a in fleet["agents"]}
targets=["backend-api-architect","frontend-architect","product-domain-architect","documentation-adr-agent"]
out={"schema":"chacha.dev/v655-production-evidence-fifth-wave-evidence/v1","revision":sys.argv[4],"observed_at":sys.argv[5],
 "verified_backfill_inserted":int((backfill.get("counts") or {}).get("inserted") or 0),
 "verified_backfill_event_type":backfill.get("event_type"),"retroactive_reassessment":False,
 "fifth_wave":{aid:{"measurement_coverage_pct":by[aid]["scorecard"]["measurement_coverage_pct"],
   "production_measurement_coverage_pct":by[aid]["scorecard"].get("production_measurement_coverage_pct"),
   "benchmark_measurement_coverage_pct":by[aid]["scorecard"].get("benchmark_measurement_coverage_pct"),
   "recommendation":by[aid]["scorecard"]["recommendation"]} for aid in targets},
 "benchmark_production_truth":False,"production_measurement_precedence":True,
 "canonical_observation_bus_mutation":"INTENTIONAL_VERIFIED_EVIDENCE_BACKFILL",
 "canonical_trust_durable_technology_watch_mutation":False,
 "direct_agent_mutation":False,"candidate_materialization":False,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
open(sys.argv[3],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V655_PRODUCTION_EVIDENCE_FIFTH_WAVE=PASS"
echo "CHACHA_DEV_V655_REAL_BACKFILL_DRY_RUN=PASS"
echo "CHACHA_DEV_V655_REAL_PRODUCTION_BACKFILL=PASS"
echo "CHACHA_DEV_V655_REAL_BACKFILL_IDEMPOTENT=PASS"
echo "CHACHA_DEV_V655_REAL_RETROACTIVE_REASSESSMENT=NO"
echo "CHACHA_DEV_V655_REAL_FIFTH_WAVE_EVIDENCE_PROMOTED=4"
echo "CHACHA_DEV_V655_REAL_FIFTH_WAVE_PRODUCTION_HANDOFF=PASS"
echo "CHACHA_DEV_V655_REAL_PRODUCTION_MEASUREMENT_PRECEDENCE=PRESERVED"
echo "CHACHA_DEV_V655_REAL_CANONICAL_TRUST_DURABLE_TW_MUTATION=NO"
echo "CHACHA_DEV_V655_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V655_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V655_INSTALL=PASS"

trap - EXIT
cleanup
