#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_V64_PILOT_REV:-}"
[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V64_NAS_RESUME=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V64_NAS_RESUME=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ssh install ln; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V64_NAS_RESUME=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d /tmp/chacha-v64-nas-resume.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
trap 'rm -rf "$WORK" 2>/dev/null || true' EXIT

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V64_NAS_RESUME=BLOCKED reason=archive_invalid"; exit 2; }

python3 -m py_compile "$SRC/dev-hub/adapters/nas-ssh-adapter.py" "$SRC/dev-hub/bin/experience-ledger.py"

NAS_BASE="/opt/chacha-dev/adapters/nas-ssh"
NAS_RELEASE="$NAS_BASE/releases/v64-$STAMP-$REV"
mkdir -p "$NAS_RELEASE" /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/evidence
install -m 0755 "$SRC/dev-hub/adapters/nas-ssh-adapter.py" "$NAS_RELEASE/nas-ssh-adapter"
NAS_ADAPTER="$NAS_RELEASE/nas-ssh-adapter"
echo "CHACHA_DEV_V64_NAS_ADAPTER_STAGED=$NAS_ADAPTER"

OBS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat >"$WORK/experience.json" <<JSON
{"schema":"chacha.dev/experience-event/v1","observed_at":"$OBS","project_id":"chacha-dev-v64-runtime-pilot","learner":"chacha-core-orchestrator","intent_signature":"v64-real-runtime-pilot-nas-resume","context_signature":"chachavps-small-runtime","outcome":"PASS","acceptance_score":1.0,"external_spend_eur":0,"reusable_lessons":["technology-watch-before-materialization","ephemeral-capsules-fit-small-vps","emergency-stop-out-of-band","nas-adapter-prepares-nested-parent"],"evidence":["operator-observed-runtime-passes","nested-nas-e2e-resume"]}
JSON

CHACHA_NAS_ADAPTER="$NAS_ADAPTER" python3 "$SRC/dev-hub/bin/experience-ledger.py"   --db /opt/chacha-dev/runtime/knowledge/experience.db record   --event "$WORK/experience.json" --nas >"$WORK/ledger.json"

REMOTE_REL="$(python3 - "$WORK/ledger.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); n=x.get("nas") or {}
assert n.get("status")=="PERSISTED",x
print(n["remote"])
PY
)"
printf '%s' "$REMOTE_REL" | grep -Eq '^[A-Za-z0-9._/-]+$'

ssh -n -o BatchMode=yes -o ConnectTimeout=12 chachanas   cat "/share/CACHEDEV1_DATA/ChaCha-DEV-HUB/$REMOTE_REL" >"$WORK/remote-experience.json"

python3 - "$WORK/experience.json" "$WORK/remote-experience.json" <<'PY'
import json,sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2]))
assert a==b,(a,b)
print("CHACHA_DEV_V64_EXPERIENCE_LEDGER_NAS_E2E=PASS")
PY

ln -sfn "$NAS_RELEASE" "$NAS_BASE/current"
test "$(readlink -f "$NAS_BASE/current")" = "$NAS_RELEASE"
echo "CHACHA_DEV_V64_NAS_ADAPTER_PROMOTED=PASS"

python3 - "$REV" "$STAMP" "$REMOTE_REL" "$NAS_RELEASE" <<'PY'
import json,sys
rev,stamp,remote,release=sys.argv[1:]
out={
  "schema":"chacha.dev/v64-nas-persistence-resume-evidence/v1",
  "status":"PASS",
  "observed_at":stamp,
  "revision":rev,
  "experience_ledger_nas_e2e":"PASS",
  "nas_adapter_release":release,
  "nas_remote_event":remote,
  "automatic_external_spend_eur":0,
  "production_application_mutation":False
}
p="/opt/chacha-dev/evidence/v64-nas-persistence-resume-"+stamp+".json"
open(p,"w",encoding="utf-8").write(json.dumps(out,indent=2)+"\n")
print("CHACHA_DEV_V64_NAS_RESUME_EVIDENCE="+p)
PY

echo "CHACHA_DEV_V64_NAS_PERSISTENCE=PASS"
echo "CHACHA_DEV_V64_RUNTIME_PILOT_RESUME_NAS=PASS"
echo "AUTOMATIC_EXTERNAL_SPEND_EUR=0"
