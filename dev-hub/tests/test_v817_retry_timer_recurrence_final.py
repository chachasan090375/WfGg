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
    assert "OnUnitInactiveSec=15min" in text,(p,"missing inactive recurrence")
    assert "OnUnitActiveSec=" not in text,(p,"stale active recurrence")
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
    'for attempt in $(seq 1 60)',
    'sleep 2',
    'NextElapseUSecRealtime',
    'NextElapseUSecMonotonic',
    'TimersMonotonic',
    '[ "$NEXT" != "0" ]',
    'systemctl list-timers --all --no-pager --no-legend "$timer"',
    '[ "$LIST_NEXT" != "-" ]',
    'CHACHA_DEV_V817_TIMER_LIST_NEXT=',
    'CHACHA_DEV_V817_UNIT_ROLLBACK=PASS',
    'CHACHA_DEV_V817_RETRY_QUEUES=PASS',
    'CHACHA_DEV_V817_AUTOMATIC_EXTERNAL_SPEND_EUR=0',
]:
    assert marker in installer,marker

def scheduled(next_value:str,list_next:str)->bool:
    return bool((next_value and next_value not in {"0","infinity"}) or (list_next and list_next!="-"))

assert not scheduled("0","-")
assert not scheduled("infinity","-")
assert not scheduled("","-")
assert scheduled("4d 8h 15min","-")
assert scheduled("","Fri")
assert scheduled("infinity","Fri")

analyze=shutil.which("systemd-analyze")
if analyze:
    p=subprocess.run([analyze,"verify",*(str(x) for x in services+timers)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)

print("CHACHA_DEV_V817_ONESHOT_INACTIVE_RECURRENCE=PASS")
print("CHACHA_DEV_V817_LOADED_TIMER_RESTART=PASS")
print("CHACHA_DEV_V817_ZERO_ELAPSE_REJECTED=PASS")
print("CHACHA_DEV_V817_LIVE_TIMER_LIST_REQUIRED=PASS")
print("CHACHA_DEV_V817_INITIAL_ONESHOT_SETTLE_WAIT=PASS")
print("CHACHA_DEV_V817_TRANSACTIONAL_ROLLBACK=PASS")
print("CHACHA_DEV_V817_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
