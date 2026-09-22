#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V613_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v613.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
BRANCH_DB="/opt/chacha-dev/runtime/knowledge/reusable-branches.db"
ARCH_DB="/opt/chacha-dev/runtime/knowledge/reusable-architectures.db"
SNAPSHOT="/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"
PREVIOUS=""

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V613_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V613_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V613_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V613_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -x /opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter ] || { echo "CHACHA_DEV_V613_INSTALL=BLOCKED reason=nas_adapter_missing"; exit 2; }
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V613_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/reusable-architecture-registry.py   dev-hub/bin/reusable-architecture-learning.py   dev-hub/bin/architecture-decision-council.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/acceptance-engine.py   dev-hub/config/reusable-architecture-memory.v1.json   dev-hub/config/architecture-decision-council.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V613_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/runtime/technology-watch
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/reusable-architecture-registry.py"   "$RELEASE/dev-hub/bin/reusable-architecture-learning.py"   "$RELEASE/dev-hub/bin/architecture-decision-council.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/acceptance-engine.py"   "$RELEASE/dev-hub/bin/technology_watch_runtime.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
ln -sfn "$RELEASE" "$CURRENT"

cat >"$WORK/preplan.json" <<'JSON'
{"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"pilot","domain":"__v613_pilot__","kind":"primary","capabilities":["memory-learning"]}]}
JSON

python3 "$CURRENT/dev-hub/bin/reusable-architecture-registry.py"   --db "$ARCH_DB" search --preplan "$WORK/preplan.json" --limit 1 >/dev/null
python3 - "$ARCH_DB" <<'PY'
import sqlite3,sys
db=sqlite3.connect(sys.argv[1])
with db:
    db.execute("DELETE FROM reusable_architectures WHERE payload LIKE '%__v613_pilot__%'")
PY
echo "CHACHA_DEV_V613_ARCHITECTURE_DB_MIGRATION=PASS"

PYTHONPATH="$CURRENT/dev-hub/bin" CHACHA_REUSABLE_BRANCH_DB="$BRANCH_DB" CHACHA_REUSABLE_ARCHITECTURE_DB="$ARCH_DB" python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" refresh >/dev/null
[ -s "$SNAPSHOT" ] || { echo "CHACHA_DEV_V613_INSTALL=BLOCKED reason=technology_snapshot_missing"; exit 2; }
python3 - "$SNAPSHOT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert "reusable_architecture_taxonomy" in x,x.keys()
PY
echo "CHACHA_DEV_V613_TECHNOLOGY_WATCH_ARCHITECTURE_AWARE=PASS"

cat >"$WORK/acceptance.json" <<'JSON'
{"schema":"chacha.dev/acceptance-result/v1","accepted":true,"criteria":[{"criterion_id":"pilot","required":true,"state":"PASS"}]}
JSON
cat >"$WORK/council.json" <<'JSON'
{"schema":"chacha.dev/architecture-decision-council/v1","version":"6.13.0","dispatch_allowed":true,"automatic_external_spend_eur":0,"mandatory_advisors":["technology-watch-pre","architecture-memory","reuse-memory","branch-foundry","agent-foundry","capability-foundry","constraint-policy","technology-watch-final"],"decisions":[{"package_id":"pilot","domain":"__v613_pilot__","capabilities":["memory-learning"],"architecture":{"pattern":"v613-complete-architecture-pilot","runtime":"none"},"architecture_source":"FOUNDRY_SYNTHESIS","agent_foundry_opinion":{"decision":"TOOL_ONLY"}}]}
JSON
cat >"$WORK/branch.json" <<'JSON'
{"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{"package_id":"pilot","domain":"__v613_pilot__","kind":"primary","architecture":{"pattern":"v613-complete-architecture-pilot","runtime":"none"},"chosen_cost":{"external_spend_eur":0}}]}
JSON
cat >"$WORK/agent.json" <<'JSON'
{"schema":"chacha.dev/agent-topology/v1","decisions":[{"package_id":"pilot","domain":"__v613_pilot__","decision":"TOOL_ONLY"}]}
JSON
cat >"$WORK/capability.json" <<'JSON'
{"schema":"chacha.dev/capability-foundry-plan/v1","plans":[]}
JSON
cat >"$WORK/waves.json" <<'JSON'
{"schema":"chacha.dev/capsule-wave-plan/v1","waves":[]}
JSON
cat >"$WORK/metrics.json" <<'JSON'
{"project":{"quality_score":100,"latency_ms":2,"memory_mb":2}}
JSON
cat >"$WORK/incidents.json" <<'JSON'
{"project":[]}
JSON

CHACHA_NAS_ADAPTER=/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter python3 "$CURRENT/dev-hub/bin/reusable-architecture-learning.py"   --acceptance "$WORK/acceptance.json"   --preplan "$WORK/preplan.json"   --architecture-council "$WORK/council.json"   --branch-topology "$WORK/branch.json"   --agent-topology "$WORK/agent.json"   --capability-foundry "$WORK/capability.json"   --runtime-wave-plan "$WORK/waves.json"   --technology-snapshot "$SNAPSHOT"   --registry "$CURRENT/dev-hub/bin/reusable-architecture-registry.py"   --registry-db "$ARCH_DB"   --metrics "$WORK/metrics.json"   --incidents "$WORK/incidents.json"   --nas-mode REQUIRED   --output "$WORK/architecture-learning.json" >/dev/null

python3 - "$WORK/architecture-learning.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["state"]=="ADOPT",x
assert x["nas"]["status"]=="PERSISTED",x
PY
echo "CHACHA_DEV_V613_ARCHITECTURE_MEMORY_NAS_E2E=PASS"

# Prove the current Council can retrieve and select the complete architecture while
# still receiving all current Foundry opinions and both Technology Watch consultations.
python3 "$CURRENT/dev-hub/bin/architecture-decision-council.py"   --repo-root "$CURRENT"   --preplan "$WORK/preplan.json"   --branch-topology "$WORK/branch.json"   --agent-topology "$WORK/agent.json"   --capability-foundry "$WORK/capability.json"   --policy "$CURRENT/dev-hub/config/architecture-decision-council.v1.json"   --reuse-db "$BRANCH_DB"   --architecture-memory-db "$ARCH_DB"   --output "$WORK/council-reuse.json" >/dev/null

python3 - "$WORK/council-reuse.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["dispatch_allowed"] is True,x
assert len(x["mandatory_advisors"])==8,x
d=x["decisions"][0]
assert d["architecture_source"]=="REUSE_REVALIDATED_COMPLETE_ARCHITECTURE",d
assert d["mandatory_advisors"]["branch-foundry"]=="PASS",d
assert d["mandatory_advisors"]["agent-foundry"]=="PASS",d
assert d["mandatory_advisors"]["capability-foundry"]=="PASS",d
assert d["mandatory_advisors"]["technology-watch-pre"]=="PASS",d
assert d["mandatory_advisors"]["technology-watch-final"]=="PASS",d
PY
echo "CHACHA_DEV_V613_COMPLETE_ARCHITECTURE_REUSE_RUNTIME=PASS"

python3 - "$ARCH_DB" <<'PY'
import sqlite3,sys
db=sqlite3.connect(sys.argv[1])
with db:
    db.execute("DELETE FROM reusable_architectures WHERE architecture_id LIKE 'architecture-%' AND payload LIKE '%__v613_pilot__%'")
PY

PYTHONPATH="$CURRENT/dev-hub/bin" CHACHA_REUSABLE_BRANCH_DB="$BRANCH_DB" CHACHA_REUSABLE_ARCHITECTURE_DB="$ARCH_DB" python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" refresh >/dev/null

systemctl daemon-reload
if systemctl list-unit-files chacha-dev-technology-watch.timer >/dev/null 2>&1; then
  systemctl restart chacha-dev-technology-watch.timer
fi

echo "CHACHA_DEV_V613_ACCEPTANCE_AUTO_ARCHITECTURE_LEARNING=PASS"
echo "CHACHA_DEV_V613_CURRENT_FOUNDRIES_MANDATORY=YES"
echo "CHACHA_DEV_V613_DOUBLE_TECHNOLOGY_WATCH=YES"
echo "CHACHA_DEV_V613_COUNCIL_SELECTION_EXECUTABLE=YES"
echo "CHACHA_DEV_V613_NAS_AUTHORITATIVE=YES"
echo "CHACHA_DEV_V613_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V613_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V613_INSTALL=PASS"

trap - EXIT
cleanup
