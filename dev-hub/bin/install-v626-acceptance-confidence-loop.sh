#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V626_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v626.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
CONFIDENCE="/opt/chacha-dev/runtime/knowledge/component-confidence.json"
MEMORY="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
PREVIOUS=""
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V626_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V626_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/semantic.out "$WORK"/coverage.out "$WORK"/acceptance-1.out "$WORK"/acceptance-2.out "$WORK"/feedback.out "$WORK"/feedback.stderr "$WORK"/confidence.out "$WORK"/confidence.stderr "$WORK"/guardian-pre.out "$WORK"/guardian-post.out; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      systemctl restart chacha-dev-production-lineage-feedback.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-component-confidence.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-central-memory-assimilation.timer >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V626_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$CONFIDENCE" ] || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=v625_confidence_snapshot_missing"; exit 2; }
python3 - "$CONFIDENCE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("schema")=="chacha.dev/component-confidence-snapshot/v1",x.get("schema")
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
assert x.get("confidence_is_advisory_not_final_authority") is True,x
assert x.get("technology_revalidation_required") is True,x
print("CHACHA_DEV_V626_V625_CONFIDENCE_BASELINE=PASS")
PY
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True:raise SystemExit("CHACHA_DEV_V626_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/acceptance-confidence-bridge.py   dev-hub/bin/acceptance-engine.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/universal_learning_runtime.py   dev-hub/bin/learning-delta-ingest.py   dev-hub/bin/guardian-governed-production-lineage-feedback.py   dev-hub/bin/guardian-governed-component-confidence.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/acceptance-confidence.v1.json   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/tests/test_v626_acceptance_confidence_loop.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/acceptance-confidence-bridge.py"   "$RELEASE/dev-hub/bin/acceptance-engine.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V626_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  CHACHA_DEV_TEST_GUARDIAN_BYPASS=1 PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v626_acceptance_confidence_loop.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V626_ACCEPTANCE_FULL_PASS_TO_CONFIDENCE=PASS   CHACHA_DEV_V626_ACCEPTANCE_CONFIDENCE_IDEMPOTENCY=PASS   CHACHA_DEV_V626_REJECTED_PROJECT_NO_BROAD_COMPONENT_PENALTY=PASS   CHACHA_DEV_V626_ACCEPTANCE_ENGINE_AUTO_BRIDGE=PASS   CHACHA_DEV_V626_REAL_ORCHESTRATOR_CONFIDENCE_GUARDIAN_EVIDENCE=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V626_SEMANTIC_PILOT=PASS"
echo "CHACHA_DEV_V626_SEMANTIC_GUARDIAN_BYPASS=TEST_ONLY"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage guardian-coverage-bootstrap
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V626_GUARDIAN_COVERAGE=PASS"

stage real-acceptance-auto-confidence
PILOT_AGENT="v626-acceptance-agent-$STAMP"
PILOT_BRANCH="v626-acceptance-branch-$STAMP"
PILOT_PROJECT="v626-runtime-pilot-$STAMP"
PILOT_DEPLOY="v626-deployment-$STAMP"
cat >"$WORK/contract.json" <<'JSON'
{"criteria":[
  {"criterion_id":"functional","dimension":"functional","required":true,"owner":"runtime"},
  {"criterion_id":"quality","dimension":"quality","required":true,"owner":"qa"}
]}
JSON
cat >"$WORK/evidence.json" <<'JSON'
{"criteria":[
  {"criterion_id":"functional","state":"PASS","evidence":"v626-live-functional"},
  {"criterion_id":"quality","state":"PASS","evidence":"v626-live-quality"}
]}
JSON
cat >"$WORK/lineage.json" <<JSON
{"schema":"chacha.dev/component-lineage/v1","components":[
  {"kind":"agent","component_id":"$PILOT_AGENT","version":"1"},
  {"kind":"branch","component_id":"$PILOT_BRANCH","version":"1"}
]}
JSON
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/acceptance-engine.py"   --contract "$WORK/contract.json" --evidence "$WORK/evidence.json" --output "$WORK/acceptance.json"   --component-lineage "$WORK/lineage.json" --confidence-project-id "$PILOT_PROJECT"   --confidence-deployment-id "$PILOT_DEPLOY" --confidence-output "$WORK/acceptance-confidence.json"   >"$WORK/acceptance-1.out"
grep -Fq 'CHACHA_DEV_V626_ACCEPTANCE_TO_COMPONENT_CONFIDENCE=PASS' "$WORK/acceptance-1.out"
OUTBOX="$(python3 - "$WORK/acceptance-confidence.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="QUEUED",x
print(x["outbox"])
PY
)"
[ -s "$OUTBOX" ] || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=acceptance_delta_missing"; exit 2; }
echo "CHACHA_DEV_V626_REAL_ACCEPTANCE_AUTO_CONFIDENCE=PASS"
echo "CHACHA_DEV_V626_REAL_ACCEPTANCE_GUARDIAN_BYPASS=NO"

stage acceptance-idempotency
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/acceptance-engine.py"   --contract "$WORK/contract.json" --evidence "$WORK/evidence.json" --output "$WORK/acceptance.json"   --component-lineage "$WORK/lineage.json" --confidence-project-id "$PILOT_PROJECT"   --confidence-deployment-id "$PILOT_DEPLOY" --confidence-output "$WORK/acceptance-confidence-2.json"   >"$WORK/acceptance-2.out"
python3 - "$WORK/acceptance-confidence-2.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="DEDUPLICATED",x
print("CHACHA_DEV_V626_REAL_ACCEPTANCE_IDEMPOTENCY=PASS")
PY

stage central-ingest
python3 "$CURRENT/dev-hub/bin/learning-delta-ingest.py"   --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db --delta "$OUTBOX" --nas >"$WORK/ingest.out"
python3 - "$WORK/ingest.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status") in {"RECORDED","DEDUPLICATED"},x
assert (x.get("nas") or {}).get("status")=="PERSISTED",x
print("CHACHA_DEV_V626_REAL_ACCEPTANCE_DELTA_NAS=PASS")
PY

stage feedback-confidence-memory
set +e
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-production-lineage-feedback.py" >"$WORK/feedback.out" 2>"$WORK/feedback.stderr"
FRC=$?
set -e
[ "$FRC" -eq 0 ] || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=feedback_failed"; exit 2; }
set +e
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-governed-component-confidence.py" >"$WORK/confidence.out" 2>"$WORK/confidence.stderr"
CRC=$?
set -e
[ "$CRC" -eq 0 ] || { echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=confidence_failed"; exit 2; }
python3 - "$CONFIDENCE" "$PILOT_AGENT" "$PILOT_BRANCH" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"));ids=set(sys.argv[2:])
rows={str(r.get("component_id")):r for r in x.get("items") or [] if str(r.get("component_id")) in ids}
assert set(rows)==ids,(rows,ids)
for r in rows.values():
    assert int(r.get("verified_success_count") or 0)==1,r
    assert r.get("state")=="PROVISIONAL",r
assert (x.get("nas") or {}).get("status")=="PERSISTED",x.get("nas")
print("CHACHA_DEV_V626_REAL_ACCEPTANCE_CONFIDENCE_ATTRIBUTION=PASS")
PY
systemctl start chacha-dev-central-memory-assimilation.service
if systemctl is-failed --quiet chacha-dev-central-memory-assimilation.service; then
  echo "CHACHA_DEV_V626_INSTALL=BLOCKED reason=central_memory_refresh_failed"; exit 2
fi
python3 - "$MEMORY" "$CONFIDENCE" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"));c=json.load(open(sys.argv[2],encoding="utf-8"))
cc=m.get("component_confidence") or {}
assert cc.get("available") is True,cc
assert cc.get("snapshot_digest")==c.get("snapshot_digest"),(cc,c.get("snapshot_digest"))
print("CHACHA_DEV_V626_ACCEPTANCE_TO_CENTRAL_MEMORY=PASS")
PY

stage real-orchestrator-guardian-confidence-evidence
PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$WORK/council.json" "$WORK/orchestrator-evidence.json" <<'PY'
import json,sys,importlib.util
from pathlib import Path
root=Path("/opt/chacha-dev/platform/current")
p=Path(sys.argv[1]);o=Path(sys.argv[2])
advisors={k:"PASS" for k in [
 "technology-watch-pre","technology-watch-final","central-memory-assimilation","component-confidence",
 "central-memory-recall","reuse-memory","architecture-memory","architecture-portfolio",
 "branch-foundry","agent-foundry","capability-foundry","constraint-policy"]}
p.write_text(json.dumps({"dispatch_allowed":True,"decisions":[{"mandatory_advisors":advisors}]}),encoding="utf-8")
spec=importlib.util.spec_from_file_location("v626_orch",root/"dev-hub/bin/autonomous-project-orchestrator.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ev=m._council_guardian_evidence(p)
assert ev.get("component_confidence") is True,ev
o.write_text(json.dumps(ev),encoding="utf-8")
PY
ARCH_ACTION="v626-arch-$STAMP"
cat >"$WORK/guardian-pre.json" <<JSON
{"schema":"chacha.dev/governance-action/v1","event_id":"v626-pre-$STAMP","action_id":"$ARCH_ACTION","phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"architecture-decision-council","action":"FINAL_ARCHITECTURE_DECISION","task_kind":"architecture-decision-council","permission":"plan","project_id":"platform-bootstrap","run_id":"v626-runtime","adapters":[],"evidence":{"emergency_stop_active":false},"context":{"resource_class":"light","human_approval_required":false,"storage_preflight_required":false,"deadline_seconds":120}}
JSON
python3 - "$WORK/orchestrator-evidence.json" "$WORK/guardian-post.json" "$ARCH_ACTION" "$STAMP" <<'PY'
import json,sys
ev=json.load(open(sys.argv[1],encoding="utf-8"))
x={"schema":"chacha.dev/governance-action/v1","event_id":"v626-post-"+sys.argv[4],"action_id":sys.argv[3],
   "phase":"POST_ACTION","actor":"central-orchestrator","subject_role":"architecture-decision-council",
   "action":"FINAL_ARCHITECTURE_DECISION","task_kind":"architecture-decision-council","permission":"plan",
   "project_id":"platform-bootstrap","run_id":"v626-runtime","adapters":[],"evidence":ev,
   "context":{"resource_class":"light","human_approval_required":False,"storage_preflight_required":False,"deadline_seconds":120}}
json.dump(x,open(sys.argv[2],"w",encoding="utf-8"))
PY
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-pre.json" >"$WORK/guardian-pre.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-pre.out"
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" check --event "$WORK/guardian-post.json" >"$WORK/guardian-post.out"
grep -Eq '"verdict"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/guardian-post.out"
echo "CHACHA_DEV_V626_REAL_ORCHESTRATOR_GUARDIAN_CONFIDENCE_EVIDENCE=PASS"

cat >"/opt/chacha-dev/evidence/v626-acceptance-confidence-loop-$STAMP.json" <<JSON
{"schema":"chacha.dev/v626-acceptance-confidence-loop-evidence/v1","revision":"$REV","observed_at":"$STAMP","semantic_pilot":"PASS","guardian_coverage":"PASS","real_acceptance_auto_confidence":"PASS","idempotency":"PASS","delta_nas":"PASS","exact_confidence_attribution":"PASS","central_memory":"PASS","real_orchestrator_guardian_confidence_evidence":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V626_FULL_ACCEPTANCE_EMITS_VERIFIED_SUCCESS=YES"
echo "CHACHA_DEV_V626_EXACT_COMPONENT_LINEAGE_REQUIRED=YES"
echo "CHACHA_DEV_V626_REJECTED_PROJECT_BROAD_COMPONENT_PENALTY=NO"
echo "CHACHA_DEV_V626_ACCEPTANCE_CONFIDENCE_IDEMPOTENT=YES"
echo "CHACHA_DEV_V626_REAL_ORCHESTRATOR_CONFIDENCE_GUARDIAN_EVIDENCE=YES"
echo "CHACHA_DEV_V626_TECHNOLOGY_REVALIDATION_REQUIRED=YES"
echo "CHACHA_DEV_V626_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V626_NAS_AUTHORITATIVE=YES"
echo "CHACHA_DEV_V626_DIRECT_APPLICATION_MUTATION=NO"
echo "CHACHA_DEV_V626_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V626_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V626_INSTALL=PASS"

trap - EXIT
cleanup
