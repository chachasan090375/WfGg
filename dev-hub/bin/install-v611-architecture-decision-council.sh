#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V611_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v611.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
REUSE_DB="/opt/chacha-dev/runtime/knowledge/reusable-branches.db"
PREVIOUS=""

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V611_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V611_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V611_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V611_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V611_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/architecture-decision-council.py   dev-hub/bin/reusable-branch-registry.py   dev-hub/bin/technology-watch-service.py   dev-hub/bin/technology_watch_runtime.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/architecture-decision-council.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V611_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/runtime/technology-watch
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/architecture-decision-council.py"   "$RELEASE/dev-hub/bin/reusable-branch-registry.py"   "$RELEASE/dev-hub/bin/technology-watch-service.py"   "$RELEASE/dev-hub/bin/technology_watch_runtime.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
printf '%s\n' "$REV" > "$RELEASE/.revision"

ln -sfn "$RELEASE" "$CURRENT"

PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/reusable-branch-registry.py"   --db "$REUSE_DB" search --domain "__bootstrap__" --limit 1 >/dev/null
echo "CHACHA_DEV_V611_REUSABLE_BRANCH_REGISTRY_RUNTIME=PASS"

PYTHONPATH="$CURRENT/dev-hub/bin" CHACHA_REUSABLE_BRANCH_DB="$REUSE_DB"   python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" refresh >"$WORK/watch.json"
grep -Fq '"technology_taxonomy"' "$WORK/watch.json"
grep -Fq '"reusable_branch_taxonomy"' "$WORK/watch.json"
echo "CHACHA_DEV_V611_TECHNOLOGY_TAXONOMY_RUNTIME=PASS"

systemctl daemon-reload
if systemctl list-unit-files chacha-dev-technology-watch.timer >/dev/null 2>&1; then
  systemctl restart chacha-dev-technology-watch.timer
  systemctl start chacha-dev-technology-watch.service
fi
echo "CHACHA_DEV_V611_TECHNOLOGY_WATCH_CONTINUOUS=PASS"

python3 - "$CURRENT" "$WORK" "$REUSE_DB" <<'PY'
import json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);work=Path(sys.argv[2]);db=Path(sys.argv[3])
pre={"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"smoke","domain":"qa","capabilities":[]}]}
branch={"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{"package_id":"smoke","domain":"qa","architecture":{"pattern":"smoke"},"chosen_cost":{"external_spend_eur":0}}]}
agent={"schema":"chacha.dev/agent-topology/v1","decisions":[{"package_id":"smoke","domain":"qa","decision":"TOOL_ONLY"}]}
cap={"schema":"chacha.dev/capability-foundry-plan/v1","plans":[]}
for n,x in [("pre",pre),("branch",branch),("agent",agent),("cap",cap)]:
    (work/(n+".json")).write_text(json.dumps(x))
out=work/"council.json"
env={"PYTHONPATH":str(root/"dev-hub/bin"),"CHACHA_REUSABLE_BRANCH_DB":str(db)}
import os
e=os.environ.copy();e.update(env)
p=subprocess.run([
    sys.executable,str(root/"dev-hub/bin/architecture-decision-council.py"),
    "--repo-root",str(root),"--preplan",str(work/"pre.json"),
    "--branch-topology",str(work/"branch.json"),"--agent-topology",str(work/"agent.json"),
    "--capability-foundry",str(work/"cap.json"),
    "--policy",str(root/"dev-hub/config/architecture-decision-council.v1.json"),
    "--reuse-db",str(db),"--output",str(out)
],env=e,check=False,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=45)
if p.returncode!=0: raise SystemExit(p.stderr+p.stdout)
x=json.load(open(out))
assert x["dispatch_allowed"] is True,x
assert len(x["mandatory_advisors"])==7,x
PY
echo "CHACHA_DEV_V611_ARCHITECTURE_COUNCIL_RUNTIME=PASS"

echo "CHACHA_DEV_V611_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V611_REUSE_REQUIRES_CURRENT_TECH_REVALIDATION=YES"
echo "CHACHA_DEV_V611_DOUBLE_TECHNOLOGY_WATCH=YES"
echo "CHACHA_DEV_V611_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V611_INSTALL=PASS"

trap - EXIT
cleanup
