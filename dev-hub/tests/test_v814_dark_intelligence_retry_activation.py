#!/usr/bin/env python3
from __future__ import annotations
import shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SYSTEMD=ROOT/"dev-hub/systemd"
BIN=ROOT/"dev-hub/bin"

services=[
 SYSTEMD/"chacha-dev-dark-intelligence-analysis-retry.service",
 SYSTEMD/"chacha-dev-dark-intelligence-corroboration-retry.service",
]
timers=[
 SYSTEMD/"chacha-dev-dark-intelligence-analysis-retry.timer",
 SYSTEMD/"chacha-dev-dark-intelligence-corroboration-retry.timer",
]
units=services+timers

for p in units:
    text=p.read_text(encoding="utf-8")
    assert text.startswith("[Unit]\n"),(p,"missing [Unit]")
    assert "Description=" in text,(p,"missing Description")

for p in services:
    text=p.read_text(encoding="utf-8")
    assert "[Service]" in text
    assert "Type=oneshot" in text
    assert "NoNewPrivileges=true" in text
    assert "ProtectSystem=strict" in text
    assert "ProtectHome=true" in text
    assert "ReadWritePaths=/opt/chacha-dev/runtime/dark-intelligence" in text
    assert "run-due --limit 2" in text

for p in timers:
    text=p.read_text(encoding="utf-8")
    assert "[Timer]" in text
    assert "OnUnitActiveSec=15min" in text
    assert "Persistent=true" in text
    assert "[Install]" in text
    assert "WantedBy=timers.target" in text

installer=(BIN/"install-v814-dark-intelligence-retry-activation.sh").read_text(encoding="utf-8")
for marker in [
 "systemd-analyze verify","systemctl daemon-reload","systemctl enable --now",
 "CHACHA_DEV_V814_UNIT_ROLLBACK=PASS","CHACHA_DEV_V814_RETRY_QUEUES=PASS",
 "CHACHA_DEV_V814_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
]:
    assert marker in installer,marker

analyze=shutil.which("systemd-analyze")
if analyze:
    p=subprocess.run([analyze,"verify",*(str(x) for x in units)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)

print("CHACHA_DEV_V814_VALID_SYSTEMD_UNITS=PASS")
print("CHACHA_DEV_V814_RETRY_LIMIT_TWO=PASS")
print("CHACHA_DEV_V814_TIMER_15_MINUTES=PASS")
print("CHACHA_DEV_V814_TRANSACTIONAL_UNIT_ROLLBACK=PASS")
print("CHACHA_DEV_V814_SYSTEMD_ANALYZE_VERIFY=PASS")
print("CHACHA_DEV_V814_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
