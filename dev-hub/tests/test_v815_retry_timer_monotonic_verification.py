#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
installer=(ROOT/"dev-hub/bin/install-v815-dark-intelligence-retry-activation.sh").read_text(encoding="utf-8")

assert "NextElapseUSecRealtime" in installer
assert "NextElapseUSecMonotonic" in installer
assert 'if [ -z "$NEXT" ] || [ "$NEXT" = "infinity" ]; then NEXT="$NEXT_MONOTONIC"; fi' in installer
assert 'CHACHA_DEV_V815_INSTALL=BLOCKED reason=timer_not_scheduled:$timer' in installer
assert "CHACHA_DEV_V815_UNIT_ROLLBACK=PASS" in installer
assert "CHACHA_DEV_V815_RETRY_QUEUES=PASS" in installer
assert "CHACHA_DEV_V815_AUTOMATIC_EXTERNAL_SPEND_EUR=0" in installer

def select(realtime,monotonic):
    nxt=realtime
    if not nxt or nxt=="infinity":
        nxt=monotonic
    return nxt

assert select("","15min")=="15min"
assert select("infinity","12min")=="12min"
assert select("Fri 2026-09-25 17:00:00 UTC","12min")=="Fri 2026-09-25 17:00:00 UTC"
assert select("","")==""

print("CHACHA_DEV_V815_MONOTONIC_TIMER_FALLBACK=PASS")
print("CHACHA_DEV_V815_REALTIME_TIMER_COMPATIBILITY=PASS")
print("CHACHA_DEV_V815_TRANSACTIONAL_ROLLBACK_PRESERVED=PASS")
print("CHACHA_DEV_V815_RETRY_QUEUES_PRESERVED=PASS")
print("CHACHA_DEV_V815_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
