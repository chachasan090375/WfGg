#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V700_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V700_SOURCE_ROOT:-}"
PURGE_APPROVED="${CHACHA_DEV_V7_PURGE_APPROVED:-NO}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
RUNTIME="/opt/chacha-dev/runtime"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v700.XXXXXX)"
EVIDENCE="/opt/chacha-dev/evidence"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_ACTIVE=0
BUS_ACTIVE=0

stage(){ STAGE="$1";echo "CHACHA_DEV_V700_STAGE=$STAGE"; }
restore_timers(){
  [ "$FLEET_ACTIVE" -eq 1 ] && systemctl start "$FLEET_TIMER" >/dev/null 2>&1 || true
  [ "$BUS_ACTIVE" -eq 1 ] && systemctl start "$BUS_TIMER" >/dev/null 2>&1 || true
}
cleanup(){ restore_timers;rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V700_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ===";tail -300 "$f" || true
    done
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V700_RUNTIME_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V700_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V700_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V700_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v663-acquired-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,sys,json
root=pathlib.Path(sys.argv[1]);rev=(root/".revision").read_text().strip()
assert rev=="a3803180a64f1ea95d94466b7b10529a7a4af92f",rev
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text()
assert '"version":"6.63.0"' in src
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v663-runtime-surface-instrumentation-readiness-*.json"))
assert ev,"V663_ACQUIRED_EVIDENCE_MISSING"
x=json.loads(ev[-1].read_text())
assert x.get("revision")==rev,x
assert x["radar"]["scope"]=="PROJECT_ONLY" and x["radar"]["sre_release_execution_credit"] is False,x
print("CHACHA_DEV_V700_V663_ACQUIRED_BASELINE=PASS")
PY

stage source
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src";tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
for p in   dev-hub/bin/install-v700-consolidated-platform-baseline.sh   dev-hub/bin/build-v7-runtime-release.py   dev-hub/bin/intendant-platform-consolidator.py   dev-hub/bin/architecture-council-platform-consolidation-v7.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_profile.py   dev-hub/bin/component_evolution_governance.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/bin/technology-watch-service.py   dev-hub/bin/agent_observation_bus.py   dev-hub/config/platform-consolidation.v1.json   dev-hub/config/platform-baseline.v7.json   dev-hub/tests/test_v700_consolidated_platform_baseline.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V700_INSTALL=BLOCKED reason=missing:$p";exit 2; }
done

stage source-qualification
(cd "$SRC";PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v700_consolidated_platform_baseline.py) >"$WORK/v700.out" 2>"$WORK/v700.err"
for m in   CHACHA_DEV_V700_CANONICAL_BASELINE=PASS   CHACHA_DEV_V700_COMPILED_RUNTIME=PASS   CHACHA_DEV_V700_INTENDANT_CONSOLIDATOR=PASS   CHACHA_DEV_V700_ARCHITECTURE_COUNCIL_CONSOLIDATION=PASS   CHACHA_DEV_V700_THREE_RELEASE_RETENTION=PASS   CHACHA_DEV_V700_RADAR_PROJECT_ONLY=PASS   CHACHA_DEV_V700_GIT_HISTORY_PRESERVED=YES; do grep -Fq "$m" "$WORK/v700.out";done
for t in   dev-hub/tests/test_v660_independent_accuracy_attestation.py   dev-hub/tests/test_v661_real_world_evidence_isolated_candidate.py   dev-hub/tests/test_v663_runtime_surface_instrumentation_readiness.py   dev-hub/tests/test_v664_real_instrumented_project_acceptance_council.py; do
  (cd "$SRC";PYTHONPATH=dev-hub/bin python3 "$t") >>"$WORK/regression.out" 2>>"$WORK/regression.err"
done
echo "CHACHA_DEV_V700_SOURCE_QUALIFICATION=PASS"

stage exact-sha-assurance
python3 - "$REV" <<'PY'
import json,sys,urllib.parse,urllib.request
rev=sys.argv[1];q=urllib.parse.urlencode({"head_sha":rev,"per_page":50})
req=urllib.request.Request("https://api.github.com/repos/chachasan090375/WfGg/actions/runs?"+q,
 headers={"User-Agent":"ChaCha-DEV-V700-Installer/1.0","Accept":"application/vnd.github+json"})
with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read().decode())
need={"ChaCha DEV Sentinel technical assurance","ChaCha DEV V7 consolidated platform baseline qualification"}
rows=x.get("workflow_runs") or []
for name in need:
 assert any(w.get("name")==name and w.get("head_sha")==rev and w.get("status")=="completed" and w.get("conclusion")=="success" for w in rows),(name,[(w.get("name"),w.get("status"),w.get("conclusion")) for w in rows])
print("CHACHA_DEV_V700_EXACT_SHA_ASSURANCE=PASS")
PY

stage build-compiled-release
mkdir -p "$RELEASE"
python3 "$SRC/dev-hub/bin/build-v7-runtime-release.py"   --source-root "$SRC" --output-root "$RELEASE" --manifest "$WORK/compiled-manifest.json"   >"$WORK/compile.out" 2>"$WORK/compile.err"
printf '%s\n' "$REV" >"$RELEASE/.revision"
grep -Fq 'CHACHA_DEV_V7_COMPILED_RUNTIME_RELEASE=PASS' "$WORK/compile.out"
[ ! -d "$RELEASE/dev-hub/tests" ]
[ ! -d "$RELEASE/dev-hub/docs" ]
[ -z "$(find "$RELEASE/dev-hub/bin" -maxdepth 1 -type f -name 'install-v6*.sh' -print -quit)" ]
grep -Fq '"version":"7.0.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
echo "CHACHA_DEV_V700_COMPILED_RELEASE=PASS"

stage activate
if systemctl is-active --quiet "$FLEET_TIMER"; then FLEET_ACTIVE=1;systemctl stop "$FLEET_TIMER";fi
if systemctl is-active --quiet "$BUS_TIMER"; then BUS_ACTIVE=1;systemctl stop "$BUS_TIMER";fi
ln -sfn "$RELEASE" "$CURRENT";ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
echo "CHACHA_DEV_V700_RELEASE_ACTIVATED=PASS"

stage quarantine-aborted-v664
python3 - "$CURRENT" "$REV" <<'PY'
import json,sys,pathlib
root=pathlib.Path(sys.argv[1]);rev=sys.argv[2]
sys.path.insert(0,str(root/"dev-hub/bin"))
import agent_observation_bus as aob
aborted="a059ac0392c42961229106ee3d3d9c1871d608f6"
event={
 "schema":"chacha.dev/agent-observation-event/v1",
 "event_id":"aobs-aborted-runtime-"+aborted,
 "event_type":"RUNTIME_REVISION_ABORTED",
 "source_id":"central-orchestrator","source_surface":"v7-platform-consolidation",
 "project_id":"chacha-dev-platform-runtime","subject_role":"platform-runtime",
 "outcome":"ABORTED","revision":rev,"verification":"OBSERVED",
 "capabilities":[],"evidence_refs":["github-revision:"+aborted],
 "details":{"aborted_revision":aborted,"reason":"V664_CONCURRENT_PILOT_ROLLED_BACK_WITHOUT_ACQUISITION","production_truth":False}
}
o=aob.publish(event,runtime_root=pathlib.Path("/opt/chacha-dev/runtime"))
assert o["status"] in {"PASS","DUPLICATE"},o
v=aob.verify_chain(pathlib.Path("/opt/chacha-dev/runtime"))
assert v["status"]=="PASS",v
print("CHACHA_DEV_V700_ABORTED_REVISION_QUARANTINE=PASS")
PY

stage runtime-health
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"   --repo-root "$CURRENT" --runtime-root "$RUNTIME"   --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"   --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output "$RUNTIME/agent-evolution/fleet-observatory-latest.json" >"$WORK/fleet.out" 2>"$WORK/fleet.err"
python3 - "$RUNTIME/agent-evolution/fleet-observatory-latest.json" <<'PY'
import json,sys
f=json.load(open(sys.argv[1]));assert f["agent_count"]==35,f.get("agent_count")
by={a["agent_id"]:a for a in f["agents"]};r=by["technology-radar-agent"]
assert r["scope"]=="PROJECT",r["scope"]
assert r["scorecard"]["production_measurement_coverage_pct"]==20.0,r["scorecard"]
assert r["metrics"]["signals"]["project_local_runtime_coverage_present"] is False,r["metrics"]["signals"]
assert sum(1 for a in f["agents"] if a["scorecard"].get("recommendation")=="MEASURE_FIRST")==0
print("CHACHA_DEV_V700_FLEET=PASS")
PY
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py"   --fleet "$RUNTIME/agent-evolution/fleet-observatory-latest.json"   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"   --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"   --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json"   --output-root "$RUNTIME/agent-evolution/profiles" >"$WORK/profiles.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS' "$WORK/profiles.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py"   --agent-profiles "$RUNTIME/agent-evolution/profiles/index.json"   --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json"   --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json"   --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json"   --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"   --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json"   --output "$RUNTIME/agent-evolution/component-governance-latest.json" >"$WORK/components.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/components.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output "$RUNTIME/guardian/coverage-latest.json" >"$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" status >"$WORK/watch.out"
grep -Fq 'CHACHA_TECHNOLOGY_WATCH_STATUS=FRESH' "$WORK/watch.out"
echo "CHACHA_DEV_V700_RUNTIME_HEALTH=PASS"

stage consolidation-dry-run
mkdir -p "$EVIDENCE"
PLAN="$EVIDENCE/v700-consolidation-plan-$STAMP.json"
APPROVAL="$EVIDENCE/v700-consolidation-approval-$STAMP.json"
ARCHIVE="$EVIDENCE/v700-retirement-archive-$STAMP.json"
APPLIED="$EVIDENCE/v700-consolidation-applied-$STAMP.json"
python3 "$CURRENT/dev-hub/bin/intendant-platform-consolidator.py"   --platform-root "$BASE" --policy "$CURRENT/dev-hub/config/platform-consolidation.v1.json"   --output "$PLAN" >"$WORK/consolidation-dry.out"
grep -Fq 'MODE=DRY_RUN' "$WORK/consolidation-dry.out"
python3 - "$PLAN" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x["active_revision"]==sys.argv[2],x
assert x["active_version"]=="7.0.0",x
assert x["missing_verified_rollback_revisions"]==[],x
assert x["keep_count"]==3,x
assert x["retire_count"]>=80,x
print("CHACHA_DEV_V700_REAL_CONSOLIDATION_DRY_RUN=PASS")
PY

stage consolidation-council
COUNCIL_ARGS=()
[ "$PURGE_APPROVED" = "YES" ] && COUNCIL_ARGS+=(--operator-explicit-purge-approval)
python3 "$CURRENT/dev-hub/bin/architecture-council-platform-consolidation-v7.py"   --plan "$PLAN" --policy "$CURRENT/dev-hub/config/platform-consolidation.v1.json"   --guardian-coverage "$RUNTIME/guardian/coverage-latest.json" --revision "$REV"   "${COUNCIL_ARGS[@]}" --output "$APPROVAL" >"$WORK/council.out" 2>"$WORK/council.err"
if [ "$PURGE_APPROVED" = "YES" ]; then
  grep -Fq 'CHACHA_DEV_V7_CONSOLIDATION_COUNCIL=PASS' "$WORK/council.out"
else
  echo "CHACHA_DEV_V700_PURGE_APPLY=SKIPPED_NO_EXPLICIT_APPROVAL"
fi

stage consolidation-apply
if [ "$PURGE_APPROVED" = "YES" ]; then
  python3 "$CURRENT/dev-hub/bin/intendant-platform-consolidator.py"     --platform-root "$BASE" --policy "$CURRENT/dev-hub/config/platform-consolidation.v1.json"     --output "$APPLIED" --archive-manifest "$ARCHIVE" --approval "$APPROVAL"     --apply --explicit-destructive-apply >"$WORK/consolidation-apply.out"
  grep -Fq 'MODE=APPLY' "$WORK/consolidation-apply.out"
  python3 - "$APPLIED" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x["release_count_after"]==3,x
assert x["deleted_release_count"]>=80,x
print("CHACHA_DEV_V700_REAL_PURGE=PASS")
print("CHACHA_DEV_V700_FREED_MIB="+str(round(x["freed_bytes"]/1024/1024,1)))
PY
fi

stage final-health
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
[ "$(cat "$CURRENT/.revision")" = "$REV" ]
grep -Fq '"version":"7.0.0"' "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"
systemctl is-active --quiet chacha-remote-desktop-commander.service
restore_timers
systemctl is-active --quiet "$FLEET_TIMER"
systemctl is-active --quiet "$BUS_TIMER"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_observation_bus.py" verify >"$WORK/bus.out"
grep -Fq 'CHACHA_DEV_V648_OBSERVATION_CHAIN=PASS' "$WORK/bus.out"

stage evidence
python3 - "$EVIDENCE/v700-consolidated-platform-baseline-$STAMP.json" "$REV" "$STAMP" "$WORK/compiled-manifest.json" "$PLAN" "$APPLIED" "$PURGE_APPROVED" <<'PY'
import json,sys,pathlib
compiled=json.load(open(sys.argv[4]));plan=json.load(open(sys.argv[5]))
applied_path=pathlib.Path(sys.argv[6]);applied=json.load(open(applied_path)) if applied_path.is_file() else None
fleet=json.load(open("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json"))
out={
 "schema":"chacha.dev/v700-consolidated-platform-baseline-evidence/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],"platform_version":"7.0.0",
 "compiled_runtime":{"source_files":compiled["source_files"],"compiled_files":compiled["compiled_files"],
   "source_bytes":compiled["source_bytes"],"compiled_bytes":compiled["compiled_bytes"],
   "excluded_file_count":compiled["excluded_file_count"],"tree_sha256":compiled["compiled_tree_sha256"]},
 "consolidation":{"owner_agent":"intendant","dry_run_retire_count":plan["retire_count"],
   "estimated_savings_bytes":plan["bytes_retirable"],"purge_approved":sys.argv[7]=="YES",
   "applied":applied is not None,"deleted_release_count":(applied or {}).get("deleted_release_count",0),
   "freed_bytes":(applied or {}).get("freed_bytes",0),"release_count_after":(applied or {}).get("release_count_after",plan["release_count_before"])},
 "agent_count":fleet["agent_count"],
 "radar_scope":"PROJECT_ONLY","git_history_preserved":True,"remote_branch_deletion":False,
 "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
 "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0
}
open(sys.argv[1],"w").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V700_CANONICAL_BASELINE=PASS"
echo "CHACHA_DEV_V700_COMPILED_RUNTIME=PASS"
echo "CHACHA_DEV_V700_RUNTIME_HEALTH=PASS"
echo "CHACHA_DEV_V700_INTENDANT_CONSOLIDATION=PASS"
echo "CHACHA_DEV_V700_GIT_HISTORY_PRESERVED=YES"
echo "CHACHA_DEV_V700_REMOTE_BRANCH_AUTO_DELETE=NO"
echo "CHACHA_DEV_V700_RADAR_PROJECT_ONLY=PASS"
echo "CHACHA_DEV_V700_ACCEPTANCE_PRODUCTION_ACTIVATION=NO"
echo "CHACHA_DEV_V700_CANONICAL_BUS_REWRITE=NO"
echo "CHACHA_DEV_V700_BENCHMARK_EVIDENCE_MUTATION=NO"
echo "CHACHA_DEV_V700_SELF_MUTATION=NO"
echo "CHACHA_DEV_V700_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V700_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V700_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V700_INSTALL=PASS"

trap - EXIT
cleanup
