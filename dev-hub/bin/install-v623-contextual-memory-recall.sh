#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V623_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v623.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
MEMORY="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
GUARDIAN_URL="https://chacha-dev-guardian.chachasan090375.workers.dev"
PREVIOUS=""
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V623_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V623_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/recall-1.out "$WORK"/recall-2.out "$WORK"/agent.out "$WORK"/branch.out "$WORK"/coverage-bootstrap.out "$WORK"/guardian-recall-pre.out "$WORK"/guardian-recall-post.out "$WORK"/guardian-arch-pre.out "$WORK"/guardian-arch-post.out "$WORK"/coverage.out; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      systemctl restart chacha-dev-central-memory-assimilation.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V623_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V623_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V623_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V623_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$MEMORY" ] || { echo "CHACHA_DEV_V623_INSTALL=BLOCKED reason=v622_memory_snapshot_missing"; exit 2; }
python3 - "$MEMORY" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("schema")=="chacha.dev/central-memory-assimilation/v1",x.get("schema")
assert x.get("single_observation_never_trusted") is True
assert x.get("technology_revalidation_required_before_reuse") is True
assert x.get("nas",{}).get("status")=="PERSISTED",x.get("nas")
print("CHACHA_DEV_V623_V622_MEMORY_BASELINE=PASS")
PY
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V623_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V623_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/central-memory-recall.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/agent-foundry-planner.py   dev-hub/bin/branch-foundry-planner.py   dev-hub/bin/architecture-decision-council.py   dev-hub/bin/functional-intent-orchestrator.py   dev-hub/bin/guardian-client.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/central-memory-recall.v1.json   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V623_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/central-memory-recall.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/agent-foundry-planner.py"   "$RELEASE/dev-hub/bin/branch-foundry-planner.py"   "$RELEASE/dev-hub/bin/architecture-decision-council.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V623_STATIC=PASS"

stage external-guardian-memory-gate
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"central_memory_assimilation_evidence_required":true' "$WORK/guardian-health.json"
grep -Fq '"contextual_memory_recall_evidence_required":true' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V623_EXTERNAL_GUARDIAN_MEMORY_GATE=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

# V6.23.1: publish Guardian coverage before the new governed role executes.
# This also lets Guardian auto-resolve stale coverage holds from an interrupted/rolled-back pilot.
stage guardian-coverage-bootstrap
python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage-bootstrap.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage-bootstrap.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage-bootstrap.out"
echo "CHACHA_DEV_V623_GUARDIAN_COVERAGE_BOOTSTRAP=PASS"

stage build-real-context
python3 - "$CURRENT/dev-hub/config/domain-orchestration.v1.json" "$WORK/intent.json" <<'PY'
import json,sys
cfg=json.load(open(sys.argv[1],encoding="utf-8"))
domains=cfg.get("domains") or {}
if not domains:raise SystemExit("NO_DOMAIN_FOR_V623_PILOT")
domain=next(iter(domains))
intent={
  "name":"v623-contextual-memory-pilot",
  "text":"V6.23 contextual memory recall validation for "+domain,
  "domains":[domain],
  "mode":"focused_change"
}
json.dump(intent,open(sys.argv[2],"w",encoding="utf-8"),indent=2)
print("CHACHA_DEV_V623_PILOT_DOMAIN="+domain)
PY
python3 "$CURRENT/dev-hub/bin/functional-intent-orchestrator.py"   --config "$CURRENT/dev-hub/config/domain-orchestration.v1.json"   --intent "$WORK/intent.json" --output "$WORK/preplan-1.json"

stage contextual-recall-first
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/central-memory-recall.py"   --memory "$MEMORY"   --policy "$CURRENT/dev-hub/config/central-memory-recall.v1.json"   --intent "$WORK/intent.json" --preplan "$WORK/preplan-1.json"   --project-id "v623-runtime-pilot" --output "$WORK/memory-brief-1.json" >"$WORK/recall-1.out"
grep -Fq 'CHACHA_DEV_V623_CENTRAL_MEMORY_RECALL=PASS' "$WORK/recall-1.out"
python3 - "$MEMORY" "$WORK/memory-brief-1.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"));b=json.load(open(sys.argv[2],encoding="utf-8"))
assert b["source_memory_snapshot_digest"]==m["snapshot_digest"],(b.get("source_memory_snapshot_digest"),m.get("snapshot_digest"))
assert b["memory_authority"]=="ADVISORY",b
assert b["provisional_is_actionable"] is False,b
assert b["single_observation_is_actionable"] is False,b
assert b["previous_solution_is_default"] is False,b
assert b["technology_revalidation_required"] is True,b
assert b["architecture_council_final_authority"] is True,b
assert all(x.get("version_status")=="CURRENT_BEST" for x in b.get("current_best_reuse_candidates") or []),b
print("CHACHA_DEV_V623_REAL_CONTEXTUAL_RECALL=PASS")
print("CHACHA_DEV_V623_PROVISIONAL_ACTIONABLE=NO")
print("CHACHA_DEV_V623_PREVIOUS_SOLUTION_DEFAULT=NO")
print("CHACHA_DEV_V623_TECHNOLOGY_REVALIDATION_REQUIRED=YES")
PY

stage contextual-recall-after-discovery
python3 - "$WORK/preplan-1.json" "$WORK/preplan-2.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
x["memory_recall_context_revision"]="post-capability-discovery"
json.dump(x,open(sys.argv[2],"w",encoding="utf-8"),indent=2)
PY
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/central-memory-recall.py"   --memory "$MEMORY"   --policy "$CURRENT/dev-hub/config/central-memory-recall.v1.json"   --intent "$WORK/intent.json" --preplan "$WORK/preplan-2.json"   --project-id "v623-runtime-pilot" --output "$WORK/memory-brief-2.json" >"$WORK/recall-2.out"
python3 - "$WORK/memory-brief-1.json" "$WORK/memory-brief-2.json" <<'PY'
import json,sys
a=json.load(open(sys.argv[1],encoding="utf-8"));b=json.load(open(sys.argv[2],encoding="utf-8"))
assert a["source_memory_snapshot_digest"]==b["source_memory_snapshot_digest"],(a,b)
assert a["query_digest"]!=b["query_digest"],(a["query_digest"],b["query_digest"])
assert b["technology_revalidation_required"] is True
print("CHACHA_DEV_V623_SECOND_RECALL_AFTER_CONTEXT_CHANGE=PASS")
PY

stage foundries-consume-memory
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent-foundry-planner.py"   --preplan "$WORK/preplan-2.json"   --config "$CURRENT/dev-hub/config/agent-foundry.v1.json"   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --project-id "v623-runtime-pilot"   --memory-brief "$WORK/memory-brief-2.json"   --output "$WORK/agent-topology.json" >"$WORK/agent.out"
grep -Fq 'CHACHA_AGENT_FOUNDRY_CENTRAL_MEMORY_RECALL=CONSUMED' "$WORK/agent.out"

PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/branch-foundry-planner.py"   --preplan "$WORK/preplan-2.json"   --config "$CURRENT/dev-hub/config/branch-foundry.v1.json"   --project-id "v623-runtime-pilot"   --agent-topology "$WORK/agent-topology.json"   --memory-brief "$WORK/memory-brief-2.json"   --output "$WORK/branch-topology.json" >"$WORK/branch.out"
grep -Fq 'CHACHA_BRANCH_FOUNDRY_CENTRAL_MEMORY_RECALL=CONSUMED' "$WORK/branch.out"
python3 - "$WORK/agent-topology.json" "$WORK/branch-topology.json" "$WORK/memory-brief-2.json" <<'PY'
import json,sys
a=json.load(open(sys.argv[1],encoding="utf-8"));b=json.load(open(sys.argv[2],encoding="utf-8"));m=json.load(open(sys.argv[3],encoding="utf-8"))
assert a.get("central_memory_recall_consumed") is True,a
assert b.get("central_memory_recall_consumed") is True,b
assert a.get("central_memory_brief_digest")==m.get("brief_digest"),(a,m)
assert b.get("central_memory_brief_digest")==m.get("brief_digest"),(b,m)
for row in a.get("decisions") or []:
    assert (row.get("central_memory_recall") or {}).get("memory_authority")=="ADVISORY",row
for row in b.get("decisions") or []:
    assert (row.get("central_memory_recall") or {}).get("previous_solution_is_default") is False,row
    assert (row.get("central_memory_recall") or {}).get("technology_revalidation_required") is True,row
print("CHACHA_DEV_V623_AGENT_FOUNDRY_MEMORY_RECALL=PASS")
print("CHACHA_DEV_V623_BRANCH_FOUNDRY_MEMORY_RECALL=PASS")
PY

stage guardian-central-memory-recall-contract
ACTION_ID="v623-recall-$STAMP"
cat >"$WORK/guardian-recall-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v623-recall-pre-$STAMP","action_id":"$ACTION_ID","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"central-memory-recall","action":"INVOKE_COMPONENT","task_kind":"central-memory-recall","permission":"plan","project_id":"platform-bootstrap","run_id":"v623-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
cat >"$WORK/guardian-recall-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v623-recall-post-$STAMP","action_id":"$ACTION_ID","phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"central-memory-recall","action":"INVOKE_COMPONENT","task_kind":"central-memory-recall","permission":"plan","project_id":"platform-bootstrap","run_id":"v623-runtime","adapters":[],"evidence":{"emergency_stop_active":false,"output_exists":true},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-recall-pre.json" >"$WORK/guardian-recall-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-recall-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-recall-post.json" >"$WORK/guardian-recall-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-recall-post.out"
echo "CHACHA_DEV_V623_GUARDIAN_RECALL_ROLE_CONTRACT=PASS"

stage guardian-final-architecture-memory-evidence
ARCH_ACTION="v623-arch-$STAMP"
cat >"$WORK/guardian-arch-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v623-arch-pre-$STAMP","action_id":"$ARCH_ACTION","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"architecture-decision-council","action":"FINAL_ARCHITECTURE_DECISION","task_kind":"architecture-decision-council","permission":"plan","project_id":"platform-bootstrap","run_id":"v623-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
cat >"$WORK/guardian-arch-post.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v623-arch-post-$STAMP","action_id":"$ARCH_ACTION","phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"architecture-decision-council","action":"FINAL_ARCHITECTURE_DECISION","task_kind":"architecture-decision-council","permission":"plan","project_id":"platform-bootstrap","run_id":"v623-runtime","adapters":[],"evidence":{"emergency_stop_active":false,"technology_watch_pre":true,"technology_watch_final":true,"central_memory_assimilation":true,"central_memory_recall":true,"reuse_memory":true,"architecture_memory":true,"architecture_portfolio":true,"branch_foundry":true,"agent_foundry":true,"capability_foundry":true,"constraint_policy":true},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-arch-pre.json" >"$WORK/guardian-arch-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-arch-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-arch-post.json" >"$WORK/guardian-arch-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-arch-post.out"
echo "CHACHA_DEV_V623_GUARDIAN_FINAL_ARCH_MEMORY_EVIDENCE=PASS"

stage guardian-coverage
python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V623_GUARDIAN_COVERAGE=PASS"

cat >"/opt/chacha-dev/evidence/v623-contextual-memory-recall-$STAMP.json" <<JSON
{"schema":"chacha.dev/v623-contextual-memory-recall-evidence/v1","revision":"$REV","observed_at":"$STAMP","real_contextual_recall":"PASS","double_recall":"PASS","agent_foundry_memory":"PASS","branch_foundry_memory":"PASS","guardian_recall_contract":"PASS","guardian_final_memory_evidence":"PASS","guardian_coverage":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V623_CENTRAL_ORCHESTRATOR_RECALLS_BEFORE_FOUNDRIES=YES"
echo "CHACHA_DEV_V623_CENTRAL_ORCHESTRATOR_RECALLS_AFTER_DISCOVERY=YES"
echo "CHACHA_DEV_V623_MEMORY_AUTHORITY=ADVISORY"
echo "CHACHA_DEV_V623_PROVISIONAL_MEMORY_ACTIONABLE=NO"
echo "CHACHA_DEV_V623_PREVIOUS_SOLUTION_IS_DEFAULT=NO"
echo "CHACHA_DEV_V623_CURRENT_BEST_REUSE_ONLY=YES"
echo "CHACHA_DEV_V623_TECHNOLOGY_REVALIDATION_REQUIRED=YES"
echo "CHACHA_DEV_V623_GUARDIAN_MEMORY_EVIDENCE_REQUIRED=YES"
echo "CHACHA_DEV_V623_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V623_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V623_INSTALL=PASS"

trap - EXIT
cleanup
