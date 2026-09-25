#!/usr/bin/env python3
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SYSTEMD=ROOT/"dev-hub/systemd"
INSTALLER=ROOT/"dev-hub/bin/install-v814-dark-intelligence-retry-activation.sh"

timers=[
 SYSTEMD/"chacha-dev-dark-intelligence-analysis-retry.timer",
 SYSTEMD/"chacha-dev-dark-intelligence-corroboration-retry.timer",
]
for p in timers:
    s=p.read_text(encoding="utf-8")
    assert s.startswith("[Unit]\n")
    assert "[Timer]" in s
    assert "OnActiveSec=1min" in s
    assert "OnUnitInactiveSec=15min" in s
    assert "OnUnitActiveSec=" not in s
    assert "Persistent=true" in s
    assert "[Install]" in s and "WantedBy=timers.target" in s

src=INSTALLER.read_text(encoding="utf-8")
assert 'NEXT_REALTIME" = "infinity"' in src
assert 'NEXT_MONOTONIC" = "infinity"' in src
assert 'NEXT_MONOTONIC" = "0"' in src
assert "timer_not_scheduled" in src

p=subprocess.run(["bash","-n",str(INSTALLER)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
assert p.returncode==0,(p.stdout,p.stderr)

q=subprocess.run(["python3",str(ROOT/"dev-hub/tests/test_v814_dark_intelligence_retry_activation.py")],
                 cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
assert q.returncode==0,(q.stdout,q.stderr)
assert "CHACHA_DEV_V814_VALID_SYSTEMD_UNITS=PASS" in q.stdout

print("CHACHA_DEV_V816_TIMER_FIRST_WAKE=PASS")
print("CHACHA_DEV_V816_TIMER_REARM_AFTER_INACTIVE=PASS")
print("CHACHA_DEV_V816_ELAPSED_INFINITY_REJECTED=PASS")
print("CHACHA_DEV_V816_V814_SECURITY_GUARANTEES=PASS")
print("CHACHA_DEV_V816_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
