#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V614_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v614.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PREVIOUS=""

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V614_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V614_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V614_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V614_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V614_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/architecture-portfolio-optimizer.py   dev-hub/bin/architecture-decision-council.py   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/config/architecture-portfolio-optimizer.v1.json   dev-hub/config/architecture-decision-council.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V614_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/architecture-portfolio-optimizer.py"   "$RELEASE/dev-hub/bin/architecture-decision-council.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
printf '%s\n' "$REV" > "$RELEASE/.revision"
ln -sfn "$RELEASE" "$CURRENT"

# Isolated runtime proof: current foundry -> fast reuse when consensus -> comparative pilot on conflict.
TMPDB="$WORK/portfolio.db"
cat >"$WORK/pre.json" <<'JSON'
{"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"web","domain":"web-ui","kind":"primary","capabilities":["static-web"]}]}
JSON
cat >"$WORK/branch.json" <<'JSON'
{"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{"package_id":"web","domain":"web-ui","architecture":{"pattern":"edge-static","runtime":"none"},"chosen_cost":{"external_spend_eur":0}}]}
JSON
cat >"$WORK/agent.json" <<'JSON'
{"schema":"chacha.dev/agent-topology/v1","decisions":[{"package_id":"web","domain":"web-ui","decision":"TOOL_ONLY"}]}
JSON

python3 "$CURRENT/dev-hub/bin/architecture-portfolio-optimizer.py"   --repo-root "$CURRENT"   --preplan "$WORK/pre.json"   --branch-topology "$WORK/branch.json"   --agent-topology "$WORK/agent.json"   --architecture-memory-db "$TMPDB"   --policy "$CURRENT/dev-hub/config/architecture-portfolio-optimizer.v1.json"   --output "$WORK/no-memory.json" >/dev/null

python3 - "$WORK/no-memory.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["mode"]=="CURRENT_FOUNDRY_SYNTHESIS",x
assert x["decision_ready"] is True,x
PY
echo "CHACHA_DEV_V614_CURRENT_FOUNDRY_PATH_RUNTIME=PASS"

python3 - "$CURRENT" "$WORK" "$TMPDB" <<'PY'
import hashlib,json,subprocess,sys,time
from pathlib import Path
root=Path(sys.argv[1]);work=Path(sys.argv[2]);db=Path(sys.argv[3])
reg=root/"dev-hub/bin/reusable-architecture-registry.py"
pre=json.load(open(work/"pre.json"))
sig=subprocess.check_output([
  sys.executable,"-c",
  "import importlib.util,json,sys;s=importlib.util.spec_from_file_location('r',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.project_signature(json.load(open(sys.argv[2]))))",
  str(reg),str(work/"pre.json")],text=True).strip()
base={
 "architecture_id":"architecture-"+sig[:20],"functional_signature":sig,
 "qualification_status":"PASS","state":"ADOPT",
 "technology_revalidated_at":time.strftime("%Y-%m-%dT%H:%M:%S",time.gmtime())+".123456Z",
 "technology_snapshot_digest":"v614-runtime","external_spend_eur":0,
 "failure_count":0,"incident_count":0
}
agree=dict(base);agree.update({
 "version":"agree","quality_score":98,"success_count":12,
 "components":{"packages":[{"domain":"web-ui","kind":"primary","capabilities":["static-web"],
 "architecture":{"pattern":"edge-static","runtime":"none"},"agent_decision":"TOOL_ONLY"}]}})
p=work/"agree.json";p.write_text(json.dumps(agree))
subprocess.run([sys.executable,str(reg),"--db",str(db),"register","--record",str(p)],check=True,stdout=subprocess.DEVNULL)
PY

python3 "$CURRENT/dev-hub/bin/architecture-portfolio-optimizer.py"   --repo-root "$CURRENT"   --preplan "$WORK/pre.json"   --branch-topology "$WORK/branch.json"   --agent-topology "$WORK/agent.json"   --architecture-memory-db "$TMPDB"   --policy "$CURRENT/dev-hub/config/architecture-portfolio-optimizer.v1.json"   --output "$WORK/agree-result.json" >/dev/null

python3 - "$WORK/agree-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["mode"]=="FAST_REUSE",x
assert x["decision_ready"] is True,x
PY
echo "CHACHA_DEV_V614_FAST_REUSE_CONSENSUS_RUNTIME=PASS"

python3 - "$CURRENT" "$WORK" "$TMPDB" <<'PY'
import json,subprocess,sys,time
from pathlib import Path
root=Path(sys.argv[1]);work=Path(sys.argv[2]);db=Path(sys.argv[3])
reg=root/"dev-hub/bin/reusable-architecture-registry.py"
sig=subprocess.check_output([
  sys.executable,"-c",
  "import importlib.util,json,sys;s=importlib.util.spec_from_file_location('r',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.project_signature(json.load(open(sys.argv[2]))))",
  str(reg),str(work/"pre.json")],text=True).strip()
conflict={
 "architecture_id":"architecture-"+sig[:20],"version":"conflict","functional_signature":sig,
 "components":{"packages":[{"domain":"web-ui","kind":"primary","capabilities":["static-web"],
 "architecture":{"pattern":"different-edge","runtime":"none"},"agent_decision":"TOOL_ONLY"}]},
 "qualification_status":"PASS","state":"ADOPT",
 "technology_revalidated_at":time.strftime("%Y-%m-%dT%H:%M:%S",time.gmtime())+".123456Z",
 "technology_snapshot_digest":"v614-runtime","external_spend_eur":0,
 "quality_score":100,"success_count":30,"failure_count":0,"incident_count":0
}
p=work/"conflict.json";p.write_text(json.dumps(conflict))
subprocess.run([sys.executable,str(reg),"--db",str(db),"register","--record",str(p)],check=True,stdout=subprocess.DEVNULL)
PY

python3 "$CURRENT/dev-hub/bin/architecture-portfolio-optimizer.py"   --repo-root "$CURRENT"   --preplan "$WORK/pre.json"   --branch-topology "$WORK/branch.json"   --agent-topology "$WORK/agent.json"   --architecture-memory-db "$TMPDB"   --policy "$CURRENT/dev-hub/config/architecture-portfolio-optimizer.v1.json"   --output "$WORK/conflict-result.json" >/dev/null

python3 - "$WORK/conflict-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["mode"]=="COMPARATIVE_PILOT_REQUIRED",x
assert x["decision_ready"] is False,x
assert x["comparative_pilot_required"] is True,x
PY
echo "CHACHA_DEV_V614_CONFLICT_COMPARATIVE_PILOT_RUNTIME=PASS"

systemctl daemon-reload
if systemctl list-unit-files chacha-dev-technology-watch.timer >/dev/null 2>&1; then
  systemctl restart chacha-dev-technology-watch.timer
fi

echo "CHACHA_DEV_V614_PORTFOLIO_SCOPE=GLOBAL"
echo "CHACHA_DEV_V614_FAST_REUSE_REQUIRES_CURRENT_CONSENSUS=YES"
echo "CHACHA_DEV_V614_PRODUCTION_BLOCKS_ON_UNRESOLVED_CONFLICT=YES"
echo "CHACHA_DEV_V614_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V614_INSTALL=PASS"

trap - EXIT
cleanup
