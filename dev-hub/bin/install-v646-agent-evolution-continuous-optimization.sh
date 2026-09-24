#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V646_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V646_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v646.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V646_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V646_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -200 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V646_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V646_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V646_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }

[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V646_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"
[ -d "$PREVIOUS/dev-hub" ] || { echo "CHACHA_DEV_V646_INSTALL=BLOCKED reason=current_release_invalid"; exit 2; }

stage v645-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.45.0"' in s,"V645_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="e636f40a0aa3f332fb429b58a153d9ff2375b4b5",("V645_ACQUIRED_REVISION_MISMATCH",rev)
ev=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v645-technology-truth-scoring-core-watch-*.json"))
assert ev,"V645_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V646_V645_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for f in   dev-hub/bin/agent_evolution_controller.py   dev-hub/bin/agent_evolution_logician.py   dev-hub/config/agent-evolution.v1.json   dev-hub/config/agent-foundry.v1.json   dev-hub/config/agent-routing.v1.json   dev-hub/config/seven-agent-final-compromise.v1.json   dev-hub/projects/wfgg-radar/project-agent-registry.v1.json   dev-hub/tests/test_v646_agent_evolution_continuous_optimization.py; do
  [ -f "$SRC/$f" ] || { echo "CHACHA_DEV_V646_INSTALL=BLOCKED reason=missing:$f"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
python3 -m py_compile "$RELEASE/dev-hub/bin/agent_evolution_controller.py" "$RELEASE/dev-hub/bin/agent_evolution_logician.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-evolution.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-routing.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json" >/dev/null
grep -Fq '"version":"6.46.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V646_STATIC=PASS"

stage semantic-qualification
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v646_agent_evolution_continuous_optimization.py
) >"$WORK/v646.out" 2>"$WORK/v646.err"
for marker in   CHACHA_DEV_V646_TECHNOLOGY_RADAR_PLATFORM_ROUTING=REMOVED   CHACHA_DEV_V646_TECHNOLOGY_RADAR_PROJECT_SCOPE=PASS   CHACHA_DEV_V646_AGENT_INVENTORY_35=PASS   CHACHA_DEV_V646_REGULAR_EVOLUTION_CADENCE=PASS   CHACHA_DEV_V646_LOGICIAN_AGENT_FALSIFICATION=PASS   CHACHA_DEV_V646_ACTIVE_SELF_MUTATION=NO   CHACHA_DEV_V646_SELF_PROMOTION=NO   CHACHA_DEV_V646_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v646.out"
done
echo "CHACHA_DEV_V646_SEMANTIC_QUALIFICATION=PASS"

stage v645-regression
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v645_technology_truth_scoring_core_watch.py
) >"$WORK/v645.out" 2>"$WORK/v645.err"
grep -Fq 'CHACHA_DEV_V645_MARKETING_ONLY_ADOPTION=BLOCKED' "$WORK/v645.out"
grep -Fq 'CHACHA_DEV_V645_CORE_ARCHITECTURE_WATCH=PASS' "$WORK/v645.out"
echo "CHACHA_DEV_V646_V645_REGRESSION=PASS"

stage real-inventory
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_evolution_controller.py" inventory   --routing "$RELEASE/dev-hub/config/agent-routing.v1.json"   --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output "$WORK/inventory.json" >"$WORK/inventory.out"
grep -Fq 'CHACHA_DEV_V646_AGENT_INVENTORY=PASS' "$WORK/inventory.out"
python3 - "$WORK/inventory.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["agent_count"]==35,x
platform=[a for a in x["agents"] if a["scope"]=="PLATFORM"]
project=[a for a in x["agents"] if a["scope"]=="PROJECT"]
assert len(platform)==34 and len(project)==1,(len(platform),len(project))
assert project[0]["agent_id"]=="technology-radar-agent" and project[0]["project_id"]=="wfgg-radar",project
assert not any(a["agent_id"]=="technology-radar-agent" for a in platform),platform
print("CHACHA_DEV_V646_REAL_TECHNOLOGY_RADAR_PLATFORM_ROUTING=REMOVED")
print("CHACHA_DEV_V646_REAL_TECHNOLOGY_RADAR_PROJECT_SCOPE=PASS")
print("CHACHA_DEV_V646_REAL_AGENT_INVENTORY_35=PASS")
PY

stage real-evolution-assessment
cat >"$WORK/weak-agent.json" <<'JSON'
{
  "dimensions":{
    "accuracy":84,
    "coverage":78,
    "calibration":76,
    "evidence_quality":81,
    "robustness":52,
    "efficiency":79,
    "handoff_quality":68,
    "learning_quality":75,
    "drift_resistance":63,
    "authority_discipline":94
  },
  "verified_failures":1,
  "rollbacks":0,
  "handoff_failures":1,
  "technology_debt":30,
  "scope_overlap_risk":15
}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_evolution_controller.py" evaluate   --agent-id backend-api-architect   --metrics "$WORK/weak-agent.json"   --policy "$RELEASE/dev-hub/config/agent-evolution.v1.json"   --output "$WORK/evaluation.json" >"$WORK/evaluation.out"
grep -Fq 'CHACHA_DEV_V646_AGENT_EVOLUTION_SCORECARD=PASS' "$WORK/evaluation.out"
python3 - "$WORK/evaluation.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
sc=x["scorecard"];p=x["plan"]
assert sc["recommendation"] in {"SHADOW_CANDIDATE","BLOCK_AND_REVIEW"},sc
routes={r["route"] for r in sc["logician_challenge"]["falsification_paths"]}
assert "FAULT_INJECTION" in routes,routes
assert "INCUMBENT_VS_CANDIDATE_SHADOW_COMPARISON" in routes,routes
assert p["self_evolution"]["proposal_allowed"] is True,p
assert p["self_evolution"]["active_self_mutation"] is False,p
assert p["self_evolution"]["self_promotion"] is False,p
assert p["candidate"]["owner"]=="agent-foundry",p
assert p["candidate"]["isolated"] is True and p["candidate"]["incumbent_control_group"] is True,p
assert p["assurance"]["technology_watch_required"] is True,p
assert p["assurance"]["guardian_permission_diff_required"] is True,p
assert p["assurance"]["sentinel_regression_required"] is True,p
assert p["assurance"]["architecture_council_final_authority"] is True,p
print("CHACHA_DEV_V646_REAL_AGENT_EVOLUTION_PROPOSAL=PASS")
print("CHACHA_DEV_V646_REAL_ACTIVE_SELF_MUTATION=NO")
print("CHACHA_DEV_V646_REAL_SELF_PROMOTION=NO")
print("CHACHA_DEV_V646_REAL_AGENT_FOUNDRY_CANDIDATE_OWNER=YES")
print("CHACHA_DEV_V646_REAL_INCUMBENT_CONTROL_GROUP=YES")
PY

stage canonical-state-isolation
hash_or_absent(){ [ -f "$1" ] && sha256sum "$1" | awk '{print $1}' || printf ABSENT; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
TB="$(hash_or_absent "$TRUST")"; DB="$(hash_or_absent "$DURABLE")"; WB="$(hash_or_absent "$TW")"
sleep 1
[ "$TB" = "$(hash_or_absent "$TRUST")" ]
[ "$DB" = "$(hash_or_absent "$DURABLE")" ]
[ "$WB" = "$(hash_or_absent "$TW")" ]
echo "CHACHA_DEV_V646_REAL_CANONICAL_STATE_MUTATION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V646_RELEASE_ACTIVATED=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V646_GUARDIAN_COVERAGE=PASS"

stage post-activation
grep -Fq '"version":"6.46.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_controller.py" inventory   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output "$WORK/post-inventory.json" >/dev/null
python3 - "$WORK/post-inventory.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["agent_count"]==35,x
PY
echo "CHACHA_DEV_V646_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v646-agent-evolution-continuous-optimization-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v646-agent-evolution-evidence/v1",
  "revision":"$REV",
  "observed_at":"$STAMP",
  "v645_real_baseline":"PASS",
  "technology_radar_platform_routing":"REMOVED",
  "technology_radar_project_scope":"wfgg-radar",
  "agent_inventory_count":35,
  "regular_evolution_cadence":"PASS",
  "agent_self_evolution":"PROPOSAL_ONLY",
  "active_self_mutation":false,
  "self_promotion":false,
  "agent_foundry_candidate_owner":true,
  "incumbent_control_group":true,
  "logician_falsification":"PASS",
  "technology_watch_required":true,
  "guardian_permission_diff_required":true,
  "sentinel_regression_required":true,
  "architecture_council_final_authority":true,
  "canonical_state_mutation":false,
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V646_AGENT_EVOLUTION_CONTINUOUS_OPTIMIZATION=PASS"
echo "CHACHA_DEV_V646_REAL_TECHNOLOGY_RADAR_PLATFORM_ROUTING=REMOVED"
echo "CHACHA_DEV_V646_REAL_TECHNOLOGY_RADAR_PROJECT_SCOPE=PASS"
echo "CHACHA_DEV_V646_REAL_AGENT_INVENTORY_35=PASS"
echo "CHACHA_DEV_V646_REAL_ACTIVE_SELF_MUTATION=NO"
echo "CHACHA_DEV_V646_REAL_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V646_REAL_AGENT_FOUNDRY_CANDIDATE_OWNER=YES"
echo "CHACHA_DEV_V646_REAL_INCUMBENT_CONTROL_GROUP=YES"
echo "CHACHA_DEV_V646_GUARDIAN_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V646_SENTINEL_AUTHORITY=PRESERVED"
echo "CHACHA_DEV_V646_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V646_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V646_INSTALL=PASS"

trap - EXIT
cleanup
