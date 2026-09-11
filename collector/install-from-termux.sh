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
python3 -m py_compile "$TMP/collector_agent.py"

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
RUNIT="/tmp/wfgg-collector-$TAG.service"
scp "${SSH_OPTS[@]}" -q "$TMP/collector_agent.py" "$REMOTE:$RAGENT"

cat > "$TMP/wfgg-collector.service" <<'UNIT'
[Unit]
Description=WfGg Collector V1 local player cache
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=wfgg-radar
Group=wfgg-radar
WorkingDirectory=/opt/wfgg-collector
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
install -d -o wfgg-radar -g wfgg-radar -m 0750 /opt/wfgg-collector
install -d -o wfgg-radar -g wfgg-radar -m 0750 /opt/wfgg-collector/bin /opt/wfgg-collector/data
install -o root -g root -m 0755 '$RAGENT' /opt/wfgg-collector/bin/collector_agent.py
install -o root -g root -m 0644 '$RUNIT' /etc/systemd/system/wfgg-collector.service
rm -f '$RAGENT' '$RUNIT'
systemctl daemon-reload
systemctl enable --now wfgg-collector.service >/dev/null
sleep 2
systemctl is-active --quiet wfgg-collector.service
python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8790/health',timeout=5) as r:
    d=json.load(r)
assert d.get('ok') is True
print('COLLECTOR_HEALTH=OK')
PY
"

say 'COLLECTOR_SERVICE=active'
say 'COLLECTOR_API=http://127.0.0.1:8790'
say 'COLLECTOR_MODE=local-cache-ingest'
say 'RADAR_PRODUCTION_CHANGED=NO'
