#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_V64_PILOT_REV:-}"
[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V64_RUNTIME_PILOT=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V64_RUNTIME_PILOT=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 systemctl systemd-run ssh grep install ln; do command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V64_RUNTIME_PILOT=BLOCKED reason=missing_command:$cmd"; exit 2; }; done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="/opt/chacha-dev/platform"; RELEASE="$BASE/releases/$STAMP-$REV"; CURRENT="$BASE/current"
WORK="$(mktemp -d /tmp/chacha-v64-runtime-pilot.XXXXXX)"; ARCHIVE="$WORK/repo.tar.gz"
PREV="$(readlink -f "$CURRENT" 2>/dev/null || true)"
ROLLBACK=1
cleanup(){
  rm -rf "$WORK" 2>/dev/null || true
  if [ "$ROLLBACK" = 1 ] && [ -n "$PREV" ] && [ -d "$PREV" ]; then ln -sfn "$PREV" "$CURRENT" || true; fi
}
trap cleanup EXIT

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
mkdir -p "$RELEASE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V64_RUNTIME_PILOT=BLOCKED reason=archive_invalid"; exit 2; }
cp -a "$SRC/dev-hub" "$RELEASE/"
printf '%s\n' "$REV" > "$RELEASE/.revision"

python3 -m py_compile   "$RELEASE/dev-hub/bin/technology_watch_runtime.py"   "$RELEASE/dev-hub/bin/technology-watch-service.py"   "$RELEASE/dev-hub/bin/capsule-runtime-controller.py"   "$RELEASE/dev-hub/bin/capsule-worker.py"   "$RELEASE/dev-hub/bin/emergency-stop-controller.py"   "$RELEASE/dev-hub/bin/emergency-stop-surface.py"   "$RELEASE/dev-hub/bin/experience-ledger.py"
ln -sfn "$RELEASE" "$CURRENT"

mkdir -p /opt/chacha-dev/runtime/technology-watch /opt/chacha-dev/runtime/control /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/runtime/capsules /opt/chacha-dev/evidence
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-technology-watch.service" /etc/systemd/system/chacha-dev-technology-watch.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-technology-watch.timer" /etc/systemd/system/chacha-dev-technology-watch.timer
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-emergency-stop-surface.service" /etc/systemd/system/chacha-dev-emergency-stop-surface.service
systemctl daemon-reload
systemctl start chacha-dev-technology-watch.service
systemctl enable --now chacha-dev-technology-watch.timer
systemctl enable --now chacha-dev-emergency-stop-surface.service
systemctl is-active --quiet chacha-dev-technology-watch.timer
systemctl is-active --quiet chacha-dev-emergency-stop-surface.service
test -s /opt/chacha-dev/runtime/technology-watch/optimizer-input.json
echo "CHACHA_DEV_V64_TECHNOLOGY_WATCH_RUNTIME=PASS"

cat >"$WORK/topology.json" <<'JSON'
{"decisions":[
 {"branch_id":"v64-pilot:graphics:primary","runtime_required":true,"decision":"MATERIALIZE_EPHEMERAL_BRANCH","resource_budget":{"memory_hard_limit_mb":192,"disk_soft_limit_mb":256,"cpu_weight":35,"processes_max":1}},
 {"branch_id":"v64-pilot:qa:review","runtime_required":true,"decision":"MATERIALIZE_EPHEMERAL_BRANCH","resource_budget":{"memory_hard_limit_mb":128,"disk_soft_limit_mb":128,"cpu_weight":25,"processes_max":1}}
]}
JSON
python3 "$CURRENT/dev-hub/bin/capsule-scheduler.py" --topology "$WORK/topology.json" --policy "$CURRENT/dev-hub/config/branch-foundry.v1.json" --output "$WORK/waves.json"
python3 "$CURRENT/dev-hub/bin/capsule-runtime-controller.py" materialize --topology "$WORK/topology.json" --wave-plan "$WORK/waves.json" --wave 1 --ttl 180 >"$WORK/capsules.json"
python3 "$CURRENT/dev-hub/bin/capsule-runtime-controller.py" status >"$WORK/capsule-status.txt"
python3 - "$WORK/capsules.json" <<'PY'
import json,sys
raw=open(sys.argv[1],encoding='utf-8').read(); x=json.JSONDecoder().raw_decode(raw)[0]
assert len(x['capsules'])==2,x
assert all(c['state']=='ACTIVE' for c in x['capsules']),x
assert sum(c['resource_budget']['memory_hard_limit_mb'] for c in x['capsules'])<=1024,x
print('CHACHA_DEV_V64_REAL_CAPSULE_MATERIALIZATION=PASS')
PY

TOKEN="$(cat /opt/chacha-dev/runtime/control/emergency-stop-ui.token)"
curl -fsS -H "X-ChaCha-Stop-Token: $TOKEN" -H 'Content-Type: application/json'   -d '{"reason":"v64-runtime-pilot-emergency-path"}' http://127.0.0.1:8788/api/emergency-stop/activate >"$WORK/stop.json"
python3 - "$WORK/stop.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x['active'] is True,x
assert x['new_dispatch_blocked'] is True and x['new_materialization_blocked'] is True,x
assert x['persistent_memory_preserved'] is True,x
assert len(x.get('transient_units_stopped') or [])>=2,x
print('CHACHA_DEV_V64_EMERGENCY_STOP_REAL_CAPSULES=PASS')
PY
curl -fsS -H "X-ChaCha-Stop-Token: $TOKEN" -H 'Content-Type: application/json'   -d '{"reason":"v64-runtime-pilot-reset","confirm":"RESET"}' http://127.0.0.1:8788/api/emergency-stop/reset >"$WORK/reset.json"
python3 - "$WORK/reset.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x['active'] is False,x
assert x['resume_authorized'] is False,x
print('CHACHA_DEV_V64_EMERGENCY_RESET_MANUAL_RESUME=PASS')
PY
curl -fsS http://127.0.0.1:8788/ | grep -Fq "STOP D’URGENCE"
echo "CHACHA_DEV_V64_GRAPHICAL_STOP_SURFACE=PASS"

NAS_ADAPTER="/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"
[ -x "$NAS_ADAPTER" ] || { echo "CHACHA_DEV_V64_RUNTIME_PILOT=BLOCKED reason=nas_adapter_missing"; exit 2; }
OBS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat >"$WORK/experience.json" <<JSON
{"schema":"chacha.dev/experience-event/v1","observed_at":"$OBS","project_id":"chacha-dev-v64-runtime-pilot","learner":"chacha-core-orchestrator","intent_signature":"v64-real-runtime-pilot","context_signature":"chachavps-small-runtime","outcome":"PASS","acceptance_score":1.0,"external_spend_eur":0,"reusable_lessons":["technology-watch-before-materialization","ephemeral-capsules-fit-small-vps","emergency-stop-out-of-band"],"evidence":["real-systemd-capsules","emergency-stop-surface"]}
JSON
python3 "$CURRENT/dev-hub/bin/experience-ledger.py" --db /opt/chacha-dev/runtime/knowledge/experience.db record --event "$WORK/experience.json" --nas >"$WORK/ledger.json"
REMOTE_REL="$(python3 - "$WORK/ledger.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); n=x.get('nas') or {}
assert n.get('status')=='PERSISTED',x
print(n['remote'])
PY
)"
printf '%s' "$REMOTE_REL" | grep -Eq '^[A-Za-z0-9._/-]+$'
ssh -n -o BatchMode=yes -o ConnectTimeout=12 chachanas cat "/share/CACHEDEV1_DATA/ChaCha-DEV-HUB/$REMOTE_REL" >"$WORK/remote-experience.json"
python3 - "$WORK/experience.json" "$WORK/remote-experience.json" <<'PY'
import json,sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); assert a==b,(a,b)
print('CHACHA_DEV_V64_EXPERIENCE_LEDGER_NAS_E2E=PASS')
PY

python3 - "$CURRENT" "$REV" "$STAMP" "$REMOTE_REL" "$WORK/capsules.json" <<'PY'
import json,sys
current,rev,stamp,remote,caps=sys.argv[1:]
raw=open(caps,encoding='utf-8').read(); c=json.JSONDecoder().raw_decode(raw)[0]
out={
 "schema":"chacha.dev/v64-runtime-pilot-evidence/v1","status":"PASS","observed_at":stamp,
 "revision":rev,"technology_watch":"PASS","capsule_materialization":"PASS",
 "capsules":[x['unit'] for x in c['capsules']],"emergency_stop_real_capsules":"PASS",
 "graphical_stop_surface":"PASS","experience_ledger_nas_e2e":"PASS","nas_remote_event":remote,
 "automatic_external_spend_eur":0,"production_application_mutation":False
}
p="/opt/chacha-dev/evidence/v64-runtime-pilot-"+stamp+".json"
open(p,'w',encoding='utf-8').write(json.dumps(out,indent=2)+"\n")
print("CHACHA_DEV_V64_RUNTIME_EVIDENCE="+p)
PY

ROLLBACK=0
echo "CHACHA_DEV_V64_RUNTIME_PILOT=PASS"
echo "CHACHA_DEV_V64_NAS_PERSISTENCE=PASS"
echo "CHACHA_DEV_V64_STOP_BUTTON_BACKEND=PASS"
echo "AUTOMATIC_EXTERNAL_SPEND_EUR=0"
trap - EXIT
cleanup
