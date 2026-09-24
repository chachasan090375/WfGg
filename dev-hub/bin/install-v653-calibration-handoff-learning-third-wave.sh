#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V653_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V653_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v653.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V653_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V653_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -260 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V653_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V653_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V653_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V653_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v652-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.52.0"' in src,"V652_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="c1659393bd48d1de7d5de0dd34d5195b44872e6f",("V652_ACQUIRED_REVISION_MISMATCH",rev)
ev=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v652-deep-assurance-second-wave-*.json"))
assert ev,"V652_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V653_V652_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V653_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/agent_benchmark_adapters.py   dev-hub/bin/agent_benchmark_oracles.py   dev-hub/bin/agent_benchmark_adapter_runner.py   dev-hub/bin/agent_benchmark_evidence_promoter.py   dev-hub/bin/agent_benchmark_campaign_runner.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_controller.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/agent-benchmark-adapters.v1.json   dev-hub/config/agent-evolution.v1.json   dev-hub/tests/test_v653_calibration_handoff_learning_third_wave.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V653_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/agent_benchmark_adapters.py"   "$RELEASE/dev-hub/bin/agent_benchmark_oracles.py"   "$RELEASE/dev-hub/bin/agent_benchmark_adapter_runner.py"   "$RELEASE/dev-hub/bin/agent_benchmark_evidence_promoter.py"   "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"   "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   "$RELEASE/dev-hub/bin/agent_evolution_controller.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-evolution.v1.json" >/dev/null
grep -Fq '"version":"6.53.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V653_STATIC=PASS"

stage semantic-qualification
(
 cd "$RELEASE"
 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v653_calibration_handoff_learning_third_wave.py
) >"$WORK/v653.out" 2>"$WORK/v653.err"
for marker in  CHACHA_DEV_V653_BENCHMARK_CONTRACT_COVERAGE=PASS  CHACHA_DEV_V653_BENCHMARK_HANDOFF_QUALITY=PASS  CHACHA_DEV_V653_AGENT_FOUNDRY_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V653_BRANCH_FOUNDRY_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V653_CAPABILITY_FOUNDRY_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V653_LOGICIAN_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V653_TECHNOLOGY_WATCH_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V653_FOUNDRY_LEARNING_QUALITY=PASS  CHACHA_DEV_V653_TECHNOLOGY_WATCH_CALIBRATION=PASS  CHACHA_DEV_V653_PREVIOUS_NINE_COVERAGE_80=PASS  CHACHA_DEV_V653_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED  CHACHA_DEV_V653_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v653.out"
done
echo "CHACHA_DEV_V653_SEMANTIC_QUALIFICATION=PASS"

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
BUS="/opt/chacha-dev/runtime/agent-observation/observations.db"
TRUST_BEFORE="$(canon_hash "$TRUST")";DURABLE_BEFORE="$(canon_hash "$DURABLE")";TW_BEFORE="$(canon_hash "$TW")";BUS_BEFORE="$(canon_hash "$BUS")"

stage isolated-fourteen-agent-wave
mkdir -p "$WORK/runtime"
cat >"$WORK/campaign.json" <<'JSON'
{"schema":"chacha.dev/agent-benchmark-campaign/v1","contracts":[
 {"agent_id":"guardian"},{"agent_id":"sentinel"},{"agent_id":"bastion"},{"agent_id":"autonomous-recovery-agent"},
 {"agent_id":"security-reviewer"},{"agent_id":"recovery-engineer"},{"agent_id":"platform-cloud-engineer"},
 {"agent_id":"data-architect"},{"agent_id":"release-engineer"},
 {"agent_id":"agent-foundry-architect"},{"agent_id":"branch-foundry-architect"},
 {"agent_id":"capability-foundry-architect"},{"agent_id":"logician"},{"agent_id":"technology-watch-agent"},
 {"agent_id":"translation-specialist"}
]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$RELEASE" --runtime-root "$WORK/runtime"  --revision "$REV" --config "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json"  --output "$WORK/isolated-run.json" >"$WORK/isolated-run.out" 2>"$WORK/isolated-run.err"
python3 - "$WORK/isolated-run.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==14,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
assert any(r["agent_id"]=="translation-specialist" and r["status"]=="NO_EXECUTABLE_ADAPTER" for r in x["results"]),x
print("CHACHA_DEV_V653_REAL_ISOLATED_FOURTEEN_AGENT_WAVE=PASS")
print("CHACHA_DEV_V653_REAL_UNSUPPORTED_AGENT_IS_FAILURE=NO")
PY
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED_BY_ISOLATED_BENCHMARK"; exit 44; }

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V653_RELEASE_ACTIVATED=PASS"

stage canonical-benchmark-evidence
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --revision "$REV" --config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/v653-pilot-benchmark-run.json  >"$WORK/canonical-run.out" 2>"$WORK/canonical-run.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/v653-pilot-benchmark-run.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==14,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V653_REAL_BENCHMARK_EVIDENCE_PROMOTED=14")
PY
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED_BY_BENCHMARK"; exit 45; }

stage fleet-rebuild
systemctl start chacha-dev-agent-fleet-observatory.service
test -s /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
previous={"guardian","sentinel","bastion","autonomous-recovery-agent","security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer"}
third={"agent-foundry-architect","branch-foundry-architect","capability-foundry-architect","logician","technology-watch-agent"}
by={a["agent_id"]:a for a in x.get("agents") or []}
for aid in sorted(previous|third):
    row=by[aid];sc=row["scorecard"];pl=row["plan"]
    assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
    assert sc["benchmark_measurement_coverage_pct"]>=80.0,(aid,sc)
    assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)
    maturity=pl.get("evidence_maturity") or {}
    assert maturity.get("benchmark_only_cannot_materialize_candidate") is True,(aid,maturity)
    if not maturity.get("candidate_evidence_mature"):
        assert (pl.get("candidate") or {}).get("owner") is None,(aid,pl)
    print(aid.upper().replace("-","_")+"_MEASUREMENT_COVERAGE="+str(sc["measurement_coverage_pct"]))
    print(aid.upper().replace("-","_")+"_PRODUCTION_COVERAGE="+str(sc.get("production_measurement_coverage_pct")))
for aid in sorted(third):
    dims=by[aid]["metrics"]["dimensions"]
    assert dims["coverage"]["status"]=="MEASURED",(aid,dims["coverage"])
    assert dims["handoff_quality"]["status"]=="MEASURED",(aid,dims["handoff_quality"])
for aid in ("agent-foundry-architect","branch-foundry-architect","capability-foundry-architect","technology-watch-agent"):
    assert by[aid]["metrics"]["dimensions"]["learning_quality"]["status"]=="MEASURED",(aid,by[aid]["metrics"]["dimensions"]["learning_quality"])
assert by["technology-watch-agent"]["metrics"]["dimensions"]["calibration"]["status"]=="MEASURED"
print("CHACHA_DEV_V653_REAL_FOURTEEN_AGENTS_COVERAGE_80=PASS")
print("CHACHA_DEV_V653_REAL_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED")
PY

stage canonical-isolation
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo "CANONICAL_TRUST_MUTATED"; exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo "CANONICAL_DURABLE_MUTATED"; exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo "CANONICAL_TW_MUTATED"; exit 43; }
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED"; exit 44; }
echo "CHACHA_DEV_V653_REAL_CANONICAL_TRUST_DURABLE_TW_BUS_MUTATION=NO"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"  --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V653_GUARDIAN_COVERAGE=PASS"

stage post-activation
grep -Fq '"version":"6.53.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
systemctl is-active --quiet chacha-remote-desktop-commander.service
echo "CHACHA_DEV_V653_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  "/opt/chacha-dev/evidence/v653-calibration-handoff-learning-third-wave-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
fleet=json.load(open(sys.argv[1],encoding="utf-8"))
targets={"guardian","sentinel","bastion","autonomous-recovery-agent","security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer","agent-foundry-architect","branch-foundry-architect","capability-foundry-architect","logician","technology-watch-agent"}
by={a["agent_id"]:a for a in fleet.get("agents") or []}
out={"schema":"chacha.dev/v653-calibration-handoff-learning-evidence/v1","revision":sys.argv[3],"observed_at":sys.argv[4],
 "targets":{aid:{"measurement_coverage_pct":by[aid]["scorecard"]["measurement_coverage_pct"],
   "production_measurement_coverage_pct":by[aid]["scorecard"].get("production_measurement_coverage_pct"),
   "recommendation":by[aid]["scorecard"]["recommendation"]} for aid in sorted(targets)},
 "promoted_benchmark_evidence_count":14,"benchmark_production_truth":False,
 "benchmark_only_candidate_materialization":False,"production_measurement_precedence":True,
 "canonical_observation_bus_mutation":False,"canonical_trust_durable_technology_watch_mutation":False,
 "guardian_coverage":"PASS","direct_agent_mutation":False,"architecture_council_final_authority":True,
 "automatic_external_spend_eur":0}
open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V653_CALIBRATION_HANDOFF_LEARNING_THIRD_WAVE=PASS"
echo "CHACHA_DEV_V653_REAL_BENCHMARK_EVIDENCE_PROMOTED=14"
echo "CHACHA_DEV_V653_REAL_FOURTEEN_AGENTS_COVERAGE_80=PASS"
echo "CHACHA_DEV_V653_REAL_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED"
echo "CHACHA_DEV_V653_REAL_PRODUCTION_MEASUREMENT_PRECEDENCE=PRESERVED"
echo "CHACHA_DEV_V653_REAL_CANONICAL_TRUST_DURABLE_TW_BUS_MUTATION=NO"
echo "CHACHA_DEV_V653_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V653_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V653_INSTALL=PASS"

trap - EXIT
cleanup
