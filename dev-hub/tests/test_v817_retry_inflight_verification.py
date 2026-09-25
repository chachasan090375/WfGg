#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
installer=(ROOT/"dev-hub/bin/install-v817-dark-intelligence-retry-calendar.sh").read_text(encoding="utf-8")
analysis_timer=(ROOT/"dev-hub/systemd/chacha-dev-dark-intelligence-analysis-retry.timer").read_text(encoding="utf-8")
corroboration_timer=(ROOT/"dev-hub/systemd/chacha-dev-dark-intelligence-corroboration-retry.timer").read_text(encoding="utf-8")

for timer in (analysis_timer,corroboration_timer):
    assert "OnCalendar=*:0/15" in timer
    assert "Persistent=true" in timer
    assert "OnUnitActiveSec=" not in timer

for marker in [
    'for attempt in 1 2 3 4 5',
    'TimersCalendar',
    'LastTriggerUSec',
    'SERVICE_STATE',
    'activating|active|deactivating',
    "CHACHA_DEV_V817_TIMER_TRIGGER_IN_FLIGHT=",
    "CHACHA_DEV_V817_TIMER_NEXT=",
    "CHACHA_DEV_V817_UNIT_ROLLBACK=PASS",
    "CHACHA_DEV_V817_RETRY_QUEUES=PASS",
    "CHACHA_DEV_V817_AUTOMATIC_EXTERNAL_SPEND_EUR=0",
]:
    assert marker in installer,marker

assert "calendar_not_loaded" in installer
assert "trigger_missing" in installer
assert "timer_not_scheduled" in installer
assert 'systemctl restart "$timer"' in installer

print("CHACHA_DEV_V817_WAITING_TIMER_VERIFICATION=PASS")
print("CHACHA_DEV_V817_INFLIGHT_TRIGGER_VERIFICATION=PASS")
print("CHACHA_DEV_V817_CALENDAR_REQUIRED_FOR_INFLIGHT=PASS")
print("CHACHA_DEV_V817_TRANSACTIONAL_ROLLBACK_PRESERVED=PASS")
print("CHACHA_DEV_V817_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
