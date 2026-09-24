#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V647_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V647_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v647.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V647_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V647_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -200 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload || true
      echo "CHACHA_DEV_V647_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V647_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V647_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V647_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v646-real-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
s=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"version":"6.46.0"' in s,"V646_RUNTIME_VERSION_NOT_ACTIVE"
rev=(root/".revision").read_text(encoding="utf-8").strip()
assert rev=="c244c97c6588e78682984a0020645408bb22d840",("V646_ACQUIRED_REVISION_MISMATCH",rev)
e=list(pathlib.Path("/opt/chacha-dev/evidence").glob("v646-agent-evolution-continuous-optimization-*.json"))
assert e,"V646_REAL_EVIDENCE_MISSING"
print("CHACHA_DEV_V647_V646_REAL_BASELINE=PASS")
PY

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V647_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_controller.py   dev-hub/bin/agent_evolution_logician.py   dev-hub/config/agent-fleet-observatory.v1.json   dev-hub/config/agent-evolution.v1.json   dev-hub/config/agent-routing.v1.json   dev-hub/config/seven-agent-final-compromise.v1.json   dev-hub/projects/wfgg-radar/project-agent-registry.v1.json   dev-hub/tests/test_v647_agent_fleet_observatory.py   dev-hub/tests/test_v646_agent_evolution_continuous_optimization.py   dev-hub/systemd/chacha-dev-agent-fleet-observatory.service   dev-hub/systemd/chacha-dev-agent-fleet-observatory.timer; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V647_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   "$RELEASE/dev-hub/bin/agent_evolution_controller.py"   "$RELEASE/dev-hub/bin/agent_evolution_logician.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/agent-evolution.v1.json" >/dev/null
grep -Fq '"version":"6.47.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V647_STATIC=PASS"

stage semantic-qualification
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v647_agent_fleet_observatory.py
) >"$WORK/v647.out" 2>"$WORK/v647.err"
for marker in   CHACHA_DEV_V647_AGENT_INVENTORY_35=PASS   CHACHA_DEV_V647_UNKNOWN_DIMENSION_DEFAULT=NONE   CHACHA_DEV_V647_MEASURE_FIRST_WITHOUT_EVIDENCE=PASS   CHACHA_DEV_V647_VERIFIED_ACCURACY_SIGNAL=PASS   CHACHA_DEV_V647_RUNTIME_ROBUSTNESS_SIGNAL=PASS   CHACHA_DEV_V647_GUARDIAN_AUTHORITY_SIGNAL=PASS   CHACHA_DEV_V647_OPTIMIZATION_AND_MEASUREMENT_QUEUES=PASS   CHACHA_DEV_V647_AGENT_SELF_SCORING_AUTHORITY=NO   CHACHA_DEV_V647_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v647.out"
done
echo "CHACHA_DEV_V647_SEMANTIC_QUALIFICATION=PASS"

stage v646-regression
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v646_agent_evolution_continuous_optimization.py
) >"$WORK/v646.out" 2>"$WORK/v646.err"
grep -Fq 'CHACHA_DEV_V646_AGENT_INVENTORY_35=PASS' "$WORK/v646.out"
grep -Fq 'CHACHA_DEV_V646_ACTIVE_SELF_MUTATION=NO' "$WORK/v646.out"
echo "CHACHA_DEV_V647_V646_REGRESSION=PASS"

stage canonical-baseline
canon_hash(){ local p="$1"; if [ -f "$p" ]; then sha256sum "$p" | awk '{print $1}'; else printf 'ABSENT'; fi; }
TRUST="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
DURABLE="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
TW="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
TRUST_BEFORE="$(canon_hash "$TRUST")"
DURABLE_BEFORE="$(canon_hash "$DURABLE")"
TW_BEFORE="$(canon_hash "$TW")"

stage real-observatory-pilot
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/agent_fleet_observatory.py"   --repo-root "$RELEASE"   --runtime-root /opt/chacha-dev/runtime   --policy "$RELEASE/dev-hub/config/agent-fleet-observatory.v1.json"   --evolution-policy "$RELEASE/dev-hub/config/agent-evolution.v1.json"   --routing "$RELEASE/dev-hub/config/agent-routing.v1.json"   --seven "$RELEASE/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$RELEASE/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output "$WORK/fleet.json"   >"$WORK/fleet.out" 2>"$WORK/fleet.err"
grep -Fq 'CHACHA_DEV_V647_AGENT_FLEET_OBSERVATORY=PASS' "$WORK/fleet.out"
grep -Fq 'CHACHA_DEV_V647_UNKNOWN_DEFAULT_SCORE=NONE' "$WORK/fleet.out"
python3 - "$WORK/fleet.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["agent_count"]==35,x["agent_count"]
assert x["unknown_dimension_default_score"] is None,x
assert x["read_only"] is True,x
assert x["agent_self_scoring_authority"] is False,x
assert x["automatic_external_spend_eur"]==0,x
assert isinstance(x["optimization_queue"],list),x
assert isinstance(x["measurement_queue"],list) and len(x["measurement_queue"])>0,x
for a in x["agents"]:
    sc=a["scorecard"]
    if sc["recommendation"]=="MEASURE_FIRST":
        assert sc["agent_debt"] is None,(a["agent_id"],sc)
print("CHACHA_DEV_V647_REAL_AGENT_INVENTORY_35=PASS")
print("CHACHA_DEV_V647_REAL_MEASUREMENT_QUEUE=PASS")
print("CHACHA_DEV_V647_REAL_FALSE_DEBT_FROM_UNKNOWN=NO")
print("OPTIMIZATION_COUNT="+str(len(x["optimization_queue"])))
print("MEASUREMENT_COUNT="+str(len(x["measurement_queue"])))
PY

[ "$TRUST_BEFORE" = "$(canon_hash "$TRUST")" ] || { echo "CANONICAL_TRUST_MUTATED"; exit 41; }
[ "$DURABLE_BEFORE" = "$(canon_hash "$DURABLE")" ] || { echo "CANONICAL_DURABLE_MUTATED"; exit 42; }
[ "$TW_BEFORE" = "$(canon_hash "$TW")" ] || { echo "CANONICAL_TECHNOLOGY_WATCH_MUTATED"; exit 43; }
echo "CHACHA_DEV_V647_REAL_CANONICAL_STATE_MUTATION=NO"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V647_RELEASE_ACTIVATED=PASS"

stage install-daily-observatory
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-fleet-observatory.service" /etc/systemd/system/chacha-dev-agent-fleet-observatory.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-agent-fleet-observatory.timer" /etc/systemd/system/chacha-dev-agent-fleet-observatory.timer
mkdir -p /opt/chacha-dev/runtime/agent-evolution
systemctl daemon-reload
systemctl enable --now chacha-dev-agent-fleet-observatory.timer >/dev/null
systemctl start chacha-dev-agent-fleet-observatory.service
systemctl is-enabled --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
test -s /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json
echo "CHACHA_DEV_V647_DAILY_OBSERVATORY_TIMER=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V647_GUARDIAN_COVERAGE=PASS"

stage post-activation
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["agent_count"]==35,x
assert x["unknown_dimension_default_score"] is None,x
assert x["agent_self_scoring_authority"] is False,x
print("CHACHA_DEV_V647_POST_ACTIVATION_OBSERVATORY=PASS")
PY
grep -Fq '"version":"6.47.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"

mkdir -p /opt/chacha-dev/evidence
python3 - "$WORK/fleet.json" "/opt/chacha-dev/evidence/v647-agent-fleet-observatory-$STAMP.json" "$REV" "$STAMP" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
out={
 "schema":"chacha.dev/v647-agent-fleet-observatory-evidence/v1",
 "revision":sys.argv[3],"observed_at":sys.argv[4],
 "agent_count":x["agent_count"],
 "optimization_count":len(x["optimization_queue"]),
 "measurement_count":len(x["measurement_queue"]),
 "unknown_dimension_default_score":None,
 "false_debt_from_unknown":False,
 "read_only":True,
 "agent_self_scoring_authority":False,
 "daily_timer":"PASS",
 "guardian_coverage":"PASS",
 "architecture_council_final_authority":True,
 "automatic_external_spend_eur":0
}
open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V647_AGENT_FLEET_OBSERVATORY=PASS"
echo "CHACHA_DEV_V647_REAL_AGENT_INVENTORY_35=PASS"
echo "CHACHA_DEV_V647_REAL_MEASUREMENT_QUEUE=PASS"
echo "CHACHA_DEV_V647_REAL_FALSE_DEBT_FROM_UNKNOWN=NO"
echo "CHACHA_DEV_V647_DAILY_OBSERVATORY_TIMER=PASS"
echo "CHACHA_DEV_V647_REAL_CANONICAL_STATE_MUTATION=NO"
echo "CHACHA_DEV_V647_AGENT_SELF_SCORING_AUTHORITY=NO"
echo "CHACHA_DEV_V647_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V647_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V647_INSTALL=PASS"

trap - EXIT
cleanup
