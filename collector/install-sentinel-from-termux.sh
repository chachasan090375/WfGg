#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for c in curl ssh scp; do command -v "$c" >/dev/null 2>&1 || die "${c}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
curl -fsSL "$RAW/sentinel-collector-v1.sh" -o "$TMP/sentinel-collector-v1.sh" || die SENTINEL_DOWNLOAD_FAILED
chmod 0755 "$TMP/sentinel-collector-v1.sh"

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'SSH_ROUTE=PUBLIC_IPV4'
fi

TAG="$$"
RSCRIPT="/tmp/wfgg-collector-sentinel-$TAG.sh"
scp "${SSH_OPTS[@]}" -q "$TMP/sentinel-collector-v1.sh" "$REMOTE:$RSCRIPT"

ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o wfgg-radar -g wfgg-radar -m 0750 /opt/wfgg-collector /opt/wfgg-collector/bin /opt/wfgg-collector/data
install -o root -g root -m 0755 '$RSCRIPT' /opt/wfgg-collector/bin/sentinel-collector-v1.sh
rm -f '$RSCRIPT'

cat >/etc/systemd/system/wfgg-collector-sentinel.service <<'UNIT'
[Unit]
Description=WfGg Sentinel - Collector V1 supervisor
After=network-online.target wfgg-collector.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/wfgg-collector/bin/sentinel-collector-v1.sh
User=root
Group=root
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/wfgg-collector /run
UNIT

cat >/etc/systemd/system/wfgg-collector-sentinel.timer <<'UNIT'
[Unit]
Description=Periodic WfGg Sentinel check for Collector V1

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=20s
Persistent=true
Unit=wfgg-collector-sentinel.service

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now wfgg-collector-sentinel.timer >/dev/null
systemctl start wfgg-collector-sentinel.service
sleep 2

echo '=== SENTINEL COLLECTOR ==='
cat /opt/wfgg-collector/data/sentinel-collector-state.env

echo '=== TIMER ==='
systemctl is-active wfgg-collector-sentinel.timer
"

say 'SENTINEL_COLLECTOR_INSTALLED=YES'
say 'SENTINEL_COLLECTOR_INTERVAL=5min'
say 'SENTINEL_LASTWAR_CREDENTIAL_ACCESS=NO'
say 'RADAR_PRODUCTION_CHANGED=NO'
