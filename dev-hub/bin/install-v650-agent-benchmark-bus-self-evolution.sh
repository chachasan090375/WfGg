#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_V650_REV:-}"; SOURCE_ROOT="${CHACHA_DEV_V650_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"; CURRENT="$BASE/current"; STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"; WORK="$(mktemp -d /tmp/chacha-v650.XXXXXX)"
PREVIOUS=""; ACTIVATED=0; STAGE="bootstrap"
stage(){ STAGE="$1"; echo "CHACHA_DEV_V650_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){ rc=$?; if [ "$rc" -ne 0 ]; then echo "CHACHA_DEV_V650_FAILURE_STAGE=$STAGE"; for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do [ -s "$f" ] || continue; echo "=== $(basename "$f") ==="; tail -200 "$f" || true; done; if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then ln -sfn "$PREVIOUS" "$CURRENT"; systemctl daemon-reload || true; echo "CHACHA_DEV_V650_ROLLBACK=PASS"; fi; rm -rf "$RELEASE" 2>/dev/null || true; fi; cleanup; exit "$rc"; }
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v649-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.49.0"' in s,s
rev=(root/".revision").read_text().strip()
assert rev=="5d600ac662a3f6ce0722f00eda43f91e24d1bacd",rev
idx=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/reassessment-queue-latest.json")
fleet=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json")
assert idx.is_file() and fleet.is_file()
i=json.loads(idx.read_text());f=json.loads(fleet.read_text())
assert f.get("agent_count")==35,f
assert int(i.get("scheduled_action_count") or 0)==70,i
print("CHACHA_DEV_V650_V649_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then SRC="$(readlink -f "$SOURCE_ROOT")"; else curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"; mkdir -p "$WORK/src"; tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1; SRC="$WORK/src"; fi
for req in dev-hub/bin/agent_benchmark_harness.py dev-hub/bin/agent_observation_bus_health.py dev-hub/bin/agent_evolution_daily_cycle.py dev-hub/bin/autonomous-project-orchestrator.py dev-hub/config/agent-benchmark-harness.v1.json dev-hub/config/agent-observation-bus.v1.json dev-hub/tests/test_v650_agent_benchmark_harness.py dev-hub/tests/test_v650_observation_bus_self_evolution.py dev-hub/systemd/chacha-dev-agent-observation-bus-health.service dev-hub/systemd/chacha-dev-agent-observation-bus-health.timer; do [ -f "$SRC/$req" ] || { echo "CHACHA_DEV_V650_INSTALL=BLOCKED reason=missing:$req"; exit 2; }; done

stage candidate-release
mkdir -p "$RELEASE"; cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"; printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile "$RELEASE/dev-hub/bin/agent_benchmark_harness.py" "$RELEASE/dev-hub/bin/agent_observation_bus_health.py" "$RELEASE/dev-hub/bin/agent_evolution_daily_cycle.py" "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
grep -Fq '"version":"6.50.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V650_STATIC=PASS"

stage semantic-qualification
(cd "$RELEASE"; PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v650_agent_benchmark_harness.py) >"$WORK/bench.out" 2>"$WORK/bench.err"
(cd "$RELEASE"; PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v650_observation_bus_self_evolution.py) >"$WORK/bus.out" 2>"$WORK/bus.err"
grep -Fq 'CHACHA_DEV_V650_70_SCHEDULED_ACTIONS_CONSUMED=PASS' "$WORK/bench.out"
grep -Fq 'CHACHA_DEV_V650_BUS_SELF_HEALTH=PASS' "$WORK/bus.out"
echo "CHACHA_DEV_V650_SEMANTIC_QUALIFICATION=PASS"

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf ABSENT; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"; DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"; TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"; BUS="/opt/chacha-dev/runtime/agent-observation/observations.db"
TRUST_BEFORE="$(canon_hash "$TRUST")"; DURABLE_BEFORE="$(canon_hash "$DURABLE")"; TW_BEFORE="$(canon_hash "$TW")"; BUS_BEFORE="$(canon_hash "$BUS")"

stage isolated-bus-self-health
mkdir -p "$WORK/runtime"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_observation_bus_health.py" --repo-root "$RELEASE" --runtime-root "$WORK/runtime" --policy "$RELEASE/dev-hub/config/agent-observation-bus.v1.json" --mode deep >"$WORK/bus-health.out"
grep -Fq 'CHACHA_DEV_V650_BUS_HEALTH=PASS' "$WORK/bus-health.out"
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || { echo CANONICAL_BUS_MUTATED_BY_SHADOW; exit 40; }
echo "CHACHA_DEV_V650_REAL_BUS_SHADOW=PASS"

stage real-70-action-campaign
python3 - "$RELEASE" "$WORK/tw.json" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/"dev-hub/bin"))
import technology_watch_runtime as tw
root=Path(sys.argv[1]);Path(sys.argv[2]).write_text(json.dumps(tw.snapshot_status(root),indent=2)+"\n")
PY
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_benchmark_harness.py" compile --index /opt/chacha-dev/runtime/agent-evolution/reassessment-queue-latest.json --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json --policy "$RELEASE/dev-hub/config/agent-benchmark-harness.v1.json" --technology-watch-status "$WORK/tw.json" --output "$WORK/campaign.json" >"$WORK/campaign.out"
python3 - "$WORK/campaign.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["scheduled_action_count"]==70,x
assert x["contract_count"]==70,x
assert x["benchmark_fixture_is_production_truth"] is False,x
assert all(c["isolated_execution"] and c["independent_oracle_required"] and c["technology_watch_revalidation_required"] for c in x["contracts"]),x
print("CHACHA_DEV_V650_REAL_70_ACTION_CAMPAIGN=PASS")
PY

[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || exit 41
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || exit 42
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || exit 43
[ "$BUS_BEFORE" = "$(canon_hash "$BUS")" ] || exit 44
echo "CHACHA_DEV_V650_REAL_CANONICAL_STATE_MUTATION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"; ACTIVATED=1
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-observation-bus-health.service" /etc/systemd/system/chacha-dev-agent-observation-bus-health.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-observation-bus-health.timer" /etc/systemd/system/chacha-dev-agent-observation-bus-health.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-agent-observation-bus-health.timer >/dev/null
systemctl start chacha-dev-agent-observation-bus-health.service
test -s /opt/chacha-dev/runtime/agent-observation/bus-health-latest.json
mkdir -p /opt/chacha-dev/runtime/agent-evolution/benchmark-campaigns
cp "$WORK/campaign.json" "/opt/chacha-dev/runtime/agent-evolution/benchmark-campaigns/$STAMP.json"
cp "$WORK/campaign.json" /opt/chacha-dev/runtime/agent-evolution/benchmark-campaign-latest.json
echo "CHACHA_DEV_V650_RELEASE_ACTIVATED=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py" --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" --client "$CURRENT/dev-hub/bin/guardian-client.py" --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"

stage post-activation
grep -Fq '"version":"6.50.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
python3 - <<'PY'
import json
c=json.load(open("/opt/chacha-dev/runtime/agent-evolution/benchmark-campaign-latest.json"))
b=json.load(open("/opt/chacha-dev/runtime/agent-observation/bus-health-latest.json"))
assert c["contract_count"]==70,c
assert b["status"]=="PASS",b
assert b["candidate_owner"]=="capability-foundry",b
assert b["direct_self_mutation"] is False and b["self_promotion"] is False,b
print("CHACHA_DEV_V650_POST_ACTIVATION=PASS")
PY

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v650-agent-benchmark-bus-self-evolution-$STAMP.json" <<JSON
{"schema":"chacha.dev/v650-agent-benchmark-bus-self-evolution-evidence/v1","revision":"$REV","observed_at":"$STAMP","scheduled_actions_consumed":70,"benchmark_contracts":70,"benchmark_fixture_production_truth":false,"bus_self_health":"PASS","bus_candidate_owner":"capability-foundry","bus_direct_self_mutation":false,"bus_self_promotion":false,"guardian_coverage":"PASS","architecture_council_final_authority":true,"automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V650_AGENT_BENCHMARK_BUS_SELF_EVOLUTION=PASS"
echo "CHACHA_DEV_V650_REAL_70_ACTION_CAMPAIGN=PASS"
echo "CHACHA_DEV_V650_REAL_BUS_HEALTH=PASS"
echo "CHACHA_DEV_V650_BUS_CANDIDATE_OWNER=CAPABILITY_FOUNDRY"
echo "CHACHA_DEV_V650_BUS_SELF_MUTATION=NO"
echo "CHACHA_DEV_V650_BUS_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V650_INSTALL=PASS"
trap - EXIT
cleanup
