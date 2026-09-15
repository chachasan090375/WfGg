#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
BIN="$ROOT/platform/bin"
CFG="$ROOT/platform/config"
RADAR="$ROOT/radar"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.2/dev-hub"

mkdir -p "$BIN" "$CFG" "$RADAR/history"

curl -fsSL "$BASE/tech-watch.py" -o "$BIN/tech-watch.py"
curl -fsSL "$BASE/tech-watch-targets.json" -o "$CFG/tech-watch-targets.json"
curl -fsSL "$BASE/architectctl.py" -o "$BIN/architectctl.py"
chmod 755 "$BIN/tech-watch.py" "$BIN/architectctl.py"
chmod 644 "$CFG/tech-watch-targets.json"
ln -sfn "$BIN/tech-watch.py" /usr/local/bin/techwatch
ln -sfn "$BIN/architectctl.py" /usr/local/bin/architectctl

python3 -m py_compile "$BIN/tech-watch.py" "$BIN/architectctl.py"
python3 -m json.tool "$CFG/tech-watch-targets.json" >/dev/null

cat >/usr/local/bin/chacha-tech-watch-run <<'EOF'
#!/bin/bash
set -euo pipefail
# Daily installed-stack/candidate refresh. Sunday adds broad market discovery.
DOW="$(date -u +%u)"
if [ "$DOW" = "7" ]; then
  exec /usr/local/bin/techwatch run --market
else
  exec /usr/local/bin/techwatch run
fi
EOF
chmod 755 /usr/local/bin/chacha-tech-watch-run

SCHEDULER=none
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  cat >/etc/systemd/system/chacha-tech-watch.service <<'EOF'
[Unit]
Description=ChaCha DEV HUB Technology Watch
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/chacha-tech-watch-run
WorkingDirectory=/opt/chacha-dev
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
EOF

  cat >/etc/systemd/system/chacha-tech-watch.timer <<'EOF'
[Unit]
Description=Daily ChaCha DEV HUB Technology Watch

[Timer]
OnCalendar=*-*-* 06:20:00 UTC
RandomizedDelaySec=20m
Persistent=true
Unit=chacha-tech-watch.service

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now chacha-tech-watch.timer >/dev/null
  SCHEDULER=systemd
else
  cat >/etc/cron.d/chacha-tech-watch <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
20 6 * * * root /usr/local/bin/chacha-tech-watch-run >>/var/log/chacha-tech-watch.log 2>&1
EOF
  chmod 644 /etc/cron.d/chacha-tech-watch
  SCHEDULER=cron
fi

echo "=== TECH WATCH V4.2 INSTALL ==="
echo "TECHWATCH_BIN=/usr/local/bin/techwatch"
echo "TECHWATCH_CONFIG=$CFG/tech-watch-targets.json"
echo "TECHWATCH_HISTORY=$RADAR/history"
echo "TECHWATCH_SCHEDULER=$SCHEDULER"
echo "TECHWATCH_POLICY=NO_AUTOMATIC_PRODUCTION_REPLACEMENT"

echo
echo "=== INITIAL WATCH ==="
/usr/local/bin/techwatch run --market

echo
echo "=== ARCHITECT WATCH STATUS ==="
/usr/local/bin/architectctl watch-status

echo
echo "=== ARCHITECT STATUS ==="
/usr/local/bin/architectctl status

if [ "$SCHEDULER" = systemd ]; then
  echo
  systemctl --no-pager --full list-timers chacha-tech-watch.timer || true
fi

echo
echo "TECH_WATCH_V4_2=READY"
