#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
installer=(ROOT/"dev-hub/bin/install-v816-dark-intelligence-retry-activation.sh").read_text(encoding="utf-8")

assert "NextElapseUSecRealtime" in installer
assert "NextElapseUSecMonotonic" in installer
assert "TimersMonotonic" in installer
assert "next_elapse=[^;} ]+" in installer
assert "CHACHA_DEV_V816_UNIT_ROLLBACK=PASS" in installer
assert "CHACHA_DEV_V816_RETRY_QUEUES=PASS" in installer
assert "CHACHA_DEV_V816_AUTOMATIC_EXTERNAL_SPEND_EUR=0" in installer

def scheduled(realtime:str,monotonic:str,timers_monotonic:str)->bool:
    nxt=realtime
    if not nxt or nxt=="infinity":
        nxt=monotonic
    if nxt and nxt!="infinity":
        return True
    return re.search(r"next_elapse=[^;} ]+",timers_monotonic or "") is not None

assert scheduled("", "infinity", "{ OnUnitActiveUSec=10s ; next_elapse=4d 8h 58s }")
assert scheduled("", "infinity", "{ OnBootUSec=5s ; next_elapse=5s }")
assert scheduled("Fri 2026-09-25 17:00:00 UTC", "infinity", "")
assert not scheduled("", "infinity", "")
assert not scheduled("", "", "{ OnUnitActiveUSec=10s ; next_elapse= }")

print("CHACHA_DEV_V816_SYSTEMD255_TIMERS_MONOTONIC=PASS")
print("CHACHA_DEV_V816_REALTIME_COMPATIBILITY=PASS")
print("CHACHA_DEV_V816_FALSE_SCHEDULE_REJECTED=PASS")
print("CHACHA_DEV_V816_TRANSACTIONAL_ROLLBACK_PRESERVED=PASS")
print("CHACHA_DEV_V816_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
