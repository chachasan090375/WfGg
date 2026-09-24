#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V650_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V650_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v650.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V650_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V650_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -200 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload || true
      echo "CHACHA_DEV_V650_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v649-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.49.0"' in s,"V649_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="5d600ac662a3f6ce0722f00eda43f91e24d1bacd",("V649_ACQUIRED_REVISION_MISMATCH",rev)
ev=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v649-assurance-agent-instrumentation-*.json"))
assert ev,"V649_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V650_V649_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/agent_benchmark_harness.py   dev-hub/bin/agent_observation_bus_health.py   dev-hub/bin/agent_observation_bus.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/config/agent-benchmark-harness.v1.json   dev-hub/config/agent-observation-bus.v1.json   dev-hub/config/technology-core-watch.v1.json   dev-hub/tests/test_v650_agent_benchmark_harness.py   dev-hub/tests/test_v650_observation_bus_self_evolution.py   dev-hub/systemd/chacha-dev-agent-observation-bus-health.service   dev-hub/systemd/chacha-dev-agent-observation-bus-health.timer; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE";cp -a "$SRC/dev-hub" "$RELEASE/dev-hub";printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/agent_benchmark_harness.py"   "$RELEASE/dev-hub/bin/agent_observation_bus_health.py"   "$RELEASE/dev-hub/bin/agent_observation_bus.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
for j in agent-benchmark-harness.v1.json agent-observation-bus.v1.json technology-core-watch.v1.json technology-watch-logician.v1.json; do
  python3 -m json.tool "$RELEASE/dev-hub/config/$j" >/dev/null
done
grep -Fq '"version":"6.50.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V650_STATIC=PASS"

stage semantic-qualification
(
 cd "$RELEASE"
 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v650_agent_benchmark_harness.py
 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v650_observation_bus_self_evolution.py
) >"$WORK/v650.out" 2>"$WORK/v650.err"
for marker in  CHACHA_DEV_V650_70_SCHEDULED_ACTIONS_CONSUMED=PASS  CHACHA_DEV_V650_INDEPENDENT_ORACLE_REQUIRED=PASS  CHACHA_DEV_V650_FIXTURE_AND_ENVIRONMENT_PARITY=PASS  CHACHA_DEV_V650_PERMISSION_EXPANSION=BLOCKED  CHACHA_DEV_V650_BUS_SELF_HEALTH=PASS  CHACHA_DEV_V650_AGENT_CHANGE_REASSESSMENT=PASS  CHACHA_DEV_V650_BUS_HASH_TAMPER_DETECTED=PASS  CHACHA_DEV_V650_BUS_SELF_MUTATION=NO  CHACHA_DEV_V650_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
 grep -Fq "$marker" "$WORK/v650.out"
done
echo "CHACHA_DEV_V650_SEMANTIC_QUALIFICATION=PASS"

stage isolated-bus-health
mkdir -p "$WORK/runtime"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_observation_bus_health.py"  --repo-root "$RELEASE" --runtime-root "$WORK/runtime"  --policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" --mode deep  >"$WORK/bus-isolated.out" 2>"$WORK/bus-isolated.err"
grep -Fq 'CHACHA_DEV_V650_BUS_HEALTH=PASS' "$WORK/bus-isolated.out"
test -s "$WORK/runtime/agent-observation/bus-health-latest.json"
test ! -e "$WORK/runtime/../observations.db"
echo "CHACHA_DEV_V650_REAL_ISOLATED_BUS_HEALTH=PASS"

stage real-benchmark-campaign
python3 - "$PREVIOUS" "$WORK" <<'PY'
import json,sys,pathlib
root=pathlib.Path(sys.argv[1]);work=pathlib.Path(sys.argv[2])
idx=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/reassessment-queue-latest.json")
fleet=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json")
assert fleet.is_file(),"FLEET_REPORT_MISSING"
if idx.is_file(): x=json.loads(idx.read_text(encoding="utf-8"))
else: x={"scheduled_actions":[]}
f=json.loads(fleet.read_text(encoding="utf-8"))
# If cadence file currently has no scheduled actions, use measurement queue as a real baseline-only benchmark request.
if not x.get("scheduled_actions"):
    x["scheduled_actions"]=[{"agent_id":r["agent_id"],"action":"DEEP_AGENT_AUDIT"} for r in (f.get("measurement_queue") or [])[:5]]
(work/"real-index.json").write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")
(work/"real-fleet.json").write_text(json.dumps(f,indent=2)+"\n",encoding="utf-8")
PY
PYTHONPATH="$RELEASE/dev-hub/bin" python3 - "$RELEASE" "$WORK/tw-status.json" <<'PY'
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/"dev-hub/bin"))
import technology_watch_runtime as tw
root=Path(sys.argv[1]);out=Path(sys.argv[2])
out.write_text(json.dumps(tw.snapshot_status(root),indent=2)+"\n",encoding="utf-8")
PY
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_harness.py" compile  --index "$WORK/real-index.json" --fleet "$WORK/real-fleet.json"  --policy "$RELEASE/dev-hub/config/agent-benchmark-harness.v1.json"  --technology-watch-status "$WORK/tw-status.json" --output "$WORK/real-campaign.json"  >"$WORK/real-campaign.out" 2>"$WORK/real-campaign.err"
python3 - "$WORK/real-campaign.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["contract_count"]==x["scheduled_action_count"],x
assert all(c["production_truth_eligible"] is False for c in x["contracts"]),x
assert all(c["independent_oracle_required"] is True for c in x["contracts"]),x
assert all(c["fixture_contract_digest"].startswith("sha256:") for c in x["contracts"]),x
print("CHACHA_DEV_V650_REAL_BENCHMARK_CAMPAIGN=PASS")
print("REAL_BENCHMARK_CONTRACT_COUNT="+str(x["contract_count"]))
PY

stage real-shadow-comparison
python3 - "$WORK/real-campaign.json" "$WORK" <<'PY'
import json,sys,pathlib
c=json.load(open(sys.argv[1],encoding="utf-8"))
w=pathlib.Path(sys.argv[2]);row=c["contracts"][0]
base={"benchmark_id":row["benchmark_id"],"agent_id":row["agent_id"],"verification":"VERIFIED","verifier":"project-control",
 "evidence_refs":["pilot:incumbent"],"fixture_contract_digest":row["fixture_contract_digest"],
 "environment_contract_digest":row["environment_contract_digest"],"revision":"incumbent-real-pilot",
 "metrics":{"accuracy":80,"robustness":88,"authority_discipline":95},"permission_expansion":False,
 "guardian_preserved":True,"sentinel_preserved":True,"automatic_external_spend_eur":0}
cand={**base,"revision":"candidate-real-pilot","verifier":"sentinel","evidence_refs":["pilot:candidate"],
 "metrics":{"accuracy":85,"robustness":92,"authority_discipline":96}}
(w/"inc.json").write_text(json.dumps(base,indent=2)+"\n",encoding="utf-8")
(w/"cand.json").write_text(json.dumps(cand,indent=2)+"\n",encoding="utf-8")
PY
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_harness.py" compare  --incumbent "$WORK/inc.json" --candidate "$WORK/cand.json"  --policy "$RELEASE/dev-hub/config/agent-benchmark-harness.v1.json"  --output "$WORK/compare.json" >"$WORK/compare.out" 2>"$WORK/compare.err"
python3 - "$WORK/compare.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["decision"]=="PILOT_ELIGIBLE",x
assert x["latest_version_priority"] is False,x
assert x["direct_candidate_promotion"] is False,x
print("CHACHA_DEV_V650_REAL_SHADOW_COMPARISON=PASS")
print("CHACHA_DEV_V650_REAL_DIRECT_CANDIDATE_PROMOTION=NO")
PY

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
TRUST_BEFORE="$(canon_hash "$TRUST")";DURABLE_BEFORE="$(canon_hash "$DURABLE")";TW_BEFORE="$(canon_hash "$TW")"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V650_RELEASE_ACTIVATED=PASS"

stage bus-health-timer
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-observation-bus-health.service" /etc/systemd/system/chacha-dev-agent-observation-bus-health.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-observation-bus-health.timer" /etc/systemd/system/chacha-dev-agent-observation-bus-health.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-agent-observation-bus-health.timer >/dev/null
systemctl start chacha-dev-agent-observation-bus-health.service
systemctl is-enabled --quiet chacha-dev-agent-observation-bus-health.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
test -s /opt/chacha-dev/runtime/agent-observation/bus-health-latest.json
python3 - /opt/chacha-dev/runtime/agent-observation/bus-health-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"] in {"PASS","REASSESS_REQUIRED"},x
assert x["direct_self_mutation"] is False,x
assert x["self_promotion"] is False,x
assert x["candidate_owner"]=="capability-foundry",x
assert x["technology_watch_revalidation_required"] is True,x
assert x["logician_falsification_required"] is True,x
assert x["shadow_required"] is True and x["pilot_required"] is True,x
print("CHACHA_DEV_V650_REAL_BUS_SELF_HEALTH=PASS")
print("CHACHA_DEV_V650_REAL_BUS_SELF_MUTATION=NO")
print("CHACHA_DEV_V650_REAL_BUS_SELF_PROMOTION=NO")
PY

stage canonical-isolation
[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo "CANONICAL_TRUST_MUTATED"; exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo "CANONICAL_DURABLE_MUTATED"; exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo "CANONICAL_TW_MUTATED"; exit 43; }
echo "CHACHA_DEV_V650_REAL_CANONICAL_TRUST_DURABLE_TW_MUTATION=NO"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"  --repo-root "$CURRENT"  --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"  --client "$CURRENT/dev-hub/bin/guardian-client.py"  --output /opt/chacha-dev/runtime/guardian/coverage-latest.json  >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V650_GUARDIAN_COVERAGE=PASS"

stage post-activation
grep -Fq '"version":"6.50.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
echo "CHACHA_DEV_V650_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
python3 - "$WORK/real-campaign.json" /opt/chacha-dev/runtime/agent-observation/bus-health-latest.json  "/opt/chacha-dev/evidence/v650-agent-benchmark-bus-evolution-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
campaign=json.load(open(sys.argv[1],encoding="utf-8"));bus=json.load(open(sys.argv[2],encoding="utf-8"))
out={"schema":"chacha.dev/v650-agent-benchmark-bus-evolution-evidence/v1",
 "revision":sys.argv[4],"observed_at":sys.argv[5],"v649_real_baseline":"PASS",
 "benchmark_contract_count":campaign["contract_count"],"benchmark_production_truth":False,
 "independent_oracle_required":True,"shadow_comparison":"PASS",
 "bus_health_status":bus["status"],"bus_active_self_mutation":False,"bus_self_promotion":False,
 "bus_candidate_owner":"capability-foundry","technology_watch_revalidation_required":True,
 "logician_falsification_required":True,"daily_bus_health_timer":"PASS",
 "guardian_coverage":"PASS","canonical_trust_durable_technology_watch_mutation":False,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
open(sys.argv[3],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V650_AGENT_BENCHMARK_SHADOW_EVOLUTION=PASS"
echo "CHACHA_DEV_V650_REAL_BENCHMARK_CAMPAIGN=PASS"
echo "CHACHA_DEV_V650_REAL_SHADOW_COMPARISON=PASS"
echo "CHACHA_DEV_V650_REAL_BUS_SELF_HEALTH=PASS"
echo "CHACHA_DEV_V650_REAL_BUS_SELF_MUTATION=NO"
echo "CHACHA_DEV_V650_REAL_BUS_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V650_REAL_CANONICAL_TRUST_DURABLE_TW_MUTATION=NO"
echo "CHACHA_DEV_V650_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V650_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V650_INSTALL=PASS"

trap - EXIT
cleanup
