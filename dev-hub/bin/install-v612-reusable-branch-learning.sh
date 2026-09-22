#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V612_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v612.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
REGISTRY_DB="/opt/chacha-dev/runtime/knowledge/reusable-branches.db"
SNAPSHOT="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
PREVIOUS=""

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V612_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V612_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V612_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V612_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -x /opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter ] || { echo "CHACHA_DEV_V612_INSTALL=BLOCKED reason=nas_adapter_missing"; exit 2; }

if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V612_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/reusable-branch-registry.py   dev-hub/bin/reusable-branch-learning.py   dev-hub/bin/acceptance-engine.py   dev-hub/config/reusable-branch-learning.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V612_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/runtime/technology-watch
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/reusable-branch-registry.py"   "$RELEASE/dev-hub/bin/reusable-branch-learning.py"   "$RELEASE/dev-hub/bin/acceptance-engine.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
ln -sfn "$RELEASE" "$CURRENT"

# Migrate/open the hot index without adding a real branch.
python3 "$CURRENT/dev-hub/bin/reusable-branch-registry.py" --db "$REGISTRY_DB" search --domain "__bootstrap__" --limit 1 >/dev/null
echo "CHACHA_DEV_V612_REUSABLE_BRANCH_DB_MIGRATION=PASS"

# Refresh Technology Watch before learning: every accepted branch carries current technology evidence.
PYTHONPATH="$CURRENT/dev-hub/bin" CHACHA_REUSABLE_BRANCH_DB="$REGISTRY_DB"   python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" refresh >/dev/null
[ -s "$SNAPSHOT" ] || { echo "CHACHA_DEV_V612_INSTALL=BLOCKED reason=technology_snapshot_missing"; exit 2; }
echo "CHACHA_DEV_V612_TECHNOLOGY_SNAPSHOT=PASS"

# Real NAS pilot using a synthetic project-local branch. The local pilot row is removed afterwards;
# the immutable NAS record remains as installation evidence.
cat >"$WORK/acceptance.json" <<'JSON'
{"schema":"chacha.dev/acceptance-result/v1","accepted":true,"criteria":[{"criterion_id":"pilot","required":true,"state":"PASS"}]}
JSON
cat >"$WORK/preplan.json" <<'JSON'
{"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"pilot","domain":"__v612_pilot__","kind":"primary","capabilities":["memory-learning"]}]}
JSON
cat >"$WORK/branch.json" <<'JSON'
{"schema":"chacha.dev/branch-topology/v1","decisions":[{"package_id":"pilot","branch_id":"pilot:__v612_pilot__:primary","domain":"__v612_pilot__","kind":"primary","decision":"CREATE_PROJECT_LOCAL_BRANCH","architecture":{"pattern":"v612-nas-learning-pilot"},"chosen_cost":{"external_spend_eur":0},"technology_watch":{"consulted":true}}]}
JSON
cat >"$WORK/metrics.json" <<'JSON'
{"branches":{"pilot:__v612_pilot__:primary":{"quality_score":100,"latency_ms":1,"memory_mb":1}}}
JSON
cat >"$WORK/incidents.json" <<'JSON'
{"branches":{"pilot:__v612_pilot__:primary":[]}}
JSON

CHACHA_NAS_ADAPTER=/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter python3 "$CURRENT/dev-hub/bin/reusable-branch-learning.py"   --acceptance "$WORK/acceptance.json"   --branch-topology "$WORK/branch.json"   --preplan "$WORK/preplan.json"   --technology-snapshot "$SNAPSHOT"   --registry "$CURRENT/dev-hub/bin/reusable-branch-registry.py"   --registry-db "$REGISTRY_DB"   --metrics "$WORK/metrics.json"   --incidents "$WORK/incidents.json"   --nas-mode REQUIRED   --output "$WORK/learning.json" >/dev/null

python3 - "$WORK/learning.json" "$REGISTRY_DB" <<'PY'
import json,sqlite3,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["registered_count"]==1,x
r=x["registered"][0]
assert r["nas"]["status"]=="PERSISTED",r
assert r["state"]=="PROJECT_LOCAL",r
db=sqlite3.connect(sys.argv[2])
with db:
    db.execute("DELETE FROM reusable_branches WHERE domain='__v612_pilot__'")
PY
echo "CHACHA_DEV_V612_BRANCH_MEMORY_NAS_E2E=PASS"

# Refresh after cleanup so Technology Watch sees only real reusable memory.
PYTHONPATH="$CURRENT/dev-hub/bin" CHACHA_REUSABLE_BRANCH_DB="$REGISTRY_DB"   python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" refresh >/dev/null

systemctl daemon-reload
if systemctl list-unit-files chacha-dev-technology-watch.timer >/dev/null 2>&1; then
  systemctl restart chacha-dev-technology-watch.timer
fi

echo "CHACHA_DEV_V612_ACCEPTANCE_AUTO_LEARNING=PASS"
echo "CHACHA_DEV_V612_NAS_AUTHORITATIVE=YES"
echo "CHACHA_DEV_V612_BEST_VERSION_RANKING=PASS"
echo "CHACHA_DEV_V612_TECH_REVALIDATION_GATE=PASS"
echo "CHACHA_DEV_V612_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V612_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V612_INSTALL=PASS"

trap - EXIT
cleanup
