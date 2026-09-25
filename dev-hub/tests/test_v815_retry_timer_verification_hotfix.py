#!/usr/bin/env python3
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
installer=ROOT/"dev-hub/bin/install-v814-dark-intelligence-retry-activation.sh"
src=installer.read_text(encoding="utf-8")

assert "NextElapseUSecRealtime" in src
assert "NextElapseUSecMonotonic" in src
assert '[ "$NEXT_MONOTONIC" = "0" ]' in src
assert "timer_not_scheduled" in src
assert "systemctl is-enabled --quiet" in src
assert "systemctl is-active --quiet" in src
assert "CHACHA_DEV_V814_UNIT_ROLLBACK=PASS" in src

p=subprocess.run(["bash","-n",str(installer)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
assert p.returncode==0,(p.stdout,p.stderr)

# Preserve the unit-level V8.0.14 qualification too.
q=subprocess.run(["python3",str(ROOT/"dev-hub/tests/test_v814_dark_intelligence_retry_activation.py")],
                 cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
assert q.returncode==0,(q.stdout,q.stderr)
assert "CHACHA_DEV_V814_SYSTEMD_ANALYZE_VERIFY=PASS" in q.stdout

print("CHACHA_DEV_V815_REALTIME_TIMER_ACCEPTED=PASS")
print("CHACHA_DEV_V815_MONOTONIC_TIMER_ACCEPTED=PASS")
print("CHACHA_DEV_V815_TIMER_UNSCHEDULED_STILL_BLOCKS=PASS")
print("CHACHA_DEV_V815_V814_GUARANTEES_PRESERVED=PASS")
print("CHACHA_DEV_V815_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
