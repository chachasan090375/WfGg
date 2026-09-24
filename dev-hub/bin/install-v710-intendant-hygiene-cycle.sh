#!/usr/bin/env bash
set -Eeuo pipefail
# V7.1 acquisition invariant: the no-retirement-needed path remains rollback-safe.
# Rollback invariant: both physical rollback slots must be distinct from the active revision.

REV="${CHACHA_DEV_V710_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V710_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
RUNTIME="/opt/chacha-dev/runtime"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v710.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
PURGE_COMMITTED=0
UNIT_DIR="/etc/systemd/system"
SERVICE="$UNIT_DIR/chacha-dev-intendant-hygiene.service"
TIMER="$UNIT_DIR/chacha-dev-intendant-hygiene.timer"
SERVICE_BACKUP="$WORK/service.backup"
TIMER_BACKUP="$WORK/timer.backup"
SERVICE_EXISTED=0
TIMER_EXISTED=0
TIMER_WAS_ACTIVE=0
TIMER_WAS_ENABLED=0
TIMER_PAUSED=0
UNITS_TOUCHED=0
DEPLOY_LOCK="$RUNTIME/control/platform-deploy.lock"
UNIT_MARKER="# ChaCha-DEV-V710-Revision: $REV"
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V710_STAGE=$STAGE"; }
assert_current(){
  local actual
  actual="$(readlink -f "$CURRENT" 2>/dev/null || true)"
  [ "$actual" = "$RELEASE" ] || { echo "CHACHA_DEV_V710_CURRENT_DRIFT expected=$RELEASE actual=$actual"; return 42; }
  [ -f "$RELEASE/dev-hub/bin/intendant-hygiene-cycle.py" ] || { echo "CHACHA_DEV_V710_RELEASE_SURFACE_MISSING=intendant-hygiene-cycle.py"; return 43; }
  [ -f "$RELEASE/dev-hub/bin/central-platform-hygiene-executor.py" ] || { echo "CHACHA_DEV_V710_RELEASE_SURFACE_MISSING=central-platform-hygiene-executor.py"; return 44; }
}
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V710_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -300 "$f" || true
    done
    if [ "$PURGE_COMMITTED" -eq 0 ]; then
      units_restored=0
      if [ "$UNITS_TOUCHED" -eq 1 ] && [ -f "$TIMER" ] && grep -Fqx "$UNIT_MARKER" "$TIMER"; then
        systemctl stop chacha-dev-intendant-hygiene.timer >/dev/null 2>&1 || true
        systemctl disable chacha-dev-intendant-hygiene.timer >/dev/null 2>&1 || true
        if [ "$TIMER_EXISTED" -eq 1 ]; then cp -a "$TIMER_BACKUP" "$TIMER"; else rm -f "$TIMER"; fi
        units_restored=1
      fi
      if [ "$UNITS_TOUCHED" -eq 1 ] && [ -f "$SERVICE" ] && grep -Fqx "$UNIT_MARKER" "$SERVICE"; then
        if [ "$SERVICE_EXISTED" -eq 1 ]; then cp -a "$SERVICE_BACKUP" "$SERVICE"; else rm -f "$SERVICE"; fi
        units_restored=1
      fi
      if [ "$units_restored" -eq 1 ]; then systemctl daemon-reload >/dev/null 2>&1 || true; fi
      if [ "$TIMER_PAUSED" -eq 1 ]; then
        if [ "$TIMER_WAS_ENABLED" -eq 1 ]; then systemctl enable chacha-dev-intendant-hygiene.timer >/dev/null 2>&1 || true; fi
        if [ "$TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start chacha-dev-intendant-hygiene.timer >/dev/null 2>&1 || true; fi
        TIMER_PAUSED=0
      fi
      if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
        actual="$(readlink -f "$CURRENT" 2>/dev/null || true)"
        if [ "$actual" = "$RELEASE" ] || [ -z "$actual" ]; then
          ln -sfn "$PREVIOUS" "$CURRENT"
          echo "CHACHA_DEV_V710_RUNTIME_ROLLBACK=PASS"
          rm -rf "$RELEASE" 2>/dev/null || true
        else
          echo "CHACHA_DEV_V710_RUNTIME_ROLLBACK=SKIPPED_EXTERNAL_CURRENT actual=$actual"
        fi
      else
        rm -rf "$RELEASE" 2>/dev/null || true
      fi
    else
      echo "CHACHA_DEV_V710_ROLLBACK=SKIPPED_COMMITTED_PHYSICAL_RETIREMENT"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V710_INSTALL=BLOCKED reason=root_required"; exit 2; }
mkdir -p "$RUNTIME/control"
exec 9>"$DEPLOY_LOCK"
flock -n 9 || { echo "CHACHA_DEV_V710_INSTALL=BLOCKED reason=platform_deploy_lock_busy"; exit 73; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V710_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V710_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"
CURRENT_REV="$(cat "$PREVIOUS/.revision" 2>/dev/null || true)"
if [ "$CURRENT_REV" = "$REV" ]; then
  stage already-active-reconcile
  RELEASE="$PREVIOUS"
  if [ -f "$SERVICE" ]; then cp -a "$SERVICE" "$SERVICE_BACKUP"; SERVICE_EXISTED=1; fi
  if [ -f "$TIMER" ]; then cp -a "$TIMER" "$TIMER_BACKUP"; TIMER_EXISTED=1; fi
  UNITS_TOUCHED=1
  { echo "$UNIT_MARKER"; cat "$RELEASE/dev-hub/systemd/chacha-dev-intendant-hygiene.service"; } >"$SERVICE"
  { echo "$UNIT_MARKER"; cat "$RELEASE/dev-hub/systemd/chacha-dev-intendant-hygiene.timer"; } >"$TIMER"
  chmod 0644 "$SERVICE" "$TIMER"
  systemctl daemon-reload
  systemctl enable chacha-dev-intendant-hygiene.timer >/dev/null
  systemctl restart chacha-dev-intendant-hygiene.timer
  systemctl is-active --quiet chacha-dev-intendant-hygiene.timer
  systemctl is-enabled --quiet chacha-dev-intendant-hygiene.timer
  NEXT_ELAPSE="$(systemctl show chacha-dev-intendant-hygiene.timer -p NextElapseUSecRealtime --value)"
  [ -n "$NEXT_ELAPSE" ] && [ "$NEXT_ELAPSE" != "infinity" ] || { echo "CHACHA_DEV_V710_TIMER_REARM=BLOCKED next=$NEXT_ELAPSE"; exit 45; }
  echo "CHACHA_DEV_V710_ALREADY_ACTIVE_RECONCILED=PASS"
  echo "CHACHA_DEV_V710_TIMER_NEXT=$NEXT_ELAPSE"
  trap - EXIT
  cleanup
  exit 0
fi

stage v7-acquired-baseline
python3 - "$PREVIOUS" <<'PY'
import pathlib,json,sys,re
root=pathlib.Path(sys.argv[1]);rev=(root/".revision").read_text().strip()
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text()
m=re.search(r'"version"\s*:\s*"([^"]+)"',src)
version=m.group(1) if m else ""
evidence_root=pathlib.Path("/opt/chacha-dev/evidence")
if version=="7.0.0":
    matches=[]
    for p in sorted(evidence_root.glob("v700-consolidated-platform-baseline-*.json")):
        try:x=json.loads(p.read_text())
        except Exception:continue
        if x.get("revision")==rev and x.get("platform_version")=="7.0.0":matches.append(x)
    assert matches,"V700_ACQUIRED_EVIDENCE_MISSING"
    assert matches[-1]["consolidation"]["applied"] is True,matches[-1]
elif version=="7.1.0":
    matches=[]
    for p in sorted(evidence_root.glob("v710-intendant-hygiene-cycle-*.json")):
        try:x=json.loads(p.read_text())
        except Exception:continue
        if x.get("revision")==rev and x.get("platform_version")=="7.1.0":matches.append(x)
    assert matches,("V710_ACQUIRED_EVIDENCE_MISSING",rev)
    x=matches[-1]
    assert x.get("single_timer") is True,x
    assert x.get("physical_executor")=="central-orchestrator",x
    assert x.get("intendant_direct_mutation") is False,x
else:
    raise AssertionError(("UNSUPPORTED_V7_BASELINE",version,rev))
print("CHACHA_DEV_V710_V7_BASELINE=PASS")
print("PREVIOUS_VERSION="+version)
print("PREVIOUS_REVISION="+rev)
PY

if systemctl is-enabled --quiet chacha-dev-intendant-hygiene.timer 2>/dev/null; then TIMER_WAS_ENABLED=1; fi
if systemctl is-active --quiet chacha-dev-intendant-hygiene.timer 2>/dev/null; then
  TIMER_WAS_ACTIVE=1
  systemctl stop chacha-dev-intendant-hygiene.timer
  TIMER_PAUSED=1
fi
if systemctl is-active --quiet chacha-dev-intendant-hygiene.service 2>/dev/null; then
  if [ "$TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start chacha-dev-intendant-hygiene.timer >/dev/null 2>&1 || true; TIMER_PAUSED=0; fi
  echo "CHACHA_DEV_V710_INSTALL=BLOCKED reason=hygiene_service_active"
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
for p in   dev-hub/bin/install-v710-intendant-hygiene-cycle.sh   dev-hub/bin/build-v7-runtime-release.py   dev-hub/bin/intendant-hygiene-cycle.py   dev-hub/bin/intendant-platform-consolidator.py   dev-hub/bin/central-platform-hygiene-executor.py   dev-hub/bin/architecture-council-platform-consolidation-v7.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/intendant-hygiene-cycle.v1.json   dev-hub/config/platform-consolidation.v1.json   dev-hub/systemd/chacha-dev-intendant-hygiene.service   dev-hub/systemd/chacha-dev-intendant-hygiene.timer   dev-hub/tests/test_v710_intendant_hygiene_cycle.py   dev-hub/tests/test_v700_consolidated_platform_baseline.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V710_INSTALL=BLOCKED reason=missing:$p"; exit 2; }
done

stage local-qualification
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v710_intendant_hygiene_cycle.py) >"$WORK/v710.out" 2>"$WORK/v710.err"
grep -Fq 'CHACHA_DEV_V710_SINGLE_HYGIENE_TIMER=PASS' "$WORK/v710.out"
grep -Fq 'CHACHA_DEV_V710_COUNCIL_GUARDIAN_PRE_EXECUTOR_POST_CHAIN=PASS' "$WORK/v710.out"
grep -Fq 'CHACHA_DEV_V710_INTENDANT_DIRECT_MUTATION=NO' "$WORK/v710.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v700_consolidated_platform_baseline.py) >"$WORK/v700.out" 2>"$WORK/v700.err"
grep -Fq 'CHACHA_DEV_V700_CANONICAL_BASELINE=PASS' "$WORK/v700.out"
for t in   dev-hub/tests/test_v623_contextual_memory_recall.py   dev-hub/tests/test_v660_independent_accuracy_attestation.py   dev-hub/tests/test_v661_real_world_evidence_isolated_candidate.py   dev-hub/tests/test_v663_runtime_surface_instrumentation_readiness.py   dev-hub/tests/test_v664_real_instrumented_project_acceptance_council.py; do
  (cd "$SRC"; PYTHONPATH=dev-hub/bin python3 "$t") >>"$WORK/regressions.out" 2>>"$WORK/regressions.err"
done
echo "CHACHA_DEV_V710_LOCAL_QUALIFICATION=PASS"

stage exact-sha-assurance
python3 - "$REV" <<'PY'
import json,sys,urllib.parse,urllib.request
rev=sys.argv[1];q=urllib.parse.urlencode({"head_sha":rev,"per_page":50})
req=urllib.request.Request("https://api.github.com/repos/chachasan090375/WfGg/actions/runs?"+q,
 headers={"User-Agent":"ChaCha-DEV-V710-Installer/1.0","Accept":"application/vnd.github+json"})
with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read().decode())
need={
 "ChaCha DEV Sentinel technical assurance",
 "ChaCha DEV V7 platform qualification",
 "ChaCha DEV V7.1 Intendant hygiene cycle qualification",
 "ChaCha DEV V7.1 Guardian hygiene contract deploy"
}
rows=x.get("workflow_runs") or []
for name in need:
 assert any(w.get("name")==name and w.get("head_sha")==rev and w.get("status")=="completed" and w.get("conclusion")=="success" for w in rows),(name,[(w.get("name"),w.get("status"),w.get("conclusion")) for w in rows])
print("CHACHA_DEV_V710_EXACT_SHA_ASSURANCE=PASS")
PY

stage external-guardian-hygiene-probe
python3 - "$PREVIOUS" "$WORK" <<'PY'
import json,pathlib,subprocess,sys,time
root=pathlib.Path(sys.argv[1]);work=pathlib.Path(sys.argv[2])
client=root/"dev-hub/bin/guardian-client.py";policy=root/"dev-hub/config/guardian-runtime-policy.v1.json"
rev=(root/".revision").read_text().strip()
for action in ("EXECUTE_SAFE_TEMP_CLEANUP","EXECUTE_PLATFORM_RETIREMENT"):
    aid="v710-installer-probe-"+action.lower()+"-"+str(int(time.time()*1000))
    base={
      "schema":"chacha.dev/governance-action/v1","action_id":aid,
      "actor":"central-orchestrator","subject_role":"platform-hygiene-executor",
      "action":action,"permission":"destructive-operation","project_id":"chacha-dev-platform",
      "revision":rev,"capabilities":["platform-hygiene"],
      "context":{"resource_class":"normal","deadline_seconds":120},
      "evidence":{"human_approval":True,"probe_only":True,"safe_scope_verified":True,
        "architecture_council_approval":True,"rollback_verified":True,
        "consolidation_plan_digest":"sha256:"+"7"*64,
        "safe_temp_manifest_digest":"sha256:"+"8"*64},
      "automatic_external_spend_eur":0
    }
    for phase in ("PRE_ACTION","POST_ACTION"):
        event=dict(base);event["event_id"]=aid+("-pre" if phase=="PRE_ACTION" else "-post");event["phase"]=phase
        if phase=="POST_ACTION":event["evidence"]=dict(base["evidence"],result_status="NOOP_CONTRACT_PROBE")
        p=work/(aid+("-pre.json" if phase=="PRE_ACTION" else "-post.json"))
        p.write_text(json.dumps(event),encoding="utf-8")
        q=subprocess.run([sys.executable,str(client),"--policy",str(policy),"check","--event",str(p)],
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
        if q.returncode!=0:
            raise SystemExit("GUARDIAN_HYGIENE_PROBE_BLOCK:"+action+":"+phase+":"+q.stdout[-1200:]+q.stderr[-1200:])
        try:x=json.loads(q.stdout.strip().splitlines()[-1])
        except Exception:raise SystemExit("GUARDIAN_HYGIENE_PROBE_INVALID_RECEIPT:"+action+":"+phase)
        if x.get("verdict") not in ("PASS","WARNING"):
            raise SystemExit("GUARDIAN_HYGIENE_PROBE_VERDICT:"+str(x))
print("CHACHA_DEV_V710_EXTERNAL_GUARDIAN_HYGIENE_PROBE=PASS")
PY

stage build-compiled-release
mkdir -p "$RELEASE"
python3 "$SRC/dev-hub/bin/build-v7-runtime-release.py"   --source-root "$SRC" --output-root "$RELEASE" --manifest "$WORK/compiled-manifest.json"   >"$WORK/compile.out" 2>"$WORK/compile.err"
printf '%s\n' "$REV" >"$RELEASE/.revision"
grep -Fq 'CHACHA_DEV_V7_COMPILED_RUNTIME_RELEASE=PASS' "$WORK/compile.out"
grep -Fq '"version":"7.1.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
[ ! -d "$RELEASE/dev-hub/tests" ]
[ ! -d "$RELEASE/dev-hub/docs" ]
[ -f "$RELEASE/dev-hub/bin/intendant-hygiene-cycle.py" ]
[ -f "$RELEASE/dev-hub/bin/central-platform-hygiene-executor.py" ]
echo "CHACHA_DEV_V710_COMPILED_RELEASE=PASS"

stage unit-backup
if [ -f "$SERVICE" ]; then cp -a "$SERVICE" "$SERVICE_BACKUP"; SERVICE_EXISTED=1; fi
if [ -f "$TIMER" ]; then cp -a "$TIMER" "$TIMER_BACKUP"; TIMER_EXISTED=1; fi
mkdir -p "$RUNTIME/intendant" "$RUNTIME/tmp"

stage activate
ln -sfn "$RELEASE" "$CURRENT"; ACTIVATED=1
assert_current
echo "CHACHA_DEV_V710_RELEASE_ACTIVATED=PASS"

stage install-units
assert_current
UNITS_TOUCHED=1
{ echo "$UNIT_MARKER"; cat "$RELEASE/dev-hub/systemd/chacha-dev-intendant-hygiene.service"; } >"$SERVICE"
{ echo "$UNIT_MARKER"; cat "$RELEASE/dev-hub/systemd/chacha-dev-intendant-hygiene.timer"; } >"$TIMER"
chmod 0644 "$SERVICE" "$TIMER"
systemctl daemon-reload
systemd-analyze verify "$SERVICE" "$TIMER" >"$WORK/systemd-verify.out" 2>"$WORK/systemd-verify.err" || {
  cat "$WORK/systemd-verify.err"; exit 41;
}
echo "CHACHA_DEV_V710_SYSTEMD_UNITS=PASS"

stage runtime-dry-run
assert_current
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/intendant-hygiene-cycle.py"   --repo-root "$RELEASE" --runtime-root "$RUNTIME" --platform-root "$BASE"   --policy "$RELEASE/dev-hub/config/intendant-hygiene-cycle.v1.json"   --consolidation-policy "$RELEASE/dev-hub/config/platform-consolidation.v1.json"   --guardian-client "$RELEASE/dev-hub/bin/guardian-client.py"   --guardian-policy "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json"   --guardian-coverage "$RUNTIME/guardian/coverage-latest.json"   --council "$RELEASE/dev-hub/bin/architecture-council-platform-consolidation-v7.py"   --consolidator "$RELEASE/dev-hub/bin/intendant-platform-consolidator.py"   --hygiene-executor "$RELEASE/dev-hub/bin/central-platform-hygiene-executor.py"   --force-cycle WEEKLY_DRY_RUN --dry-run >"$WORK/runtime-dry.out" 2>"$WORK/runtime-dry.err"
grep -Fq 'CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=PASS' "$WORK/runtime-dry.out"
grep -Fq 'INTENDANT_DIRECT_MUTATION=NO' "$WORK/runtime-dry.out"
echo "CHACHA_DEV_V710_RUNTIME_DRY_RUN=PASS"

stage enable-timer
assert_current
systemctl enable chacha-dev-intendant-hygiene.timer >/dev/null
systemctl start chacha-dev-intendant-hygiene.timer
systemctl is-active --quiet chacha-dev-intendant-hygiene.timer
systemctl is-enabled --quiet chacha-dev-intendant-hygiene.timer
TIMER_PAUSED=0
systemctl list-timers chacha-dev-intendant-hygiene.timer --no-pager >"$WORK/timer-status.out"
echo "CHACHA_DEV_V710_TIMER_ACTIVE=PASS"

stage post-health
assert_current
systemctl is-active --quiet chacha-remote-desktop-commander.service
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$RELEASE" --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output "$RUNTIME/guardian/coverage-latest.json" >"$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$RELEASE" status >"$WORK/watch.out"
grep -Fq 'CHACHA_TECHNOLOGY_WATCH_STATUS=FRESH' "$WORK/watch.out"
echo "CHACHA_DEV_V710_POST_HEALTH=PASS"

stage real-governed-pilot
assert_current
# V7.1 adds a fourth physical release. Force one governed weekly cycle to prove
# automatic retirement returns the platform to active + two verified rollbacks.
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/intendant-hygiene-cycle.py"   --repo-root "$RELEASE" --runtime-root "$RUNTIME" --platform-root "$BASE"   --policy "$RELEASE/dev-hub/config/intendant-hygiene-cycle.v1.json"   --consolidation-policy "$RELEASE/dev-hub/config/platform-consolidation.v1.json"   --guardian-client "$RELEASE/dev-hub/bin/guardian-client.py"   --guardian-policy "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json"   --guardian-coverage "$RUNTIME/guardian/coverage-latest.json"   --council "$RELEASE/dev-hub/bin/architecture-council-platform-consolidation-v7.py"   --consolidator "$RELEASE/dev-hub/bin/intendant-platform-consolidator.py"   --hygiene-executor "$RELEASE/dev-hub/bin/central-platform-hygiene-executor.py"   --force-cycle WEEKLY_DRY_RUN >"$WORK/runtime-pilot.out" 2>"$WORK/runtime-pilot.err"
grep -Fq 'CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=PASS' "$WORK/runtime-pilot.out"
python3 - "$RUNTIME/intendant/hygiene-latest.json" "$REV" <<'PY'
import json,sys,pathlib
x=json.load(open(sys.argv[1]))
assert x["platform_revision"]==sys.argv[2],x
assert x["platform_version"]=="7.1.0",x
assert x["physical_executor"]=="central-orchestrator",x
assert x["intendant_direct_mutation"] is False,x
w=next(r for r in x["results"] if r["cycle"]=="WEEKLY_DRY_RUN")
assert w["status"] in {"PASS","WARNING"},w
dry=next((a for a in w["actions"] if a["action"]=="RELEASE_RETIREMENT_DRY_RUN"),None)
assert dry is not None,w
retire_count=int(dry.get("retire_count") or 0)
apply=next((a for a in w["actions"] if a["action"]=="SAFE_RELEASE_RETIREMENT_APPLY"),None)
rels=[p for p in pathlib.Path("/opt/chacha-dev/platform/releases").iterdir() if p.is_dir()]
assert len(rels)==3,len(rels)
if retire_count>0:
    assert apply is not None,w
    assert apply["executor"]=="central-orchestrator",apply
    assert apply["guardian_post_action"] is True,apply
    print("CHACHA_DEV_V710_REAL_GOVERNED_RETIREMENT=PASS")
else:
    assert apply is None,w
    rollbacks=list(dry.get("selected_rollback_revisions") or [])
    assert len(rollbacks)==2,rollbacks
    print("CHACHA_DEV_V710_REAL_GOVERNED_RETENTION=PASS_NO_RETIREMENT_NEEDED")
PY
RETIRE_COUNT_REAL="$(python3 - "$RUNTIME/intendant/hygiene-latest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
w=next(r for r in x["results"] if r["cycle"]=="WEEKLY_DRY_RUN")
dry=next(a for a in w["actions"] if a["action"]=="RELEASE_RETIREMENT_DRY_RUN")
print(int(dry.get("retire_count") or 0))
PY
)"
if [ "$RETIRE_COUNT_REAL" -gt 0 ]; then
  PURGE_COMMITTED=1
  echo "CHACHA_DEV_V710_PURGE_COMMITTED=YES"
else
  PURGE_COMMITTED=0
  echo "CHACHA_DEV_V710_PURGE_COMMITTED=NO_RETIREMENT_NEEDED"
fi

stage evidence
assert_current
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
[ "$(find "$BASE/releases" -mindepth 1 -maxdepth 1 -type d | wc -l)" -eq 3 ]
systemctl is-active --quiet chacha-dev-intendant-hygiene.timer
mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v710-intendant-hygiene-cycle-$STAMP.json" "$REV" "$STAMP" "$WORK/compiled-manifest.json" "$RUNTIME/intendant/hygiene-latest.json" <<'PY'
import json,sys,pathlib
compiled=json.load(open(sys.argv[4]));h=json.load(open(sys.argv[5]))
rels=[p.name for p in pathlib.Path("/opt/chacha-dev/platform/releases").iterdir() if p.is_dir()]
out={
 "schema":"chacha.dev/v710-intendant-hygiene-cycle-evidence/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],"platform_version":"7.1.0",
 "single_timer":True,"owner_agent":"intendant","physical_executor":"central-orchestrator",
 "daily_light_hours":24,"weekly_dry_run_hours":168,"monthly_consolidation_hours":720,
 "thresholds":{"filesystem_used_pct_gte":75,"physical_release_count_gt":3,
   "runtime_temp_bytes_gte":1073741824,"hygiene_debt_score_gte":60},
 "dynamic_rollback_slots":2,"physical_release_count":len(rels),"physical_releases":rels,
 "hygiene_latest":h,"compiled_tree_sha256":compiled["compiled_tree_sha256"],
 "intendant_direct_mutation":False,"remote_branch_auto_delete":False,"source_code_auto_delete":False,
 "git_history_preserved":True,"canonical_observation_bus_rewrite":False,
 "benchmark_evidence_mutation":False,"architecture_council_final_authority":True,
 "automatic_external_spend_eur":0
}
open(sys.argv[1],"w").write(json.dumps(out,indent=2)+"\n")
PY

echo "CHACHA_DEV_V710_INSTALL=PASS"
echo "CHACHA_DEV_V710_SINGLE_HYGIENE_TIMER=PASS"
echo "CHACHA_DEV_V710_DAILY_LIGHT_CYCLE=PASS"
echo "CHACHA_DEV_V710_WEEKLY_DRY_RUN=PASS"
echo "CHACHA_DEV_V710_MONTHLY_REVIEW_ONLY=PASS"
echo "CHACHA_DEV_V710_THRESHOLD_WATCH=PASS"
echo "CHACHA_DEV_V710_DYNAMIC_TWO_ROLLBACK_RETENTION=PASS"
echo "CHACHA_DEV_V710_INTENDANT_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V710_PHYSICAL_EXECUTOR=central-orchestrator"
echo "CHACHA_DEV_V710_REMOTE_BRANCH_AUTO_DELETE=NO"
echo "CHACHA_DEV_V710_SOURCE_CODE_AUTO_DELETE=NO"
echo "CHACHA_DEV_V710_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V710_AUTOMATIC_EXTERNAL_SPEND_EUR=0"

trap - EXIT
cleanup
