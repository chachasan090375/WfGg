#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh scp; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
curl -fsSL "$RAW/collector_agent.py" -o "$TMP/collector_agent.py"
curl -fsSL "$RAW/incremental_engine.py" -o "$TMP/incremental_engine.py"
python3 - "$TMP/incremental_engine.py" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
marker='# WFGG_PROFILE_SPARSE_MERGE_V1'
if marker not in s:
    old="""    if effective.get('power') is None and old:\n        effective['power']=old['power']\n"""
    new="""    # WFGG_PROFILE_SPARSE_MERGE_V1\n    # Direct profile replies do not carry world-map coordinates. Missing X/Y\n    # are sparse fields and must not erase the most recent map observation.\n    if old:\n        if effective.get('x') is None:\n            effective['x']=old['x']\n        if effective.get('y') is None:\n            effective['y']=old['y']\n        if effective.get('power') is None:\n            effective['power']=old['power']\n"""
    if s.count(old) != 1:
        raise SystemExit('PROFILE_MERGE_PATCH_ANCHOR_MISSING')
    p.write_text(s.replace(old,new,1),encoding='utf-8')
print('COLLECTOR_PROFILE_SPARSE_MERGE=READY')
PY
python3 -m py_compile "$TMP/collector_agent.py" "$TMP/incremental_engine.py"

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'SSH_ROUTE=PUBLIC_IPV4'
fi

TAG="$$"
RAGENT="/tmp/wfgg-collector-agent-$TAG.py"
RENGINE="/tmp/wfgg-collector-incremental-$TAG.py"
RUNIT="/tmp/wfgg-collector-$TAG.service"
scp "${SSH_OPTS[@]}" -q "$TMP/collector_agent.py" "$REMOTE:$RAGENT"
scp "${SSH_OPTS[@]}" -q "$TMP/incremental_engine.py" "$REMOTE:$RENGINE"

cat > "$TMP/wfgg-collector.service" <<'UNIT'
[Unit]
Description=WfGg Collector V2 incremental player cache
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=wfgg-radar
Group=wfgg-radar
WorkingDirectory=/opt/wfgg-collector/bin
Environment=WFGG_COLLECTOR_ROOT=/opt/wfgg-collector
Environment=WFGG_COLLECTOR_HOST=127.0.0.1
Environment=WFGG_COLLECTOR_PORT=8790
ExecStart=/usr/bin/python3 /opt/wfgg-collector/bin/collector_agent.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/wfgg-collector
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
UNIT
scp "${SSH_OPTS[@]}" -q "$TMP/wfgg-collector.service" "$REMOTE:$RUNIT"

ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
id wfgg-radar >/dev/null 2>&1
install -d -o wfgg-radar -g wfgg-radar -m 0750 /opt/wfgg-collector /opt/wfgg-collector/bin /opt/wfgg-collector/data /opt/wfgg-collector/data/masters
install -o root -g root -m 0755 '$RAGENT' /opt/wfgg-collector/bin/collector_agent.py
install -o root -g root -m 0644 '$RENGINE' /opt/wfgg-collector/bin/incremental_engine.py
install -o root -g root -m 0644 '$RUNIT' /etc/systemd/system/wfgg-collector.service
rm -f '$RAGENT' '$RENGINE' '$RUNIT'
chown wfgg-radar:wfgg-radar /opt/wfgg-collector/data/masters
systemctl daemon-reload
systemctl enable --now wfgg-collector.service >/dev/null
systemctl restart wfgg-collector.service
sleep 3
systemctl is-active --quiet wfgg-collector.service
grep -q 'WFGG_PROFILE_SPARSE_MERGE_V1' /opt/wfgg-collector/bin/incremental_engine.py
python3 - <<'PY'
import json,urllib.error,urllib.request
base='http://127.0.0.1:8790'
with urllib.request.urlopen(base+'/health',timeout=10) as r:
    d=json.load(r)
assert d.get('ok') is True
print('COLLECTOR_HEALTH=OK')
try:
    with urllib.request.urlopen(base+'/master/latest',timeout=10) as r:
        m=json.load(r).get('master')
except urllib.error.HTTPError as e:
    m=None if e.code==404 else (_ for _ in ()).throw(e)
if not m:
    body=json.dumps({'note':'initial-master-before-incremental-cycles'}).encode()
    req=urllib.request.Request(base+'/master/create',data=body,method='POST',headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as r:
        m=json.load(r)['master']
    print('COLLECTOR_MASTER_CREATED=YES')
else:
    print('COLLECTOR_MASTER_CREATED=NO')
print('COLLECTOR_MASTER_ID='+str(m.get('id','')))
print('COLLECTOR_MASTER_PLAYERS='+str(m.get('player_count','')))
print('COLLECTOR_MASTER_SHA='+str(m.get('sha256','')))
with urllib.request.urlopen(base+'/stats',timeout=10) as r:
    s=json.load(r)
print('COLLECTOR_PLAYERS='+str(s.get('players',0)))
PY
"

say 'COLLECTOR_SERVICE=active'
say 'COLLECTOR_API=http://127.0.0.1:8790'
say 'COLLECTOR_MODE=master-plus-increments'
say 'COLLECTOR_PROFILE_SPARSE_MERGE=ACTIVE'
say 'RADAR_PRODUCTION_CHANGED=NO'
