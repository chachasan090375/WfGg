#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V720_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V720_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
RUNTIME="/opt/chacha-dev/runtime"
EVIDENCE="/opt/chacha-dev/evidence"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v720.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
PURGE_COMMITTED=0
TIMER="chacha-dev-intendant-hygiene.timer"
TIMER_WAS_ACTIVE=0
TIMER_WAS_ENABLED=0
TIMER_PAUSED=0
DEPLOY_LOCK="$RUNTIME/control/platform-deploy.lock"
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V720_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
assert_current(){
  local actual
  actual="$(readlink -f "$CURRENT" 2>/dev/null || true)"
  [ "$actual" = "$RELEASE" ] || { echo "CHACHA_DEV_V720_CURRENT_DRIFT expected=$RELEASE actual=$actual"; return 42; }
  [ "$(cat "$RELEASE/.revision" 2>/dev/null || true)" = "$REV" ] || return 43
  [ -f "$RELEASE/dev-hub/bin/human-interface-gateway.py" ] || return 44
  [ -f "$RELEASE/dev-hub/config/human-interface-gateway.v1.json" ] || return 45
}
restore_timer(){
  if [ "$TIMER_PAUSED" -eq 1 ]; then
    if [ "$TIMER_WAS_ENABLED" -eq 1 ]; then systemctl enable "$TIMER" >/dev/null 2>&1 || true; fi
    if [ "$TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start "$TIMER" >/dev/null 2>&1 || true; fi
    TIMER_PAUSED=0
  fi
}
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V720_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -320 "$f" || true
    done
    if [ "$PURGE_COMMITTED" -eq 0 ] && [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      actual="$(readlink -f "$CURRENT" 2>/dev/null || true)"
      if [ "$actual" = "$RELEASE" ] || [ -z "$actual" ]; then
        ln -sfn "$PREVIOUS" "$CURRENT"
        rm -rf "$RELEASE" 2>/dev/null || true
        echo "CHACHA_DEV_V720_RUNTIME_ROLLBACK=PASS"
      else
        echo "CHACHA_DEV_V720_RUNTIME_ROLLBACK=SKIPPED_EXTERNAL_CURRENT actual=$actual"
      fi
    elif [ "$PURGE_COMMITTED" -eq 1 ]; then
      echo "CHACHA_DEV_V720_RUNTIME_ROLLBACK=SKIPPED_COMMITTED_RETIREMENT"
    fi
    restore_timer
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V720_INSTALL=BLOCKED reason=root_required"; exit 2; }
mkdir -p "$RUNTIME/control"
exec 9>"$DEPLOY_LOCK"
flock -n 9 || { echo "CHACHA_DEV_V720_INSTALL=BLOCKED reason=platform_deploy_lock_busy"; exit 73; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V720_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V720_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v710-acquired-baseline
python3 - "$PREVIOUS" <<'PY'
import json,pathlib,re,sys
root=pathlib.Path(sys.argv[1])
rev=(root/".revision").read_text().strip()
assert rev=="04cb15a998dda8996be2c7cfb6442d4a16d1529d",rev
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text()
m=re.search(r'"version"\s*:\s*"([^"]+)"',src)
assert m and m.group(1)=="7.1.0",(m.group(1) if m else None)
matches=[]
for p in sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v710-intendant-hygiene-cycle-*.json")):
    try:x=json.loads(p.read_text())
    except Exception:continue
    if x.get("revision")==rev and x.get("platform_version")=="7.1.0":matches.append(x)
assert matches,("V710_ACQUIRED_EVIDENCE_MISSING",rev)
x=matches[-1]
assert x.get("single_timer") is True,x
assert x.get("physical_executor")=="central-orchestrator",x
assert x.get("intendant_direct_mutation") is False,x
print("CHACHA_DEV_V720_V710_BASELINE=PASS")
PY

if systemctl is-enabled --quiet "$TIMER" 2>/dev/null; then TIMER_WAS_ENABLED=1; fi
if systemctl is-active --quiet "$TIMER" 2>/dev/null; then
  TIMER_WAS_ACTIVE=1
  systemctl stop "$TIMER"
  TIMER_PAUSED=1
fi
if systemctl is-active --quiet chacha-dev-intendant-hygiene.service 2>/dev/null; then
  restore_timer
  echo "CHACHA_DEV_V720_INSTALL=BLOCKED reason=hygiene_service_active"
  exit 74
fi

stage source
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"; tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
for p in   dev-hub/bin/install-v720-human-interface-gateway.sh   dev-hub/bin/build-v7-runtime-release.py   dev-hub/bin/human-interface-gateway.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/project-control.py   dev-hub/bin/emergency-stop-controller.py   dev-hub/bin/intendant-hygiene-cycle.py   dev-hub/bin/intendant-platform-consolidator.py   dev-hub/bin/central-platform-hygiene-executor.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/bin/technology-watch-service.py   dev-hub/config/human-interface-gateway.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/intendant-hygiene-cycle.v1.json   dev-hub/config/platform-consolidation.v1.json   dev-hub/tests/test_v720_human_interface_gateway.py   dev-hub/tests/test_v710_intendant_hygiene_cycle.py   dev-hub/tests/test_v700_consolidated_platform_baseline.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V720_INSTALL=BLOCKED reason=missing:$p"; exit 2; }
done

stage local-qualification
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v720_human_interface_gateway.py) >"$WORK/v720.out" 2>"$WORK/v720.err"
grep -Fq 'CHACHA_DEV_V720_HUMAN_INTERFACE_GATEWAY=PASS' "$WORK/v720.out"
grep -Fq 'CHACHA_DEV_V720_GO_CONTINUES_PRIOR_BRAIN_RECEIPT=PASS' "$WORK/v720.out"
grep -Fq 'CHACHA_DEV_V720_BRAIN_UNAVAILABLE_FAIL_CLOSED=PASS' "$WORK/v720.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v710_intendant_hygiene_cycle.py) >"$WORK/v710.out" 2>"$WORK/v710.err"
grep -Fq 'CHACHA_DEV_V710_DYNAMIC_TWO_ROLLBACK_RETENTION=PASS' "$WORK/v710.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v700_consolidated_platform_baseline.py) >"$WORK/v700.out" 2>"$WORK/v700.err"
grep -Fq 'CHACHA_DEV_V700_CANONICAL_BASELINE=PASS' "$WORK/v700.out"
for t in   dev-hub/tests/test_v660_independent_accuracy_attestation.py   dev-hub/tests/test_v661_real_world_evidence_isolated_candidate.py   dev-hub/tests/test_v663_runtime_surface_instrumentation_readiness.py   dev-hub/tests/test_v664_real_instrumented_project_acceptance_council.py; do
  (cd "$SRC"; PYTHONPATH=dev-hub/bin python3 "$t") >>"$WORK/regressions.out" 2>>"$WORK/regressions.err"
done
echo "CHACHA_DEV_V720_LOCAL_QUALIFICATION=PASS"

stage exact-sha-assurance
python3 - "$REV" <<'PY'
import json,sys,urllib.parse,urllib.request
rev=sys.argv[1];q=urllib.parse.urlencode({"head_sha":rev,"per_page":50})
req=urllib.request.Request("https://api.github.com/repos/chachasan090375/WfGg/actions/runs?"+q,
 headers={"User-Agent":"ChaCha-DEV-V720-Installer/1.0","Accept":"application/vnd.github+json"})
with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read().decode())
need={
 "ChaCha DEV Sentinel technical assurance",
 "ChaCha DEV V7 platform qualification",
 "ChaCha DEV V7.2 Human Interface Gateway qualification"
}
rows=x.get("workflow_runs") or []
for name in need:
 assert any(w.get("name")==name and w.get("head_sha")==rev and w.get("status")=="completed" and w.get("conclusion")=="success" for w in rows),(name,[(w.get("name"),w.get("status"),w.get("conclusion")) for w in rows])
print("CHACHA_DEV_V720_EXACT_SHA_ASSURANCE=PASS")
PY

stage build-compiled-release
mkdir -p "$RELEASE"
python3 "$SRC/dev-hub/bin/build-v7-runtime-release.py"   --source-root "$SRC" --output-root "$RELEASE" --manifest "$WORK/compiled-manifest.json"   >"$WORK/compile.out" 2>"$WORK/compile.err"
printf '%s\n' "$REV" >"$RELEASE/.revision"
grep -Fq 'CHACHA_DEV_V7_COMPILED_RUNTIME_RELEASE=PASS' "$WORK/compile.out"
grep -Fq '"version":"7.2.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
[ -f "$RELEASE/dev-hub/bin/human-interface-gateway.py" ]
[ -f "$RELEASE/dev-hub/config/human-interface-gateway.v1.json" ]
echo "CHACHA_DEV_V720_COMPILED_RELEASE=PASS"

stage activate
ln -sfn "$RELEASE" "$CURRENT"; ACTIVATED=1
assert_current
echo "CHACHA_DEV_V720_RELEASE_ACTIVATED=PASS"

stage guardian-and-platform-health
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$RELEASE"   --manifest "$RELEASE/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$RELEASE/dev-hub/bin/guardian-client.py"   --output "$RUNTIME/guardian/coverage-latest.json" >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/technology-watch-service.py" --repo-root "$RELEASE" status >"$WORK/watch.out"
grep -Fq 'CHACHA_TECHNOLOGY_WATCH_STATUS=FRESH' "$WORK/watch.out"
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
echo "CHACHA_DEV_V720_PLATFORM_HEALTH=PASS"

stage real-status-pilot
REQ_STATUS="v720-real-status-$STAMP"
STATUS_OUT="$WORK/status-response.json"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/human-interface-gateway.py"   --repo-root "$RELEASE" --runtime-root "$RUNTIME"   --policy "$RELEASE/dev-hub/config/human-interface-gateway.v1.json"   --text "Allo" --request-id "$REQ_STATUS" --project chacha-dev-platform   --output "$STATUS_OUT" >"$WORK/status.out" 2>"$WORK/status.err"
python3 - "$STATUS_OUT" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["command"]=="STATUS" and x["status"]=="OK",x
assert x["authority"]=="central-orchestrator",x
assert x["status_source"]=="canonical-platform-runtime",x
assert x["platform_revision"]==sys.argv[2],x
assert x["platform_version"]=="7.2.0",x
assert x["interface_direct_technical_decision"] is False,x
print("CHACHA_DEV_V720_REAL_STATUS=PASS")
PY

stage real-instruction-pilot
REQ_INSTRUCTION="v720-real-instruction-$STAMP"
INSTRUCTION_OUT="$WORK/instruction-response.json"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/human-interface-gateway.py"   --repo-root "$RELEASE" --runtime-root "$RUNTIME"   --policy "$RELEASE/dev-hub/config/human-interface-gateway.v1.json"   --text "Préparer une analyse non destructive de la passerelle d interface ChaCha DEV, sans exécution, sans mutation production et sans dépense externe."   --request-id "$REQ_INSTRUCTION" --project chacha-dev-platform   --output "$INSTRUCTION_OUT" >"$WORK/instruction.out" 2>"$WORK/instruction.err"
python3 - "$INSTRUCTION_OUT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["command"]=="INSTRUCTION",x
assert x["status"] in {"PLAN_READY","BLOCKED"},x
assert x["authority"]=="central-orchestrator",x
assert x["brain_decision_obtained"] is True,x
assert x["interface_direct_technical_decision"] is False,x
assert x["interface_direct_mutation"] is False,x
assert x.get("brain_receipt"),x
assert x.get("evidence_refs"),x
assert float(x.get("automatic_external_spend_eur") or 0)==0,x
print("CHACHA_DEV_V720_REAL_CENTRAL_ORCHESTRATION=PASS")
PY

stage real-go-pilot
REQ_GO="v720-real-go-$STAMP"
GO_OUT="$WORK/go-response.json"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/human-interface-gateway.py"   --repo-root "$RELEASE" --runtime-root "$RUNTIME"   --policy "$RELEASE/dev-hub/config/human-interface-gateway.v1.json"   --text "Go" --request-id "$REQ_GO" --output "$GO_OUT" >"$WORK/go.out" 2>"$WORK/go.err"
python3 - "$GO_OUT" "$REQ_INSTRUCTION" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["command"]=="CONTINUE" and x["status"]=="CONTINUE_ALLOWED",x
assert x["authority"]=="central-orchestrator-prior-receipt",x
assert x["continuation_of_request_id"]==sys.argv[2],x
assert x["new_technical_decision_created"] is False,x
assert x["interface_direct_technical_decision"] is False,x
print("CHACHA_DEV_V720_REAL_GO_CONTINUATION=PASS")
PY

stage audit-chain
python3 - "$RUNTIME/human-interface/audit.jsonl" <<'PY'
import hashlib,json,sys,pathlib
p=pathlib.Path(sys.argv[1]);assert p.is_file(),p
prev="GENESIS";seq=1
for line in p.read_text(encoding="utf-8").splitlines():
    if not line.strip():continue
    x=json.loads(line)
    assert x["seq"]==seq,(seq,x)
    assert x["previous_event_digest"]==prev,(seq,x)
    payload={k:v for k,v in x.items() if k!="event_digest"}
    actual="sha256:"+hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    assert actual==x["event_digest"],(seq,actual,x["event_digest"])
    prev=actual;seq+=1
print("CHACHA_DEV_V720_AUDIT_CHAIN=PASS")
PY

stage governed-retention
assert_current
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/intendant-hygiene-cycle.py"   --repo-root "$RELEASE" --runtime-root "$RUNTIME" --platform-root "$BASE"   --policy "$RELEASE/dev-hub/config/intendant-hygiene-cycle.v1.json"   --consolidation-policy "$RELEASE/dev-hub/config/platform-consolidation.v1.json"   --guardian-client "$RELEASE/dev-hub/bin/guardian-client.py"   --guardian-policy "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json"   --guardian-coverage "$RUNTIME/guardian/coverage-latest.json"   --council "$RELEASE/dev-hub/bin/architecture-council-platform-consolidation-v7.py"   --consolidator "$RELEASE/dev-hub/bin/intendant-platform-consolidator.py"   --hygiene-executor "$RELEASE/dev-hub/bin/central-platform-hygiene-executor.py"   --force-cycle WEEKLY_DRY_RUN >"$WORK/retention.out" 2>"$WORK/retention.err"
grep -Fq 'CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=PASS' "$WORK/retention.out"
python3 - "$RUNTIME/intendant/hygiene-latest.json" "$REV" <<'PY'
import json,pathlib,sys
x=json.load(open(sys.argv[1]))
assert x["platform_revision"]==sys.argv[2],x
w=next(r for r in x["results"] if r["cycle"]=="WEEKLY_DRY_RUN")
assert w["status"] in {"PASS","WARNING"},w
dry=next(a for a in w["actions"] if a["action"]=="RELEASE_RETIREMENT_DRY_RUN")
ret=int(dry.get("retire_count") or 0)
if ret>0:
    apply=next(a for a in w["actions"] if a["action"]=="SAFE_RELEASE_RETIREMENT_APPLY")
    assert apply["executor"]=="central-orchestrator",apply
    assert apply["guardian_post_action"] is True,apply
rels=[p for p in pathlib.Path("/opt/chacha-dev/platform/releases").iterdir() if p.is_dir()]
assert len(rels)==3,len(rels)
revs=[(p/".revision").read_text().strip() for p in rels]
assert len(set(revs))==3,revs
assert sys.argv[2] in revs,revs
print("CHACHA_DEV_V720_RETENTION=PASS")
PY
PURGE_COMMITTED=1

stage evidence
assert_current
mkdir -p "$EVIDENCE"
python3 - "$EVIDENCE/v720-human-interface-gateway-$STAMP.json" "$REV" "$STAMP" "$STATUS_OUT" "$INSTRUCTION_OUT" "$GO_OUT" <<'PY'
import json,pathlib,sys
status=json.load(open(sys.argv[4]));instruction=json.load(open(sys.argv[5]));go=json.load(open(sys.argv[6]))
rels=[p for p in pathlib.Path("/opt/chacha-dev/platform/releases").iterdir() if p.is_dir()]
out={
 "schema":"chacha.dev/v720-human-interface-gateway-evidence/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],"platform_version":"7.2.0",
 "component":"human-interface-gateway","component_is_agent":False,
 "decision_authority":"central-orchestrator",
 "status_pilot":{"status":status["status"],"authority":status["authority"],"source":status.get("status_source")},
 "instruction_pilot":{"status":instruction["status"],"authority":instruction["authority"],
   "brain_decision_obtained":instruction["brain_decision_obtained"],"next_action":instruction["next_action"],
   "evidence_refs":instruction["evidence_refs"]},
 "go_pilot":{"status":go["status"],"authority":go["authority"],
   "continuation_of_request_id":go.get("continuation_of_request_id"),
   "new_technical_decision_created":go.get("new_technical_decision_created")},
 "stop_production_pilot":"NOT_EXECUTED_SAFETY",
 "stop_sandbox_tested":True,
 "interface_direct_technical_decision":False,"interface_direct_mutation":False,
 "brain_unavailable_fail_closed":True,"audit_hash_chain":True,
 "guardian_all_hooks_active":True,
 "physical_release_count":len(rels),"distinct_release_revisions":len(set((p/".revision").read_text().strip() for p in rels)),
 "canonical_observation_bus_rewrite":False,"automatic_external_spend_eur":0
}
open(sys.argv[1],"w").write(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
PY

stage resume-timer
if [ "$TIMER_WAS_ENABLED" -eq 1 ]; then systemctl enable "$TIMER" >/dev/null; fi
if [ "$TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start "$TIMER"; fi
TIMER_PAUSED=0
systemctl is-active --quiet "$TIMER"
assert_current

echo "CHACHA_DEV_V720_INSTALL=PASS"
echo "CHACHA_DEV_V720_HUMAN_INTERFACE_GATEWAY=PASS"
echo "CHACHA_DEV_V720_REAL_STATUS=PASS"
echo "CHACHA_DEV_V720_REAL_CENTRAL_ORCHESTRATION=PASS"
echo "CHACHA_DEV_V720_REAL_GO_CONTINUATION=PASS"
echo "CHACHA_DEV_V720_STOP_PRODUCTION_PILOT=NOT_EXECUTED_SAFETY"
echo "CHACHA_DEV_V720_INTERFACE_TECHNICAL_DECISION_AUTHORITY=NO"
echo "CHACHA_DEV_V720_INTERFACE_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V720_GUARDIAN_COVERAGE=PASS"
echo "CHACHA_DEV_V720_AUTOMATIC_EXTERNAL_SPEND_EUR=0"

trap - EXIT
cleanup
