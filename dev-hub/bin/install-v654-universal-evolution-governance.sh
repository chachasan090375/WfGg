#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V654_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V654_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v654.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"
COMPONENT_CONFIDENCE_TIMER="chacha-dev-component-confidence.timer"
COMPONENT_CONFIDENCE_SERVICE="chacha-dev-component-confidence.service"
COMPONENT_CONFIDENCE_TIMER_WAS_ACTIVE=0

stage(){ STAGE="$1"; echo "CHACHA_DEV_V654_STAGE=$STAGE"; }
restore_component_confidence_timer(){
  if [ "$COMPONENT_CONFIDENCE_TIMER_WAS_ACTIVE" -eq 1 ]; then
    systemctl start "$COMPONENT_CONFIDENCE_TIMER" >/dev/null 2>&1 || true
  fi
}
cleanup(){ restore_component_confidence_timer; rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V654_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -260 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V654_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V654_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V654_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V654_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v653-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.53.0"' in src,"V653_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="7c1bec95e168bfc9c022f6d1b6ecf9c6ee2ccc63",("V653_ACQUIRED_REVISION_MISMATCH",rev)
ev=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v653-calibration-handoff-learning-third-wave-*.json"))
assert any("7c1bec95e168bfc9c022f6d1b6ecf9c6ee2ccc63" in p.read_text(encoding="utf-8") for p in ev),"V653_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V654_V653_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V654_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in  dev-hub/bin/agent_evolution_profile.py  dev-hub/bin/component_evolution_governance.py  dev-hub/bin/agent-foundry-planner.py  dev-hub/bin/project-embedded-assurance.py  dev-hub/bin/agent_evolution_daily_cycle.py  dev-hub/bin/agent_observation_bus_health.py  dev-hub/bin/agent_benchmark_adapters.py  dev-hub/bin/agent_benchmark_oracles.py  dev-hub/bin/agent_benchmark_campaign_runner.py  dev-hub/bin/agent_fleet_observatory.py  dev-hub/bin/autonomous-project-orchestrator.py  dev-hub/config/agent-evolution-profile.v1.json  dev-hub/config/universal-evolution-governance.v1.json  dev-hub/config/lightweight-agent-runtime-profile.v1.json  dev-hub/config/project-embedded-assurance.v1.json  dev-hub/config/agent-benchmark-adapters.v1.json  dev-hub/tests/test_v654_universal_evolution_governance.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V654_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile  "$RELEASE/dev-hub/bin/agent_evolution_profile.py"  "$RELEASE/dev-hub/bin/component_evolution_governance.py"  "$RELEASE/dev-hub/bin/agent-foundry-planner.py"  "$RELEASE/dev-hub/bin/project-embedded-assurance.py"  "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py"  "$RELEASE/dev-hub/bin/agent_observation_bus_health.py"  "$RELEASE/dev-hub/bin/agent_benchmark_adapters.py"  "$RELEASE/dev-hub/bin/agent_benchmark_oracles.py"  "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-evolution-profile.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/universal-evolution-governance.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/lightweight-agent-runtime-profile.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/project-embedded-assurance.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json" >/dev/null
grep -Fq '"version":"6.54.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V654_STATIC=PASS"

stage semantic-qualification
(
 cd "$RELEASE"
 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v654_universal_evolution_governance.py
) >"$WORK/v654.out" 2>"$WORK/v654.err"
for marker in  CHACHA_DEV_V654_UNIVERSAL_PROFILE_35=PASS  CHACHA_DEV_V654_PROFILE_IS_PERFORMANCE_SCORE=NO  CHACHA_DEV_V654_PROJECT_RADAR_SCOPE=PROJECT_LOCAL  CHACHA_DEV_V654_CURATOR_INTENDANT_PROFILE_ONLY=PASS  CHACHA_DEV_V654_ACCEPTANCE_ENGINEER_ADAPTER=PASS  CHACHA_DEV_V654_CONTRACT_INTEGRATOR_ADAPTER=PASS  CHACHA_DEV_V654_INTEGRATION_ARCHITECT_ADAPTER=PASS  CHACHA_DEV_V654_ERGONOMIST_ADAPTER=PASS  CHACHA_DEV_V654_FOURTH_WAVE_CANDIDATE_MATERIALIZATION=BLOCKED  CHACHA_DEV_V654_BUS_PROFILE_POLICY_REASSESSMENT=PASS  CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS  CHACHA_DEV_V654_SINGLE_EVOLUTION_OWNER=PASS  CHACHA_DEV_V654_CONNECTOR_AGENT_SCORECARD=NO  CHACHA_DEV_V654_PASSIVE_ARTIFACT_INHERITS_OWNER=PASS  CHACHA_DEV_V654_FUTURE_AGENT_INHERITANCE=PASS  CHACHA_DEV_V654_LIGHTWEIGHT_EMBEDDED_PROFILE=PASS  CHACHA_DEV_V654_LOCAL_TECH_WATCH_LOGICIAN_FOUNDRY_DUPLICATION=NO  CHACHA_DEV_V654_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v654.out"
done
echo "CHACHA_DEV_V654_SEMANTIC_QUALIFICATION=PASS"

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
  echo "CHACHA_DEV_V654_INSTALL=BLOCKED reason=component_confidence_refresh_did_not_quiesce";exit 46
fi
echo "CHACHA_DEV_V654_COMPONENT_CONFIDENCE_REFRESH_FROZEN=PASS"

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
BUS="/opt/chacha-dev/runtime/agent-observation/observations.db"
TRUST_BEFORE="$(canon_hash "$TRUST")";DURABLE_BEFORE="$(canon_hash "$DURABLE")";TW_BEFORE="$(canon_hash "$TW")";BUS_BEFORE="$(canon_hash "$BUS")"

stage isolated-fourth-wave
mkdir -p "$WORK/runtime"
cat >"$WORK/campaign.json" <<'JSON'
{"schema":"chacha.dev/agent-benchmark-campaign/v1","contracts":[
 {"agent_id":"acceptance-engineer"},{"agent_id":"contract-integrator"},
 {"agent_id":"integration-architect"},{"agent_id":"ergonomist"},
 {"agent_id":"curator"},{"agent_id":"intendant"}
]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$RELEASE" --runtime-root "$WORK/runtime"  --revision "$REV" --config "$RELEASE/dev-hub/config/agent-benchmark-adapters.v1.json"  --output "$WORK/isolated-run.json" >"$WORK/isolated-run.out" 2>"$WORK/isolated-run.err"
python3 - "$WORK/isolated-run.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==4,x
unsupported={r["agent_id"] for r in x["results"] if r["status"]=="NO_EXECUTABLE_ADAPTER"}
assert {"curator","intendant"}<=unsupported,unsupported
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V654_REAL_ISOLATED_FOURTH_WAVE=PASS")
print("CHACHA_DEV_V654_REAL_CURATOR_INTENDANT_PROFILE_ONLY=PASS")
PY
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED_BY_ISOLATED_BENCHMARK";exit 44; }

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V654_RELEASE_ACTIVATED=PASS"

stage canonical-fourth-wave-evidence
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_benchmark_campaign_runner.py"  --campaign "$WORK/campaign.json" --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --revision "$REV" --config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/v654-pilot-benchmark-run.json  >"$WORK/canonical-run.out" 2>"$WORK/canonical-run.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/v654-pilot-benchmark-run.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["promoted_count"]==4,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert x["canonical_observation_bus_writes"] is False,x
print("CHACHA_DEV_V654_REAL_BENCHMARK_EVIDENCE_PROMOTED=4")
PY

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"  --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  >"$WORK/fleet.out" 2>"$WORK/fleet.err"
grep -Fq 'CHACHA_DEV_V647_AGENT_FLEET_OBSERVATORY=PASS' "$WORK/fleet.out"

stage universal-profiles
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py"  --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json  --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"  --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"  --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"  --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"  --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"  --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json"  --output-root /opt/chacha-dev/runtime/agent-evolution/profiles  >"$WORK/profiles.out" 2>"$WORK/profiles.err"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS' "$WORK/profiles.out"
python3 - <<'PY'
import json
from pathlib import Path
idx=json.load(open('/opt/chacha-dev/runtime/agent-evolution/profiles/index.json',encoding='utf-8'))
assert idx["profile_count"]==35,idx
assert idx["profile_is_performance_score"] is False,idx
by={p["identity"]["agent_id"]:p for p in idx["profiles"]}
for aid in ["acceptance-engineer","contract-integrator","integration-architect","ergonomist"]:
    p=by[aid];assert p["measurement"]["total_coverage_pct"]>=80,(aid,p)
    assert p["evolution"]["candidate_materialization_allowed_now"] is False,(aid,p)
assert by["curator"]["measurement"]["strategy"]=="PROFILE_ONLY"
assert by["intendant"]["measurement"]["strategy"]=="PROFILE_ONLY"
radar=by["technology-radar-agent"]
assert radar["evolution"]["scope"]=="PROJECT_LOCAL" and radar["evolution"]["platform_global_promotion_forbidden"] is True,radar
tw=by["technology-watch-agent"]
assert tw["measurement"]["next_action"]=="ACCUMULATE_PRODUCTION_EVIDENCE",tw
print("CHACHA_DEV_V654_REAL_UNIVERSAL_PROFILE_35=PASS")
print("CHACHA_DEV_V654_REAL_PROJECT_RADAR_SCOPE=PROJECT_LOCAL")
print("CHACHA_DEV_V654_REAL_TECHNOLOGY_WATCH_NEXT=ACCUMULATE_PRODUCTION_EVIDENCE")
PY

stage universal-component-governance
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py" \
 --agent-profiles /opt/chacha-dev/runtime/agent-evolution/profiles/index.json \
 --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json" \
 --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json" \
 --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json" \
 --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
 --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json" \
 --output /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json \
 >"$WORK/component-governance.out" 2>"$WORK/component-governance.err"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/component-governance.out"
python3 - <<'PY'
import json
p='/opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json'
x=json.load(open(p,encoding='utf-8'))
assert x["component_count"]>70,x["component_count"]
assert x["single_evolution_owner_per_component"] is True,x
assert x["no_parallel_governance_engines"] is True,x
assert x["lightweight_agents_do_not_duplicate_central_intelligence"] is True,x
by={c["component_id"]:c for c in x["components"]}
assert by["core:central-orchestrator"]["evolution_owner"]=="branch-foundry",by["core:central-orchestrator"]
assert by["adapter:playwright-mcp-adapter"]["evolution_owner"]=="capability-foundry",by["adapter:playwright-mcp-adapter"]
assert by["adapter:playwright-mcp-adapter"]["agent_scorecard"] is False,by["adapter:playwright-mcp-adapter"]
assert by["integration:playwright-mcp"]["sources"]==["mcp-provider-catalog","provider-adapters"],by["integration:playwright-mcp"]
assert x["passive_artifact_governance"]["inherit_owner"] is True,x
print("CHACHA_DEV_V654_REAL_UNIVERSAL_COMPONENT_GOVERNANCE=PASS")
print("CHACHA_DEV_V654_REAL_SINGLE_EVOLUTION_OWNER=PASS")
print("CHACHA_DEV_V654_REAL_CONNECTOR_AGENT_SCORECARD=NO")
PY

stage future-agent-inheritance
PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$CURRENT" <<'PY'
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);binp=root/"dev-hub/bin"
sys.path.insert(0,str(binp))
spec=importlib.util.spec_from_file_location("v654_agent_foundry",binp/"agent-foundry-planner.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
routing=json.load(open(root/"dev-hub/config/agent-routing.v1.json",encoding="utf-8"))
cfg=json.load(open(root/"dev-hub/config/agent-foundry.v1.json",encoding="utf-8"))
pkg={"id":"v654-real-light","domain":"custom-domain","kind":"primary",
     "capabilities":["custom-a","custom-b","custom-c","custom-d","custom-e"],"roles":[],"toolchain":[]}
x=m.decide_package(pkg,routing,cfg,"v654-real")
assert x["decision"]=="CREATE_EPHEMERAL_AGENT",x
mf=x["manifest"];ep=mf["evolution_profile"];lp=mf["lightweight_runtime_profile"]
assert ep["governance_class"]=="LIGHTWEIGHT_PROJECT_AGENT",ep
assert ep["active_self_mutation"] is False and ep["self_promotion"] is False,ep
assert lp["central_observation_bus"] is True and lp["incremental_learning_uplink"] is True,lp
assert "technology-watch-engine" in lp["local_forbidden_controls"],lp
print("CHACHA_DEV_V654_REAL_FUTURE_AGENT_INHERITANCE=PASS")
PY

stage lightweight-embedded-profile
mkdir -p "$WORK/embedded-input"
printf '#!/usr/bin/env python3\n' >"$WORK/embedded-input/runtime.py"
printf '#!/usr/bin/env python3\n' >"$WORK/embedded-input/relay.py"
printf '// v654\n' >"$WORK/embedded-input/client.mjs"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/project-embedded-assurance.py" \
 --project-id v654-real-project \
 --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
 --runtime-script "$WORK/embedded-input/runtime.py" \
 --relay-script "$WORK/embedded-input/relay.py" \
 --client-runtime "$WORK/embedded-input/client.mjs" \
 --output-dir "$WORK/embedded-bundle" \
 >"$WORK/embedded.out" 2>"$WORK/embedded.err"
python3 - "$WORK/embedded-bundle/embedded-assurance.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
lp=x["lightweight_agent_runtime_profile"]
assert lp["governance_class"]=="LIGHTWEIGHT_EMBEDDED_AGENT",lp
assert lp["technology_watch_local"] is False,lp
assert lp["logician_local"] is False,lp
assert lp["foundry_local"] is False,lp
assert lp["benchmark_orchestrator_local"] is False,lp
assert lp["active_self_mutation"] is False and lp["self_promotion"] is False,lp
assert all(p["runtime_profile"]=="LIGHTWEIGHT_EMBEDDED_AGENT" and p["central_governance"] is True for p in x["local_probes"].values()),x["local_probes"]
print("CHACHA_DEV_V654_REAL_LIGHTWEIGHT_EMBEDDED_PROFILE=PASS")
print("CHACHA_DEV_V654_REAL_LOCAL_HEAVY_GOVERNANCE_DUPLICATION=NO")
PY

stage bus-health-profile-policy
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_observation_bus_health.py"  --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime  --policy "$CURRENT/dev-hub/config/agent-observation-bus.v1.json" --mode lightweight  >"$WORK/bus-health.out" 2>"$WORK/bus-health.err"
python3 - <<'PY'
import json
p='/opt/chacha-dev/runtime/agent-observation/bus-health-latest.json'
x=json.load(open(p,encoding='utf-8'))
assert (x.get("evolution_profile_policy") or {}).get("digest","").startswith("sha256:"),x
assert (x.get("evolution_profile_policy") or {}).get("change_requires_reassessment") is True,x
assert (x.get("universal_evolution_governance_policy") or {}).get("digest","").startswith("sha256:"),x
assert (x.get("universal_evolution_governance_policy") or {}).get("change_requires_reassessment") is True,x
assert (x.get("lightweight_agent_runtime_profile") or {}).get("digest","").startswith("sha256:"),x
assert (x.get("lightweight_agent_runtime_profile") or {}).get("change_requires_reassessment") is True,x
assert x.get("direct_self_mutation") is False and x.get("self_promotion") is False,x
print("CHACHA_DEV_V654_REAL_BUS_PROFILE_POLICY_DIGEST=PASS")
PY

stage canonical-isolation
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo "CANONICAL_TRUST_MUTATED";exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo "CANONICAL_DURABLE_MUTATED";exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo "CANONICAL_TW_MUTATED";exit 43; }
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo "CANONICAL_BUS_MUTATED";exit 44; }
echo "CHACHA_DEV_V654_REAL_CANONICAL_TRUST_DURABLE_TW_BUS_MUTATION=NO"
restore_component_confidence_timer
if [ "$COMPONENT_CONFIDENCE_TIMER_WAS_ACTIVE" -eq 1 ]; then
 systemctl is-active --quiet "$COMPONENT_CONFIDENCE_TIMER"
 echo "CHACHA_DEV_V654_COMPONENT_CONFIDENCE_TIMER_RESTORED=PASS"
fi

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"  --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V654_GUARDIAN_COVERAGE=PASS"

stage post-activation
grep -Fq '"version":"6.54.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
systemctl is-active --quiet chacha-remote-desktop-commander.service
echo "CHACHA_DEV_V654_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v654-universal-evolution-governance-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
idx=json.load(open('/opt/chacha-dev/runtime/agent-evolution/profiles/index.json',encoding='utf-8'))
fleet=json.load(open('/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json',encoding='utf-8'))
by={a["agent_id"]:a for a in fleet.get("agents") or []}
targets=["acceptance-engineer","contract-integrator","integration-architect","ergonomist"]
out={"schema":"chacha.dev/v654-universal-evolution-governance-evidence/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],"universal_profile_count":idx["profile_count"],
 "universal_component_governance":True,"single_evolution_owner_per_component":True,
 "lightweight_embedded_agent_profile":True,"local_heavy_governance_duplication":False,
 "profile_is_performance_score":False,
 "fourth_wave":{aid:{"measurement_coverage_pct":by[aid]["scorecard"]["measurement_coverage_pct"],
                     "production_measurement_coverage_pct":by[aid]["scorecard"].get("production_measurement_coverage_pct")} for aid in targets},
 "curator_profile_only":True,"intendant_profile_only":True,"technology_radar_scope":"PROJECT_LOCAL",
 "promoted_benchmark_evidence_count":4,"benchmark_production_truth":False,
 "canonical_observation_bus_mutation":False,"canonical_trust_durable_technology_watch_mutation":False,
 "guardian_coverage":"PASS","direct_agent_mutation":False,"architecture_council_final_authority":True,
 "automatic_external_spend_eur":0}
open(sys.argv[1],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V654_UNIVERSAL_EVOLUTION_GOVERNANCE=PASS"
echo "CHACHA_DEV_V654_REAL_UNIVERSAL_PROFILE_35=PASS"
echo "CHACHA_DEV_V654_REAL_FOURTH_WAVE_EVIDENCE_PROMOTED=4"
echo "CHACHA_DEV_V654_REAL_PROJECT_RADAR_SCOPE=PROJECT_LOCAL"
echo "CHACHA_DEV_V654_REAL_CURATOR_INTENDANT_PROFILE_ONLY=PASS"
echo "CHACHA_DEV_V654_REAL_BUS_PROFILE_POLICY_DIGEST=PASS"
echo "CHACHA_DEV_V654_REAL_UNIVERSAL_COMPONENT_GOVERNANCE=PASS"
echo "CHACHA_DEV_V654_REAL_SINGLE_EVOLUTION_OWNER=PASS"
echo "CHACHA_DEV_V654_REAL_FUTURE_AGENT_INHERITANCE=PASS"
echo "CHACHA_DEV_V654_REAL_LIGHTWEIGHT_EMBEDDED_PROFILE=PASS"
echo "CHACHA_DEV_V654_REAL_LOCAL_HEAVY_GOVERNANCE_DUPLICATION=NO"
echo "CHACHA_DEV_V654_REAL_CANONICAL_TRUST_DURABLE_TW_BUS_MUTATION=NO"
echo "CHACHA_DEV_V654_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V654_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V654_INSTALL=PASS"

trap - EXIT
cleanup
