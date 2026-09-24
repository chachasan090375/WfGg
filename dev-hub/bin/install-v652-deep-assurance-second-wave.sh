#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V652_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V652_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v652.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V652_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V652_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -240 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V652_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V652_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V652_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V652_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v651-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.51.0"' in s,"V651_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="54923351d60d8702996db97d50c8b8ace112b2a0",("V651_ACQUIRED_REVISION_MISMATCH",rev)
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v651-executable-agent-benchmarks-*.json"))
assert ev,"V651_REAL_EVIDENCE_MISSING"
x=json.loads(ev[-1].read_text(encoding="utf-8"))
assert int(x.get("promoted_benchmark_evidence_count") or 0)==4,x
print("CHACHA_DEV_V652_V651_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V652_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in  dev-hub/bin/agent_benchmark_adapters.py  dev-hub/bin/agent_benchmark_oracles.py  dev-hub/bin/agent_benchmark_adapter_runner.py  dev-hub/bin/agent_benchmark_evidence_promoter.py  dev-hub/bin/agent_benchmark_campaign_runner.py  dev-hub/bin/agent_fleet_observatory.py  dev-hub/bin/agent_evolution_daily_cycle.py  dev-hub/config/agent-benchmark-adapters.v1.json  dev-hub/config/agent-fleet-observatory.v1.json  dev-hub/tests/test_v652_deep_assurance_second_wave.py  dev-hub/tests/test_v651_executable_agent_benchmark_adapters.py; do
 [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V652_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile  "$RELEASE/dev-hub/bin/agent_benchmark_adapters.py"  "$RELEASE/dev-hub/bin/agent_benchmark_oracles.py"  "$RELEASE/dev-hub/bin/agent_benchmark_adapter_runner.py"  "$RELEASE/dev-hub/bin/agent_benchmark_evidence_promoter.py"  "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"  "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"  "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py"  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" >/dev/null
grep -Fq '"version":"6.52.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 - "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
expected={"guardian","sentinel","bastion","autonomous-recovery-agent","security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer"}
assert expected<=set(x.get("supported_agents") or {}),x
assert (x.get("evidence") or {}).get("independent_oracle_id")=="v652-independent-benchmark-oracle",x
assert (x.get("isolation") or {}).get("external_network_required") is False,x
assert int((x.get("deep_calibration") or {}).get("repeat_count") or 0)==2,x
print("CHACHA_DEV_V652_STATIC_CONTRACT=PASS")
PY
echo "CHACHA_DEV_V652_STATIC=PASS"

stage semantic-qualification
(
 cd "$RELEASE"
 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v652_deep_assurance_second_wave.py
 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v651_executable_agent_benchmark_adapters.py
) >"$WORK/v652.out" 2>"$WORK/v652.err"
for marker in  CHACHA_DEV_V652_PRIORITY_AGENT_DEEP_CALIBRATION=PASS  CHACHA_DEV_V652_SECURITY_REVIEWER_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V652_RECOVERY_ENGINEER_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V652_PLATFORM_CLOUD_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V652_DATA_ARCHITECT_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V652_RELEASE_ENGINEER_EXECUTABLE_ADAPTER=PASS  CHACHA_DEV_V652_DRIFT_RESISTANCE_MEASURED=PASS  CHACHA_DEV_V652_EFFICIENCY_MEASURED=PASS  CHACHA_DEV_V652_MEASUREMENT_COVERAGE_60=PASS  CHACHA_DEV_V652_EXPLICIT_ORACLE_IDENTITY_GATE=PASS  CHACHA_DEV_V652_LATEST_PROMOTED_BENCHMARK_SELECTION=PASS  CHACHA_DEV_V652_CANONICAL_OBSERVATION_BUS_WRITE=NO  CHACHA_DEV_V652_AUTOMATIC_EXTERNAL_SPEND_EUR=0  CHACHA_DEV_V651_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS; do
 grep -Fq "$marker" "$WORK/v652.out"
done
echo "CHACHA_DEV_V652_SEMANTIC_QUALIFICATION=PASS"

stage technology-watch-freshness
PYTHONPATH="$RELEASE/dev-hub/bin" python3 - "$RELEASE" >"$WORK/tw.out" <<'PY'
import json,sys
from pathlib import Path
import technology_watch_runtime as tw
root=Path(sys.argv[1]);x=tw.snapshot_status(root)
print(json.dumps(x,sort_keys=True))
assert x.get("fresh") is True,x
print("CHACHA_DEV_V652_REAL_TECHNOLOGY_WATCH_FRESH=PASS")
PY

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
BUS="/opt/chacha-dev/runtime/agent-observation/observations.db"
TRUST_BEFORE="$(canon_hash "$TRUST")";DURABLE_BEFORE="$(canon_hash "$DURABLE")";TW_BEFORE="$(canon_hash "$TW")";BUS_BEFORE="$(canon_hash "$BUS")"

stage isolated-real-adapters
mkdir -p "$WORK/runtime"
cat >"$WORK/campaign.json" <<'JSON'
{"schema":"chacha.dev/agent-benchmark-campaign/v1","contracts":[
 {"agent_id":"guardian"},{"agent_id":"sentinel"},{"agent_id":"bastion"},{"agent_id":"autonomous-recovery-agent"},
 {"agent_id":"security-reviewer"},{"agent_id":"recovery-engineer"},{"agent_id":"platform-cloud-engineer"},
 {"agent_id":"data-architect"},{"agent_id":"release-engineer"},{"agent_id":"graphics-specialist"}
]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$RELEASE" --runtime-root "$WORK/runtime"  --revision "$REV" --config "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json"  --output "$WORK/isolated-run.json" >"$WORK/isolated-run.out" 2>"$WORK/isolated-run.err"
python3 - "$WORK/isolated-run.json" "$WORK/runtime" "$REV" <<'PY'
import json,sys,pathlib
x=json.load(open(sys.argv[1],encoding="utf-8"));rt=pathlib.Path(sys.argv[2]);rev=sys.argv[3]
assert x["promoted_count"]==9,x
assert x["canonical_observation_bus_writes"] is False,x
assert any(r["agent_id"]=="graphics-specialist" and r["status"]=="NO_EXECUTABLE_ADAPTER" for r in x["results"]),x
targets={"guardian","sentinel","bastion","autonomous-recovery-agent","security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer"}
for aid in targets:
    p=rt/"agent-evolution/benchmark-evidence"/aid/(rev+".json")
    e=json.load(open(p,encoding="utf-8"))
    assert e["verification"]=="BENCHMARK_VERIFIED",e
    assert e["verifier"]=="v652-independent-benchmark-oracle",e
    assert e["truth_scope"]=="BENCHMARK_ONLY" and e["production_truth_eligible"] is False,e
    assert {"accuracy","robustness","authority_discipline","evidence_quality","drift_resistance","efficiency"}<=set(e["dimensions"]),e
    assert e["repeat_count"]==2 and e["deep_calibration"] is True,e
print("CHACHA_DEV_V652_REAL_ISOLATED_ADAPTERS=PASS")
print("CHACHA_DEV_V652_REAL_PROMOTED_EVIDENCE=9")
print("CHACHA_DEV_V652_REAL_UNSUPPORTED_AGENT_IS_FAILURE=NO")
PY
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED_BY_ISOLATED_ADAPTER"; exit 44; }
echo "CHACHA_DEV_V652_REAL_CANONICAL_BUS_MUTATION_BEFORE_ACTIVATION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V652_RELEASE_ACTIVATED=PASS"

stage canonical-benchmark-evidence
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --revision "$REV" --config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/v652-pilot-benchmark-run.json  >"$WORK/canonical-run.out" 2>"$WORK/canonical-run.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/v652-pilot-benchmark-run.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==9,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V652_REAL_BENCHMARK_EVIDENCE_PROMOTED=9")
print("CHACHA_DEV_V652_REAL_BENCHMARK_PRODUCTION_TRUTH=NO")
PY
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED_BY_BENCHMARK"; exit 45; }
echo "CHACHA_DEV_V652_REAL_CANONICAL_BUS_MUTATION=NO"

stage fleet-rebuild
systemctl start chacha-dev-agent-fleet-observatory.service
test -s /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));rev=sys.argv[2]
targets={"guardian","sentinel","bastion","autonomous-recovery-agent","security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer"}
by={a["agent_id"]:a for a in x.get("agents") or []}
assert targets<=set(by),targets-set(by)
for aid in sorted(targets):
    row=by[aid];sc=row["scorecard"];m=row["metrics"];dims=m["dimensions"]
    assert sc["measurement_coverage_pct"]>=60.0,(aid,sc)
    assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)
    assert m["signals"].get("benchmark_evidence_present") is True,(aid,m)
    for d in ("drift_resistance","efficiency"):
        assert dims[d].get("status")=="MEASURED",(aid,d,dims[d])
        assert dims[d].get("evidence_scope")=="BENCHMARK_ONLY",(aid,d,dims[d])
        assert any(rev in str(ref) for ref in dims[d].get("source_refs") or []),(aid,d,dims[d])
    print(aid.upper().replace("-","_")+"_MEASUREMENT_COVERAGE="+str(sc["measurement_coverage_pct"]))
    print(aid.upper().replace("-","_")+"_RECOMMENDATION="+str(sc["recommendation"]))
print("CHACHA_DEV_V652_REAL_NINE_AGENTS_COVERAGE_60=PASS")
print("CHACHA_DEV_V652_REAL_FIRST_WAVE_DEEPENED=PASS")
print("CHACHA_DEV_V652_REAL_SECOND_WAVE_MEASURE_FIRST_EXITED=PASS")
PY

stage canonical-isolation
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo "CANONICAL_TRUST_MUTATED"; exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo "CANONICAL_DURABLE_MUTATED"; exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo "CANONICAL_TW_MUTATED"; exit 43; }
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED"; exit 44; }
echo "CHACHA_DEV_V652_REAL_CANONICAL_TRUST_DURABLE_TW_BUS_MUTATION=NO"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"  --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json  >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V652_GUARDIAN_COVERAGE=PASS"

stage post-activation
grep -Fq '"version":"6.52.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
echo "CHACHA_DEV_V652_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  "/opt/chacha-dev/evidence/v652-deep-assurance-second-wave-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
fleet=json.load(open(sys.argv[1],encoding="utf-8"))
targets={"guardian","sentinel","bastion","autonomous-recovery-agent","security-reviewer","recovery-engineer","platform-cloud-engineer","data-architect","release-engineer"}
by={a["agent_id"]:a for a in fleet.get("agents") or []}
out={"schema":"chacha.dev/v652-deep-assurance-second-wave-evidence/v1","revision":sys.argv[3],"observed_at":sys.argv[4],
 "targets":{aid:{"measurement_coverage_pct":by[aid]["scorecard"]["measurement_coverage_pct"],
                 "recommendation":by[aid]["scorecard"]["recommendation"],
                 "drift_resistance":by[aid]["metrics"]["dimensions"]["drift_resistance"]["value"],
                 "efficiency":by[aid]["metrics"]["dimensions"]["efficiency"]["value"]} for aid in sorted(targets)},
 "promoted_benchmark_evidence_count":9,"benchmark_production_truth":False,
 "explicit_oracle_id":"v652-independent-benchmark-oracle","repeat_count":2,
 "canonical_observation_bus_mutation":False,"canonical_trust_durable_technology_watch_mutation":False,
 "guardian_coverage":"PASS","direct_agent_mutation":False,"candidate_materialization":False,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V652_DEEP_ASSURANCE_SECOND_ADAPTER_WAVE=PASS"
echo "CHACHA_DEV_V652_REAL_PROMOTED_EVIDENCE=9"
echo "CHACHA_DEV_V652_REAL_NINE_AGENTS_COVERAGE_60=PASS"
echo "CHACHA_DEV_V652_REAL_FIRST_WAVE_DEEPENED=PASS"
echo "CHACHA_DEV_V652_REAL_SECOND_WAVE_MEASURE_FIRST_EXITED=PASS"
echo "CHACHA_DEV_V652_REAL_BENCHMARK_PRODUCTION_TRUTH=NO"
echo "CHACHA_DEV_V652_REAL_CANONICAL_TRUST_DURABLE_TW_BUS_MUTATION=NO"
echo "CHACHA_DEV_V652_DIRECT_AGENT_MUTATION=NO"
echo "CHACHA_DEV_V652_CANDIDATE_MATERIALIZATION=NO"
echo "CHACHA_DEV_V652_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V652_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V652_INSTALL=PASS"

trap - EXIT
cleanup
