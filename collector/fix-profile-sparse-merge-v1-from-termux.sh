#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
TARGET="/opt/wfgg-collector/bin/incremental_engine.py"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in ssh; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'PROFILE_MERGE_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'PROFILE_MERGE_SSH_ROUTE=PUBLIC_IPV4'
fi

ssh "${SSH_OPTS[@]}" -T "$REMOTE" "TARGET='$TARGET' python3 -" <<'PY'
from pathlib import Path
import os, py_compile, shutil, urllib.request, json

p=Path(os.environ['TARGET'])
s=p.read_text(encoding='utf-8')
marker='# WFGG_PROFILE_SPARSE_MERGE_V1'
if marker not in s:
    old="""    if effective.get('power') is None and old:\n        effective['power']=old['power']\n"""
    new="""    # WFGG_PROFILE_SPARSE_MERGE_V1\n    # Direct profile replies do not carry world-map coordinates.  Treat those\n    # missing coordinates as sparse fields instead of erasing the latest map\n    # observation. Power already follows the same non-destructive rule.\n    if old:\n        if effective.get('x') is None:\n            effective['x']=old['x']\n        if effective.get('y') is None:\n            effective['y']=old['y']\n        if effective.get('power') is None:\n            effective['power']=old['power']\n"""
    if s.count(old) != 1:
        raise SystemExit('PROFILE_MERGE_PATCH_ANCHOR_MISSING')
    backup=p.with_suffix('.py.before-profile-merge-v1')
    shutil.copy2(p, backup)
    s=s.replace(old,new,1)
    p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('PROFILE_SPARSE_MERGE_PATCH=OK')
PY

ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
systemctl restart wfgg-collector.service
sleep 2
systemctl is-active --quiet wfgg-collector.service
python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8790/health',timeout=10) as r:
    d=json.load(r)
assert d.get('ok') is True
print('PROFILE_MERGE_COLLECTOR_HEALTH=OK')
PY
grep -q 'WFGG_PROFILE_SPARSE_MERGE_V1' '$TARGET'
echo PROFILE_MERGE_COLLECTOR_SERVICE=active
"

say 'PROFILE_MERGE_ACTIVATION=OK'
say 'PROFILE_MERGE_RULE=KEEP_XY_WHEN_PROFILE_OMITS_THEM'
