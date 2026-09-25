#!/usr/bin/env python3
from pathlib import Path
import shutil,subprocess,re

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

installer=(BIN/"install-v817-dark-intelligence-retry-activation.sh").read_text(encoding="utf-8")
for marker in [
    'systemctl restart "$timer"',
    'for attempt in $(seq 1 45)',
    'sleep 2',
    'systemctl list-timers --all --no-pager --no-legend "$timer"',
    'timer_has_no_next',
    'CHACHA_DEV_V817_TIMER_LISTED=',
    'CHACHA_DEV_V817_TIMER_NEXT=',
    'CHACHA_DEV_V817_UNIT_ROLLBACK=PASS',
    'CHACHA_DEV_V817_RETRY_QUEUES=PASS',
    'CHACHA_DEV_V817_AUTOMATIC_EXTERNAL_SPEND_EUR=0',
]:
    assert marker in installer,marker

def row_has_next(row:str)->bool:
    if not row.strip():
        return False
    return re.search(r'^\s*-\s+-\s+',row) is None

# Representative list-timers rows from the VPS:
assert row_has_next("Fri 2026-09-25 16:34:18 UTC 14min Fri 2026-09-25 16:19:18 UTC 1s ago chacha-v816-probe.timer chacha-v816-probe.service")
assert not row_has_next("- - Fri 2026-09-25 16:06:57 UTC - chacha-dev-dark-intelligence-analysis-retry.timer chacha-dev-dark-intelligence-analysis-retry.service")

analyze=shutil.which("systemd-analyze")
if analyze:
    p=subprocess.run([analyze,"verify",*(str(x) for x in services+timers)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)

print("CHACHA_DEV_V817_ONESHOT_INACTIVE_RECURRENCE=PASS")
print("CHACHA_DEV_V817_STALE_ACTIVE_TIMER_REMOVED=PASS")
print("CHACHA_DEV_V817_TIMER_RESTART_REQUIRED=PASS")
print("CHACHA_DEV_V817_REAL_NEXT_REQUIRED=PASS")
print("CHACHA_DEV_V817_TRANSACTIONAL_ROLLBACK=PASS")
print("CHACHA_DEV_V817_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
