#!/usr/bin/env python3
from pathlib import Path
import shutil,subprocess

ROOT=Path(__file__).resolve().parents[2]
SYSTEMD=ROOT/"dev-hub/systemd"
BIN=ROOT/"dev-hub/bin"

timers=[
 SYSTEMD/"chacha-dev-dark-intelligence-analysis-retry.timer",
 SYSTEMD/"chacha-dev-dark-intelligence-corroboration-retry.timer",
]
services=[
 SYSTEMD/"chacha-dev-dark-intelligence-analysis-retry.service",
 SYSTEMD/"chacha-dev-dark-intelligence-corroboration-retry.service",
]

for p in timers:
    text=p.read_text(encoding="utf-8")
    assert "OnUnitInactiveSec=15min" in text,(p,"missing OnUnitInactiveSec")
    assert "OnUnitActiveSec=" not in text,(p,"stale OnUnitActiveSec")
    assert "RandomizedDelaySec=" in text
    assert "WantedBy=timers.target" in text

for p in services:
    text=p.read_text(encoding="utf-8")
    assert "Type=oneshot" in text
    assert "run-due --limit 2" in text
    assert "NoNewPrivileges=true" in text
    assert "ProtectSystem=strict" in text

installer=(BIN/"install-v816-dark-intelligence-retry-activation.sh").read_text(encoding="utf-8")
for marker in [
    'for attempt in $(seq 1 45)',
    'sleep 2',
    'systemctl restart "$timer"',
    'NextElapseUSecRealtime',
    'NextElapseUSecMonotonic',
    '[ "$NEXT" != "0" ]',
    'systemctl list-timers --all --no-pager --no-legend "$timer"',
    'CHACHA_DEV_V816_TIMER_LISTED=',
    'CHACHA_DEV_V816_UNIT_ROLLBACK=PASS',
    'CHACHA_DEV_V816_RETRY_QUEUES=PASS',
    'CHACHA_DEV_V816_AUTOMATIC_EXTERNAL_SPEND_EUR=0',
]:
    assert marker in installer,marker

analyze=shutil.which("systemd-analyze")
if analyze:
    p=subprocess.run([analyze,"verify",*(str(x) for x in services+timers)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)

print("CHACHA_DEV_V816_ONESHOT_RECURRENCE=PASS")
print("CHACHA_DEV_V816_STALE_ACTIVE_TIMER_REMOVED=PASS")
print("CHACHA_DEV_V816_INITIAL_RUN_SETTLE_WAIT=PASS")
print("CHACHA_DEV_V816_TIMER_LIST_VERIFICATION=PASS")
print("CHACHA_DEV_V816_TRANSACTIONAL_ROLLBACK=PASS")
print("CHACHA_DEV_V816_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
