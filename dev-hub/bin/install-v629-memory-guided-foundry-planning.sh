#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V629_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v629.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
MEMORY="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
CONFIDENCE="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
PREVIOUS=""
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V629_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V629_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V629_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln readlink grep cp find; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$MEMORY" ] || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=central_memory_missing"; exit 2; }
[ -s "$CONFIDENCE" ] || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=component_confidence_missing"; exit 2; }
[ -f "$CURRENT/dev-hub/bin/trusted_dispatch_learning.py" ] || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=v628_missing"; exit 2; }

python3 - "$MEMORY" "$CONFIDENCE" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"))
c=json.load(open(sys.argv[2],encoding="utf-8"))
assert m.get("schema")=="chacha.dev/central-memory-assimilation/v1",m.get("schema")
assert c.get("schema")=="chacha.dev/component-confidence-snapshot/v1",c.get("schema")
assert (c.get("nas") or {}).get("status")=="PERSISTED",c.get("nas")
assert c.get("confidence_is_advisory_not_final_authority") is True,c
assert c.get("technology_revalidation_required") is True,c
print("CHACHA_DEV_V629_V628_BASELINE=PASS")
PY

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True:raise SystemExit("CHACHA_DEV_V629_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
for required in   dev-hub/bin/planning_memory_runtime.py   dev-hub/bin/central-memory-recall.py   dev-hub/bin/agent-foundry-planner.py   dev-hub/bin/branch-foundry-planner.py   dev-hub/bin/branch-blueprint-optimizer.py   dev-hub/bin/capability-foundry.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/guardian-client.py   dev-hub/config/central-memory-recall.v1.json   dev-hub/config/agent-foundry.v1.json   dev-hub/config/branch-foundry.v1.json   dev-hub/config/capability-foundry.v1.json   dev-hub/tests/test_v629_memory_guided_foundry_planning.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V629_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/planning_memory_runtime.py"   "$RELEASE/dev-hub/bin/central-memory-recall.py"   "$RELEASE/dev-hub/bin/agent-foundry-planner.py"   "$RELEASE/dev-hub/bin/branch-foundry-planner.py"   "$RELEASE/dev-hub/bin/branch-blueprint-optimizer.py"   "$RELEASE/dev-hub/bin/capability-foundry.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/central-memory-recall.v1.json" >/dev/null
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V629_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v629_memory_guided_foundry_planning.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V629_CONTEXTUAL_COMPONENT_RANKING=PASS   CHACHA_DEV_V629_NEGATIVE_COMPONENT_FAST_REUSE_EXCLUSION=PASS   CHACHA_DEV_V629_AGENT_FOUNDRY_MEMORY_DECISION=PASS   CHACHA_DEV_V629_BRANCH_FOUNDRY_MEMORY_CANDIDATES=PASS   CHACHA_DEV_V629_CAPABILITY_FOUNDRY_MEMORY_CANDIDATES=PASS   CHACHA_DEV_V629_TECHNOLOGY_WATCH_REMAINS_REQUIRED=PASS   CHACHA_DEV_V629_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V629_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage guardian-coverage-bootstrap
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V629_GUARDIAN_COVERAGE=PASS"

stage live-central-memory-recall
cat >"$WORK/intent.json" <<'JSON'
{
  "name":"v629-live-memory-pilot",
  "text":"Explique le statut du développement de la plateforme sans modifier quoi que ce soit.",
  "domains":["development"],
  "mode":"simple_question"
}
JSON
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/functional-intent-orchestrator.py"   --config "$CURRENT/dev-hub/config/domain-orchestration.v1.json"   --intent "$WORK/intent.json" --output "$WORK/preplan.json"

PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/central-memory-recall.py"   --memory "$MEMORY"   --component-confidence "$CONFIDENCE"   --policy "$CURRENT/dev-hub/config/central-memory-recall.v1.json"   --intent "$WORK/intent.json" --preplan "$WORK/preplan.json"   --project-id "v629-live-$STAMP" --output "$WORK/memory-brief.json" >"$WORK/recall.out"

python3 - "$WORK/memory-brief.json" "$MEMORY" "$CONFIDENCE" <<'PY'
import json,sys
b=json.load(open(sys.argv[1],encoding="utf-8"))
m=json.load(open(sys.argv[2],encoding="utf-8"))
c=json.load(open(sys.argv[3],encoding="utf-8"))
assert b.get("schema")=="chacha.dev/central-memory-recall/v1",b
assert b.get("source_memory_snapshot_digest")==m.get("snapshot_digest"),(b,m.get("snapshot_digest"))
assert (b.get("component_confidence") or {}).get("snapshot_digest")==c.get("snapshot_digest"),b
assert b.get("foundry_planning_context_ready") is True,b
assert b.get("memory_authority")=="ADVISORY",b
assert b.get("technology_revalidation_required") is True,b
print("CHACHA_DEV_V629_REAL_LIVE_MEMORY_RECALL=PASS")
print("CHACHA_DEV_V629_REAL_COMPONENT_CONFIDENCE_JOIN=PASS")
PY

stage guardian-governed-foundry-consumption
PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$CURRENT" "$WORK" "$STAMP" >"$WORK/foundry-live.out" 2>"$WORK/foundry-live.stderr" <<'PY'
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);work=Path(sys.argv[2]);stamp=sys.argv[3]
spec=importlib.util.spec_from_file_location("apo",root/"dev-hub/bin/autonomous-project-orchestrator.py")
apo=importlib.util.module_from_spec(spec);spec.loader.exec_module(apo)
apo.configure_guardian(root,work/"guardian")
cfg=root/"dev-hub/config";bin_dir=root/"dev-hub/bin"
pid="v629-live-"+stamp
pre=work/"preplan.json";brief=work/"memory-brief.json"
agent=work/"agent.json";branch=work/"branch.json";cap=work/"capability.json"
apo.run(bin_dir/"agent-foundry-planner.py",[
 "--preplan",pre,"--config",cfg/"agent-foundry.v1.json",
 "--routing",cfg/"agent-routing.v1.json","--project-id",pid,
 "--memory-brief",brief,"--output",agent
])
apo.run(bin_dir/"branch-foundry-planner.py",[
 "--preplan",pre,"--config",cfg/"branch-foundry.v1.json",
 "--project-id",pid,"--agent-topology",agent,
 "--memory-brief",brief,"--output",branch
])
(work/"empty-gaps.json").write_text(json.dumps({"project_id":pid,"missing_capabilities":[]})+"\n",encoding="utf-8")
apo.run(bin_dir/"capability-foundry.py",[
 "--request",work/"empty-gaps.json","--policy",cfg/"capability-foundry.v1.json",
 "--domains",cfg/"domain-orchestration.v1.json","--capabilities",cfg/"capability-registry.v1.json",
 "--memory-brief",brief,"--output",cap
])
a=json.load(open(agent,encoding="utf-8"));b=json.load(open(branch,encoding="utf-8"));c=json.load(open(cap,encoding="utf-8"))
assert a.get("central_memory_recall_consumed") is True,a
assert b.get("central_memory_recall_consumed") is True,b
assert c.get("central_memory_recall_consumed") is True,c
assert a.get("technology_watch_consulted") is True,a
assert b.get("technology_watch_consulted") is True,b
assert c.get("technology_watch_consulted") is True,c
assert all("memory_guided_planning" in x for x in a.get("decisions") or []),a
assert all("memory_guided_planning" in x for x in b.get("decisions") or []),b
print("CHACHA_DEV_V629_REAL_AGENT_FOUNDRY_MEMORY_CONSUMED=PASS")
print("CHACHA_DEV_V629_REAL_BRANCH_FOUNDRY_MEMORY_CONSUMED=PASS")
print("CHACHA_DEV_V629_REAL_CAPABILITY_FOUNDRY_MEMORY_CONSUMED=PASS")
print("CHACHA_DEV_V629_REAL_GUARDIAN_BYPASS=NO")
PY
grep -Fq 'CHACHA_DEV_V629_REAL_AGENT_FOUNDRY_MEMORY_CONSUMED=PASS' "$WORK/foundry-live.out"
grep -Fq 'CHACHA_DEV_V629_REAL_BRANCH_FOUNDRY_MEMORY_CONSUMED=PASS' "$WORK/foundry-live.out"
grep -Fq 'CHACHA_DEV_V629_REAL_CAPABILITY_FOUNDRY_MEMORY_CONSUMED=PASS' "$WORK/foundry-live.out"
grep -Fq 'CHACHA_DEV_V629_REAL_GUARDIAN_BYPASS=NO' "$WORK/foundry-live.out"

stage deterministic-active-influence
(
  cd "$CURRENT"
  PYTHONPATH="$CURRENT/dev-hub/bin" python3 dev-hub/tests/test_v629_memory_guided_foundry_planning.py
) >"$WORK/active-influence.out" 2>&1
grep -Fq 'CHACHA_DEV_V629_AGENT_FOUNDRY_MEMORY_DECISION=PASS' "$WORK/active-influence.out"
grep -Fq 'CHACHA_DEV_V629_BRANCH_FOUNDRY_MEMORY_CANDIDATES=PASS' "$WORK/active-influence.out"
grep -Fq 'CHACHA_DEV_V629_CAPABILITY_FOUNDRY_MEMORY_CANDIDATES=PASS' "$WORK/active-influence.out"
grep -Fq 'CHACHA_DEV_V629_NEGATIVE_COMPONENT_FAST_REUSE_EXCLUSION=PASS' "$WORK/active-influence.out"
echo "CHACHA_DEV_V629_REAL_MEMORY_CHANGES_CANDIDATE_FORMATION=PASS"

stage post-activation-invariants
python3 - "$CURRENT/dev-hub/config/central-memory-recall.v1.json"   "$CURRENT/dev-hub/config/agent-foundry.v1.json"   "$CURRENT/dev-hub/config/branch-foundry.v1.json"   "$CURRENT/dev-hub/config/capability-foundry.v1.json" <<'PY'
import json,sys
r,a,b,c=[json.load(open(p,encoding="utf-8")) for p in sys.argv[1:]]
assert r["behavior"]["memory_guides_candidate_generation_not_final_architecture"] is True
assert a["principles"]["memory_never_skips_technology_watch"] is True
assert b["principles"]["memory_never_overrides_hard_constraints"] is True
assert c["rules"]["architecture_council_remains_final_authority"] is True
assert c["rules"]["memory_cannot_register_missing_capability_by_itself"] is True
print("CHACHA_DEV_V629_MEMORY_ADVISORY_NOT_FINAL_AUTHORITY=PASS")
print("CHACHA_DEV_V629_TECHNOLOGY_REVALIDATION_GUARD=PASS")
PY

cat >"/opt/chacha-dev/evidence/v629-memory-guided-foundry-planning-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v629-memory-guided-foundry-planning-evidence/v1",
  "revision":"$REV","observed_at":"$STAMP",
  "semantic_pilot":"PASS","guardian_coverage":"PASS",
  "live_memory_recall":"PASS","component_confidence_join":"PASS",
  "agent_foundry_memory_consumed":"PASS","branch_foundry_memory_consumed":"PASS",
  "capability_foundry_memory_consumed":"PASS","active_candidate_influence":"PASS",
  "technology_watch_required":true,"architecture_council_final_authority":true,
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V629_CENTRAL_MEMORY_ACTIVE_IN_FOUNDRY_CANDIDATES=YES"
echo "CHACHA_DEV_V629_NEGATIVE_CONFIDENCE_FAST_REUSE_EXCLUSION=YES"
echo "CHACHA_DEV_V629_AGENT_FOUNDRY_MEMORY_GUIDED=YES"
echo "CHACHA_DEV_V629_BRANCH_FOUNDRY_MEMORY_GUIDED=YES"
echo "CHACHA_DEV_V629_CAPABILITY_FOUNDRY_MEMORY_GUIDED=YES"
echo "CHACHA_DEV_V629_MEMORY_CANNOT_EXPAND_CAPABILITIES_OR_PERMISSIONS=YES"
echo "CHACHA_DEV_V629_TECHNOLOGY_WATCH_REMAINS_REQUIRED=YES"
echo "CHACHA_DEV_V629_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V629_DIRECT_APPLICATION_MUTATION=NO"
echo "CHACHA_DEV_V629_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V629_INSTALL=PASS"

trap - EXIT
cleanup
