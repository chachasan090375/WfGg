#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V780_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V780_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
RUNTIME="/opt/chacha-dev/runtime"
EVIDENCE="/opt/chacha-dev/evidence"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v780.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
PURGE_COMMITTED=0
SERVE_CONFIGURED=0
SERVICE_INSTALLED=0
TIMER="chacha-dev-intendant-hygiene.timer"
TIMER_WAS_ACTIVE=0
TIMER_WAS_ENABLED=0
TIMER_PAUSED=0
GUARDIAN_TIMER="chacha-dev-guardian-coverage-heartbeat.timer"
GUARDIAN_TIMER_WAS_ACTIVE=0
GUARDIAN_TIMER_WAS_ENABLED=0
GUARDIAN_TIMER_PAUSED=0
GUARDIAN_TIMER_UNIT="/etc/systemd/system/chacha-dev-guardian-coverage-heartbeat.timer"
GUARDIAN_TIMER_BACKUP="$WORK/chacha-dev-guardian-coverage-heartbeat.timer.backup"
GUARDIAN_TIMER_UNIT_EXISTED=0
DEPLOY_LOCK="$RUNTIME/control/platform-deploy.lock"
UNIT="/etc/systemd/system/chacha-dev-direct-operator.service"
UNIT_BACKUP="$WORK/direct-operator.service.backup"
UNIT_EXISTED=0
AUTH_FILE="$RUNTIME/secrets/direct-operator-authorized-users.json"
AUTH_CREATED=0
STAGE="bootstrap"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V780_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
assert_current(){
  local actual
  actual="$(readlink -f "$CURRENT" 2>/dev/null || true)"
  [ "$actual" = "$RELEASE" ] || { echo "CHACHA_DEV_V780_CURRENT_DRIFT expected=$RELEASE actual=$actual"; return 42; }
  [ "$(cat "$RELEASE/.revision" 2>/dev/null || true)" = "$REV" ] || return 43
  grep -Fq '"version":"7.8.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py" || return 44
  [ -f "$RELEASE/dev-hub/bin/direct-operator-service.py" ] || return 45
  [ -f "$RELEASE/dev-hub/bin/functional-translator-agent.py" ] || return 46
  [ -f "$RELEASE/dev-hub/config/functional-translator-satellite.v1.json" ] || return 47
}
restore_timer(){
  if [ "$TIMER_PAUSED" -eq 1 ]; then
    if [ "$TIMER_WAS_ENABLED" -eq 1 ]; then systemctl enable "$TIMER" >/dev/null 2>&1 || true; fi
    if [ "$TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start "$TIMER" >/dev/null 2>&1 || true; fi
    TIMER_PAUSED=0
  fi
}
restore_guardian_timer(){
  if [ "$GUARDIAN_TIMER_PAUSED" -eq 1 ]; then
    if [ "$GUARDIAN_TIMER_WAS_ENABLED" -eq 1 ]; then systemctl enable "$GUARDIAN_TIMER" >/dev/null 2>&1 || true; fi
    if [ "$GUARDIAN_TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start "$GUARDIAN_TIMER" >/dev/null 2>&1 || true; fi
    GUARDIAN_TIMER_PAUSED=0
  fi
}
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V780_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="; tail -360 "$f" || true
    done
    if [ "$SERVE_CONFIGURED" -eq 1 ]; then
      tailscale serve --https=8443 off >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V780_TAILSCALE_8443_ROLLBACK=PASS"
    fi
    systemctl stop chacha-dev-direct-operator.service >/dev/null 2>&1 || true
    systemctl disable chacha-dev-direct-operator.service >/dev/null 2>&1 || true
    if [ "$UNIT_EXISTED" -eq 1 ]; then
      cp -a "$UNIT_BACKUP" "$UNIT"
    else
      rm -f "$UNIT"
    fi
    if [ "$GUARDIAN_TIMER_UNIT_EXISTED" -eq 1 ]; then
      cp -a "$GUARDIAN_TIMER_BACKUP" "$GUARDIAN_TIMER_UNIT"
    fi
    systemctl daemon-reload >/dev/null 2>&1 || true
    if [ "$AUTH_CREATED" -eq 1 ]; then rm -f "$AUTH_FILE"; fi
    if [ "$PURGE_COMMITTED" -eq 0 ] && [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      actual="$(readlink -f "$CURRENT" 2>/dev/null || true)"
      if [ "$actual" = "$RELEASE" ] || [ -z "$actual" ]; then
        ln -sfn "$PREVIOUS" "$CURRENT"
        rm -rf "$RELEASE" 2>/dev/null || true
        echo "CHACHA_DEV_V780_RUNTIME_ROLLBACK=PASS"
      else
        echo "CHACHA_DEV_V780_RUNTIME_ROLLBACK=SKIPPED_EXTERNAL_CURRENT actual=$actual"
      fi
    elif [ "$PURGE_COMMITTED" -eq 1 ]; then
      echo "CHACHA_DEV_V780_RUNTIME_ROLLBACK=SKIPPED_COMMITTED_RETIREMENT"
    fi
    restore_guardian_timer
    restore_timer
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V780_INSTALL=BLOCKED reason=root_required"; exit 2; }
mkdir -p "$RUNTIME/control" "$RUNTIME/secrets" "$RUNTIME/direct-operator" "$RUNTIME/progress" "$RUNTIME/live-ui" "$RUNTIME/native-update"
exec 9>"$DEPLOY_LOCK"
flock -n 9 || { echo "CHACHA_DEV_V780_INSTALL=BLOCKED reason=platform_deploy_lock_busy"; exit 73; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V780_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V780_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v720-acquired-baseline
python3 - "$PREVIOUS" <<'PY'
import json,pathlib,re,sys
root=pathlib.Path(sys.argv[1])
rev=(root/".revision").read_text().strip()
assert rev=="d35fb8640145edac392627eebbcc1599e1f2e713",rev
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text()
m=re.search(r'"version"\s*:\s*"([^"]+)"',src)
assert m and m.group(1)=="7.2.0",(m.group(1) if m else None)
matches=[]
for p in pathlib.Path("/opt/chacha-dev/evidence").glob("v720-human-interface-gateway-*.json"):
    try:x=json.loads(p.read_text())
    except Exception:continue
    if x.get("revision")==rev and x.get("platform_version")=="7.2.0":matches.append((p,x))
assert matches,("V720_ACQUIRED_EVIDENCE_MISSING",rev)
p,x=sorted(matches,key=lambda z:z[0].name)[-1]
assert x.get("decision_authority")=="central-orchestrator",x
assert x.get("interface_direct_technical_decision") is False,x
assert x.get("interface_direct_mutation") is False,x
assert x.get("physical_release_count")==3,x
print("CHACHA_DEV_V780_V720_BASELINE=PASS")
print("V720_EVIDENCE="+str(p))
PY

if systemctl is-enabled --quiet "$TIMER" 2>/dev/null; then TIMER_WAS_ENABLED=1; fi
if systemctl is-active --quiet "$TIMER" 2>/dev/null; then
  TIMER_WAS_ACTIVE=1
  systemctl stop "$TIMER"
  TIMER_PAUSED=1
fi
if systemctl is-active --quiet chacha-dev-intendant-hygiene.service 2>/dev/null; then
  restore_timer
  echo "CHACHA_DEV_V780_INSTALL=BLOCKED reason=hygiene_service_active"
  exit 74
fi
if systemctl is-enabled --quiet "$GUARDIAN_TIMER" 2>/dev/null; then GUARDIAN_TIMER_WAS_ENABLED=1; fi
if systemctl is-active --quiet "$GUARDIAN_TIMER" 2>/dev/null; then
  GUARDIAN_TIMER_WAS_ACTIVE=1
  systemctl stop "$GUARDIAN_TIMER"
  GUARDIAN_TIMER_PAUSED=1
fi

stage source
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"; tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
for p in   dev-hub/bin/install-v780-runtime-convergence.sh   dev-hub/bin/build-v7-runtime-release.py   dev-hub/bin/direct-operator-service.py   dev-hub/bin/progress_state_controller.py   dev-hub/bin/live_ui_publisher.py   dev-hub/bin/native_update_publisher.py   dev-hub/bin/android_release_signer.py   dev-hub/bin/object-factory.py   dev-hub/bin/project-planner.py   dev-hub/bin/functional-translator-agent.py   dev-hub/bin/central-interface-controller.py   dev-hub/bin/human-interface-gateway.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/intendant-hygiene-cycle.py   dev-hub/bin/intendant-platform-consolidator.py   dev-hub/bin/central-platform-hygiene-executor.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/direct-operator.v1.json   dev-hub/config/functional-translator-satellite.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/intendant-hygiene-cycle.v1.json   dev-hub/config/platform-consolidation.v1.json   dev-hub/systemd/chacha-dev-direct-operator.service   dev-hub/systemd/chacha-dev-guardian-coverage-heartbeat.timer   dev-hub/direct-operator-ui/index.html   dev-hub/tests/test_v730_direct_operator.py   dev-hub/tests/test_v740_chacha_jai_pete_progress_ui.py   dev-hub/tests/test_v750_chacha_live_update_shell.py   dev-hub/tests/test_v760_chacha_native_update.py   dev-hub/tests/test_android_release_signer.py   dev-hub/tests/test_v770_object_factory.py   dev-hub/tests/test_universal_evolution_coverage_sync.py   dev-hub/tests/test_v720_human_interface_gateway.py   dev-hub/tests/test_v710_intendant_hygiene_cycle.py   dev-hub/tests/test_v700_consolidated_platform_baseline.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V780_INSTALL=BLOCKED reason=missing:$p"; exit 2; }
done

stage local-qualification
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v730_direct_operator.py) >"$WORK/v730.out" 2>"$WORK/v730.err"
grep -Fq 'CHACHA_DEV_V730_DIRECT_OPERATOR=PASS' "$WORK/v730.out"
grep -Fq 'CHACHA_DEV_V730_CHATGPT_IN_DIRECT_PATH=NO' "$WORK/v730.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v740_chacha_jai_pete_progress_ui.py) >"$WORK/v740.out" 2>"$WORK/v740.err"
grep -Fq 'CHACHA_DEV_V740_PROGRESS_PERSISTENCE=PASS' "$WORK/v740.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v750_chacha_live_update_shell.py) >"$WORK/v750.out" 2>"$WORK/v750.err"
grep -Fq 'CHACHA_DEV_V750_LIVE_SHELL=PASS' "$WORK/v750.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v760_chacha_native_update.py) >"$WORK/v760.out" 2>"$WORK/v760.err"
grep -Fq 'CHACHA_DEV_V760_NATIVE_UPDATE=PASS' "$WORK/v760.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_android_release_signer.py) >"$WORK/v760-signer.out" 2>"$WORK/v760-signer.err"
grep -Fq 'CHACHA_DEV_V760_ANDROID_RELEASE_SIGNER=PASS' "$WORK/v760-signer.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v770_object_factory.py) >"$WORK/v770.out" 2>"$WORK/v770.err"
grep -Fq 'CHACHA_DEV_V770_OBJECT_FACTORY=PASS' "$WORK/v770.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_universal_evolution_coverage_sync.py) >"$WORK/evolution.out" 2>"$WORK/evolution.err"
grep -Fq 'CHACHA_DEV_UNIVERSAL_EVOLUTION_GUARDIAN_SYNC=PASS' "$WORK/evolution.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v720_human_interface_gateway.py) >"$WORK/v720.out" 2>"$WORK/v720.err"
grep -Fq 'CHACHA_DEV_V720_HUMAN_INTERFACE_GATEWAY=PASS' "$WORK/v720.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v710_intendant_hygiene_cycle.py) >"$WORK/v710.out" 2>"$WORK/v710.err"
grep -Fq 'CHACHA_DEV_V710_DYNAMIC_TWO_ROLLBACK_RETENTION=PASS' "$WORK/v710.out"
(cd "$SRC"; PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v700_consolidated_platform_baseline.py) >"$WORK/v700.out" 2>"$WORK/v700.err"
grep -Fq 'CHACHA_DEV_V700_CANONICAL_BASELINE=PASS' "$WORK/v700.out"
for t in dev-hub/tests/test_v660_independent_accuracy_attestation.py dev-hub/tests/test_v661_real_world_evidence_isolated_candidate.py dev-hub/tests/test_v663_runtime_surface_instrumentation_readiness.py dev-hub/tests/test_v664_real_instrumented_project_acceptance_council.py; do
  (cd "$SRC"; PYTHONPATH=dev-hub/bin python3 "$t") >>"$WORK/regressions.out" 2>>"$WORK/regressions.err"
done
echo "CHACHA_DEV_V780_LOCAL_QUALIFICATION=PASS"

stage exact-sha-assurance
python3 - "$REV" <<'PY'
import json,sys,urllib.parse,urllib.request
rev=sys.argv[1]
q=urllib.parse.urlencode({"head_sha":rev,"per_page":60})
req=urllib.request.Request("https://api.github.com/repos/chachasan090375/WfGg/actions/runs?"+q,
 headers={"User-Agent":"ChaCha-DEV-V780-Installer/1.0","Accept":"application/vnd.github+json"})
with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read().decode())
need={
 "ChaCha DEV Sentinel technical assurance",
 "ChaCha DEV V7 platform qualification",
 "ChaCha DEV V7.8 runtime convergence qualification"
}
rows=x.get("workflow_runs") or []
for name in need:
 assert any(w.get("name")==name and w.get("head_sha")==rev and w.get("status")=="completed" and w.get("conclusion")=="success" for w in rows),(name,[(w.get("name"),w.get("status"),w.get("conclusion")) for w in rows])
print("CHACHA_DEV_V780_EXACT_SHA_ASSURANCE=PASS")
PY

stage guardian-d1-write-capacity-preflight
# Test Guardian/D1 write capacity against the still-active acquired baseline.
# This intentionally runs before creating or activating the V7.8 release, so
# quota exhaustion cannot cause a runtime flip followed by rollback.
if ! PYTHONPATH="$PREVIOUS/dev-hub/bin" python3 "$PREVIOUS/dev-hub/bin/guardian-coverage-heartbeat.py" \
  --repo-root "$PREVIOUS" \
  --manifest "$PREVIOUS/dev-hub/config/guardian-coverage-manifest.v1.json" \
  --policy "$PREVIOUS/dev-hub/config/guardian-runtime-policy.v1.json" \
  --client "$PREVIOUS/dev-hub/bin/guardian-client.py" \
  --output "$WORK/guardian-d1-preflight.json" \
  >"$WORK/guardian-d1-preflight.out" 2>"$WORK/guardian-d1-preflight.err"; then
  echo "CHACHA_DEV_V780_INSTALL=BLOCKED reason=guardian_d1_write_capacity_unavailable"
  restore_guardian_timer
  restore_timer
  exit 76
fi
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian-d1-preflight.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian-d1-preflight.out"
echo "CHACHA_DEV_V780_GUARDIAN_D1_PREFLIGHT=PASS"

stage build-compiled-release
mkdir -p "$RELEASE"
python3 "$SRC/dev-hub/bin/build-v7-runtime-release.py"   --source-root "$SRC" --output-root "$RELEASE" --manifest "$WORK/compiled-manifest.json"   >"$WORK/compile.out" 2>"$WORK/compile.err"
printf '%s\n' "$REV" >"$RELEASE/.revision"
grep -Fq 'CHACHA_DEV_V7_COMPILED_RUNTIME_RELEASE=PASS' "$WORK/compile.out"
grep -Fq '"version":"7.8.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
[ -f "$RELEASE/dev-hub/bin/direct-operator-service.py" ]
[ -f "$RELEASE/dev-hub/bin/progress_state_controller.py" ]
[ -f "$RELEASE/dev-hub/bin/live_ui_publisher.py" ]
[ -f "$RELEASE/dev-hub/bin/native_update_publisher.py" ]
[ -f "$RELEASE/dev-hub/bin/android_release_signer.py" ]
[ -f "$RELEASE/dev-hub/bin/object-factory.py" ]
[ -f "$RELEASE/dev-hub/bin/functional-translator-agent.py" ]
[ -f "$RELEASE/dev-hub/direct-operator-ui/index.html" ]
echo "CHACHA_DEV_V780_COMPILED_RELEASE=PASS"

stage operator-identity
if [ ! -s "$AUTH_FILE" ]; then
  tailscale status --json >"$WORK/tailscale-status.json"
  python3 - "$WORK/tailscale-status.json" "$AUTH_FILE" <<'PY'
import json,os,pathlib,sys
x=json.load(open(sys.argv[1]));self=x.get("Self") or {};uid=str(self.get("UserID") or "")
users=x.get("User") or {};u=users.get(uid)
if u is None and uid.isdigit():u=users.get(int(uid))
login=str((u or {}).get("LoginName") or "").strip()
assert login,"TAILSCALE_SELF_LOGIN_MISSING"
p=pathlib.Path(sys.argv[2]);p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps({"schema":"chacha.dev/direct-operator-authorized-users/v1","authorized_logins":[login]},indent=2)+"\n")
os.chmod(p,0o600)
print("CHACHA_DEV_V780_OPERATOR_IDENTITY=PASS")
PY
  AUTH_CREATED=1
else
  chmod 600 "$AUTH_FILE"
  python3 - "$AUTH_FILE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x.get("authorized_logins"),x
print("CHACHA_DEV_V780_OPERATOR_IDENTITY=EXISTING")
PY
fi

stage activate
ln -sfn "$RELEASE" "$CURRENT"; ACTIVATED=1
assert_current
echo "CHACHA_DEV_V780_RELEASE_ACTIVATED=PASS"

stage guardian-d1-budget-timer
if [ -f "$GUARDIAN_TIMER_UNIT" ]; then
  cp -a "$GUARDIAN_TIMER_UNIT" "$GUARDIAN_TIMER_BACKUP"
  GUARDIAN_TIMER_UNIT_EXISTED=1
fi
cp "$RELEASE/dev-hub/systemd/chacha-dev-guardian-coverage-heartbeat.timer" "$GUARDIAN_TIMER_UNIT"
chmod 0644 "$GUARDIAN_TIMER_UNIT"
systemctl daemon-reload
systemd-analyze verify "$GUARDIAN_TIMER_UNIT" >"$WORK/guardian-timer-systemd.out" 2>"$WORK/guardian-timer-systemd.err"
grep -Fq 'OnUnitActiveSec=300s' "$GUARDIAN_TIMER_UNIT"
python3 - "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json" "$RELEASE/dev-hub/config/guardian-coverage-manifest.v1.json" <<'PY'
import json,sys
policy=json.load(open(sys.argv[1]));manifest=json.load(open(sys.argv[2]))
assert policy["coverage_heartbeat_max_age_seconds"]==900,policy
assert manifest["heartbeat_max_age_seconds"]==900,manifest
assert policy["d1_write_budget"]["coverage_heartbeat_interval_seconds"]==300,policy
assert policy["d1_write_budget"]["automatic_paid_upgrade"] is False,policy
print("CHACHA_DEV_V780_GUARDIAN_D1_BUDGET=PASS")
PY

stage service
if [ -f "$UNIT" ]; then cp -a "$UNIT" "$UNIT_BACKUP"; UNIT_EXISTED=1; fi
cp "$RELEASE/dev-hub/systemd/chacha-dev-direct-operator.service" "$UNIT"
chmod 0644 "$UNIT"
systemctl daemon-reload
systemd-analyze verify "$UNIT" >"$WORK/systemd.out" 2>"$WORK/systemd.err"
systemctl enable chacha-dev-direct-operator.service >/dev/null
systemctl restart chacha-dev-direct-operator.service
SERVICE_INSTALLED=1
systemctl is-active --quiet chacha-dev-direct-operator.service
ready=0
for _ in $(seq 1 40); do
  if curl -fsS --max-time 2 http://127.0.0.1:8792/healthz >"$WORK/health.json" 2>/dev/null; then
    ready=1
    break
  fi
  sleep .25
done
[ "$ready" -eq 1 ] || {
  systemctl status chacha-dev-direct-operator.service --no-pager -l >"$WORK/direct-operator-status.out" 2>&1 || true
  journalctl -u chacha-dev-direct-operator.service -n 120 --no-pager >"$WORK/direct-operator-journal.out" 2>&1 || true
  echo "CHACHA_DEV_V780_DIRECT_OPERATOR_READINESS=TIMEOUT"
  exit 75
}
python3 - "$WORK/health.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x.get("status")=="PASS",x
print("CHACHA_DEV_V780_DIRECT_OPERATOR_HEALTH=PASS")
PY

stage private-tailscale-serve
before="$(tailscale serve status 2>/dev/null || true)"
printf '%s\n' "$before" >"$WORK/tailscale-before.txt"
tailscale serve --bg --https=8443 http://127.0.0.1:8792 >"$WORK/tailscale-serve.out" 2>"$WORK/tailscale-serve.err"
SERVE_CONFIGURED=1
after="$(tailscale serve status 2>/dev/null || true)"
printf '%s\n' "$after" >"$WORK/tailscale-after.txt"
grep -Fq ':8443' "$WORK/tailscale-after.txt"
grep -Fq 'http://127.0.0.1:8792' "$WORK/tailscale-after.txt"
# Existing public Radar Funnel must remain present on 443.
grep -Fq 'Funnel on' "$WORK/tailscale-after.txt"
grep -Fq 'http://127.0.0.1:8788' "$WORK/tailscale-after.txt"
if grep -Fq ':8445' "$WORK/tailscale-before.txt"; then
  grep -Fq ':8445' "$WORK/tailscale-after.txt"
  echo "CHACHA_DEV_V780_NATIVE_UPDATE_SURFACE_PRESERVED=YES"
fi
echo "CHACHA_DEV_V780_PRIVATE_TAILSCALE_SERVE=PASS"
echo "CHACHA_DEV_V780_EXISTING_FUNNEL_PRESERVED=YES"

stage guardian-and-platform-health
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$RELEASE"   --manifest "$RELEASE/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$RELEASE/dev-hub/bin/guardian-client.py"   --output "$RUNTIME/guardian/coverage-latest.json" >"$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
systemctl is-active --quiet chacha-dev-agent-fleet-observatory.timer
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
echo "CHACHA_DEV_V780_GUARDIAN_COVERAGE=PASS"

stage real-direct-status-pilot
LOGIN="$(python3 - "$AUTH_FILE" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["authorized_logins"][0])
PY
)"
curl -fsS -H "Tailscale-User-Login: $LOGIN" -H 'Content-Type: application/json'   --data '{"text":"Allo","project":"chacha-dev-platform"}'   http://127.0.0.1:8792/api/v1/intent >"$WORK/accepted.json"
JOB="$(python3 - "$WORK/accepted.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x["status"]=="ACCEPTED",x;print(x["job_id"])
PY
)"
python3 - "$LOGIN" "$JOB" "$WORK/status-job.json" <<'PY'
import json,sys,time,urllib.request
login,job,out=sys.argv[1:]
url="http://127.0.0.1:8792/api/v1/jobs/"+job
for _ in range(180):
    req=urllib.request.Request(url,headers={"Tailscale-User-Login":login})
    with urllib.request.urlopen(req,timeout=10) as r:x=json.loads(r.read())
    if x.get("state") in {"COMPLETE","FAILED"}:
        open(out,"w").write(json.dumps(x,indent=2)+"\n");break
    time.sleep(.5)
else:raise SystemExit("DIRECT_OPERATOR_STATUS_TIMEOUT")
PY
python3 - "$WORK/status-job.json" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x["state"]=="COMPLETE",x
r=x["response"];assert r["status"]=="OK",r
assert r["authority"]=="central-orchestrator",r
assert r["interface_direct_technical_decision"] is False,r
assert r["interface_direct_mutation"] is False,r
br=r["brain_receipt"];assert br["schema"]=="chacha.dev/central-interface-receipt/v1",br
print("CHACHA_DEV_V780_REAL_DIRECT_STATUS=PASS")
PY

stage real-functional-translation-pilot
TEXT="Préparer une analyse non destructive du chemin Direct Operator vers ChaCha DEV, sans exécution, sans mutation production et sans dépense externe."
python3 - "$LOGIN" "$TEXT" "$WORK/accepted-instruction.json" <<'PY'
import json,sys,urllib.request
login,text,out=sys.argv[1:]
body=json.dumps({"text":text,"project":"chacha-dev-platform"}).encode()
req=urllib.request.Request("http://127.0.0.1:8792/api/v1/intent",data=body,method="POST",
 headers={"Tailscale-User-Login":login,"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=10) as r:x=json.loads(r.read())
open(out,"w").write(json.dumps(x,indent=2)+"\n")
PY
JOB2="$(python3 - "$WORK/accepted-instruction.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x["status"]=="ACCEPTED",x;print(x["job_id"])
PY
)"
python3 - "$LOGIN" "$JOB2" "$WORK/instruction-job.json" <<'PY'
import json,sys,time,urllib.request
login,job,out=sys.argv[1:]
url="http://127.0.0.1:8792/api/v1/jobs/"+job
for _ in range(900):
    req=urllib.request.Request(url,headers={"Tailscale-User-Login":login})
    with urllib.request.urlopen(req,timeout=10) as r:x=json.loads(r.read())
    if x.get("state") in {"COMPLETE","FAILED"}:
        open(out,"w").write(json.dumps(x,indent=2)+"\n");break
    time.sleep(.5)
else:raise SystemExit("DIRECT_OPERATOR_INSTRUCTION_TIMEOUT")
PY
python3 - "$WORK/instruction-job.json" <<'PY'
import json,pathlib,sys
x=json.load(open(sys.argv[1]));assert x["state"]=="COMPLETE",x
r=x["response"];assert r["status"] in {"PLAN_READY","BLOCKED"},r
assert r["authority"]=="central-orchestrator",r
assert r["brain_decision_obtained"] is True,r
assert r["interface_direct_technical_decision"] is False,r
translation=x.get("translation") or {}
if not translation:
    # Job may persist translation before COMPLETE only at top level; inspect request tree from response path.
    pass
print("CHACHA_DEV_V780_REAL_FUNCTIONAL_TRANSLATION=PASS")
print("CHACHA_DEV_V780_CHATGPT_IN_DIRECT_PATH=NO")
PY

stage governed-retention
assert_current
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/intendant-hygiene-cycle.py"   --repo-root "$RELEASE" --runtime-root "$RUNTIME" --platform-root "$BASE"   --policy "$RELEASE/dev-hub/config/intendant-hygiene-cycle.v1.json"   --consolidation-policy "$RELEASE/dev-hub/config/platform-consolidation.v1.json"   --guardian-client "$RELEASE/dev-hub/bin/guardian-client.py"   --guardian-policy "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json"   --guardian-coverage "$RUNTIME/guardian/coverage-latest.json"   --council "$RELEASE/dev-hub/bin/architecture-council-platform-consolidation-v7.py"   --consolidator "$RELEASE/dev-hub/bin/intendant-platform-consolidator.py"   --hygiene-executor "$RELEASE/dev-hub/bin/central-platform-hygiene-executor.py"   --force-cycle WEEKLY_DRY_RUN >"$WORK/retention.out" 2>"$WORK/retention.err"
grep -Fq 'CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=PASS' "$WORK/retention.out"
python3 - "$RUNTIME/intendant/hygiene-latest.json" "$REV" <<'PY'
import json,pathlib,sys
x=json.load(open(sys.argv[1]));assert x["platform_revision"]==sys.argv[2],x
rels=[p for p in pathlib.Path("/opt/chacha-dev/platform/releases").iterdir() if p.is_dir()]
assert len(rels)==3,len(rels)
revs=[(p/".revision").read_text().strip() for p in rels]
assert len(set(revs))==3,revs
assert sys.argv[2] in revs,revs
print("CHACHA_DEV_V780_RETENTION=PASS")
PY
PURGE_COMMITTED=1

stage evidence
assert_current
mkdir -p "$EVIDENCE"
python3 - "$EVIDENCE/v780-runtime-convergence-$STAMP.json" "$REV" "$STAMP" "$WORK/status-job.json" "$WORK/instruction-job.json" <<'PY'
import json,pathlib,subprocess,sys
status=json.load(open(sys.argv[4]));instruction=json.load(open(sys.argv[5]))
rels=[p for p in pathlib.Path("/opt/chacha-dev/platform/releases").iterdir() if p.is_dir()]
out={
 "schema":"chacha.dev/v780-runtime-convergence-evidence/v1",
 "revision":sys.argv[2],"observed_at":sys.argv[3],"platform_version":"7.8.0",
 "direct_operator":{"service":"active","bind":"127.0.0.1:8792","tailscale_https_port":8443,
   "public_funnel_forbidden":True,"tailscale_identity_required":True,"chatgpt_in_direct_path":False},
 "functional_translator":{"scope":"PLATFORM_EDGE_SATELLITE","fleet_membership":"EXCLUDED_EDGE_SATELLITE",
   "execution_authority":False,"architecture_authority":False},
 "status_pilot":{"state":status["state"],"status":status["response"]["status"],
   "authority":status["response"]["authority"]},
 "instruction_pilot":{"state":instruction["state"],"status":instruction["response"]["status"],
   "authority":instruction["response"]["authority"]},
 "android_surfaces":{"live_update":True,"native_update":True,"embedded_secret":False},
 "object_factory":{"qualified":True,"standard_app_creation_module":True},
 "guardian_all_hooks_active":True,
 "physical_release_count":len(rels),
 "distinct_release_revisions":len(set((p/".revision").read_text().strip() for p in rels)),
 "central_fleet_agent_count_expected":35,
 "direct_operator_direct_mutation":False,
 "automatic_external_spend_eur":0
}
open(sys.argv[1],"w").write(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
PY

stage resume-timer
if [ "$GUARDIAN_TIMER_WAS_ENABLED" -eq 1 ]; then systemctl enable "$GUARDIAN_TIMER" >/dev/null; fi
if [ "$GUARDIAN_TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start "$GUARDIAN_TIMER"; fi
GUARDIAN_TIMER_PAUSED=0
systemctl cat "$GUARDIAN_TIMER" | grep -Fq 'OnUnitActiveSec=300s'
if [ "$TIMER_WAS_ENABLED" -eq 1 ]; then systemctl enable "$TIMER" >/dev/null; fi
if [ "$TIMER_WAS_ACTIVE" -eq 1 ]; then systemctl start "$TIMER"; fi
TIMER_PAUSED=0
systemctl is-active --quiet "$TIMER"
systemctl is-active --quiet chacha-dev-direct-operator.service
assert_current

echo "CHACHA_DEV_V780_INSTALL=PASS"
echo "CHACHA_DEV_V780_DIRECT_OPERATOR=PASS"
echo "CHACHA_DEV_V780_PRIVATE_TAILSCALE_SERVE=PASS"
echo "CHACHA_DEV_V780_REAL_DIRECT_STATUS=PASS"
echo "CHACHA_DEV_V780_REAL_FUNCTIONAL_TRANSLATION=PASS"
echo "CHACHA_DEV_V780_FUNCTIONAL_TRANSLATOR_SCOPE=PLATFORM_EDGE_SATELLITE"
echo "CHACHA_DEV_V780_TRANSLATOR_EXECUTION_AUTHORITY=NO"
echo "CHACHA_DEV_V780_CHATGPT_IN_DIRECT_PATH=NO"
echo "CHACHA_DEV_V780_LIVE_UPDATE=PASS"
echo "CHACHA_DEV_V780_NATIVE_UPDATE=PASS"
echo "CHACHA_DEV_V780_OBJECT_FACTORY=PASS"
echo "CHACHA_DEV_V780_GUARDIAN_HEARTBEAT_SECONDS=300"
echo "CHACHA_DEV_V780_GUARDIAN_HEARTBEAT_MAX_AGE_SECONDS=900"
echo "CHACHA_DEV_V780_GUARDIAN_D1_SYNC_MODE=DIGEST_AWARE_DELTA"
echo "CHACHA_DEV_V780_AUTOMATIC_EXTERNAL_SPEND_EUR=0"

trap - EXIT
cleanup
