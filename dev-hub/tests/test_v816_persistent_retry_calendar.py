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
for p in timers:
    text=p.read_text(encoding="utf-8")
    assert "OnCalendar=*:0/15" in text,(p,"calendar missing")
    assert "Persistent=true" in text
    assert "OnUnitActiveSec=" not in text
    assert "OnBootSec=" not in text
    assert "WantedBy=timers.target" in text

installer=(BIN/"install-v816-dark-intelligence-retry-calendar.sh").read_text(encoding="utf-8")
assert 'systemctl enable "$timer"' in installer
assert 'systemctl restart "$timer"' in installer
assert "NextElapseUSecRealtime" in installer
assert "NextElapseUSecMonotonic" in installer
assert "CHACHA_DEV_V816_UNIT_ROLLBACK=PASS" in installer
assert "CHACHA_DEV_V816_RETRY_QUEUES=PASS" in installer
assert "CHACHA_DEV_V816_AUTOMATIC_EXTERNAL_SPEND_EUR=0" in installer

analyze=shutil.which("systemd-analyze")
if analyze:
    p=subprocess.run([analyze,"calendar","*:0/15"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    assert "Next elapse" in p.stdout or "next elapse" in p.stdout.lower(),p.stdout

print("CHACHA_DEV_V816_RECURRING_CALENDAR_TIMER=PASS")
print("CHACHA_DEV_V816_NO_ELAPSED_MONOTONIC_TRAP=PASS")
print("CHACHA_DEV_V816_TIMER_RESTART_ON_INSTALL=PASS")
print("CHACHA_DEV_V816_TRANSACTIONAL_ROLLBACK_PRESERVED=PASS")
print("CHACHA_DEV_V816_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
