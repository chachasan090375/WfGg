#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "dev-hub/bin/emergency-control-bridge.py"
INSTALLER = ROOT / "dev-hub/bin/install-emergency-control-bridge.sh"
UNIT = ROOT / "dev-hub/systemd/chacha-dev-emergency-control-bridge.service"
CONFIG = ROOT / "dev-hub/config/emergency-control-bridge.v1.json"

with tempfile.TemporaryDirectory(prefix="chacha-emergency-bridge-") as td:
    td = Path(td)
    command = td / "command.json"
    state = td / "bridge-state.json"
    emergency_state = td / "emergency-state.json"
    calls = td / "calls.txt"
    fake_controller = td / "controller.py"

    fake_controller.write_text(
        """#!/usr/bin/env python3
import json,sys,time
from pathlib import Path
args=sys.argv
reason=args[args.index('--reason')+1]
actor=args[args.index('--actor')+1]
Path(%r).open('a',encoding='utf-8').write(reason+'|'+actor+'\\n')
print(json.dumps({'active':True,'activated_at':'2026-09-22T14:00:00Z','reason':reason,'actor':actor}))
""" % str(calls),
        encoding="utf-8",
    )
    fake_controller.chmod(0o755)

    def write(action: str, request_id: str, reason: str) -> None:
        command.write_text(
            json.dumps(
                {
                    "schema": "chacha.dev/emergency-stop-command/v1",
                    "action": action,
                    "request_id": request_id,
                    "issued_at": "2026-09-22T14:00:00Z",
                    "actor": "test",
                    "reason": reason,
                }
            ),
            encoding="utf-8",
        )

    def run(*extra: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(BRIDGE),
                "--command-file",
                str(command),
                "--state",
                str(state),
                "--emergency-state",
                str(emergency_state),
                "--controller",
                str(fake_controller),
                *extra,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=check,
        )

    write("NOOP", "baseline-v65-test", "neutral")
    out = run("--baseline")
    assert "BASELINE=PASS" in out.stdout, out.stdout
    assert not calls.exists()

    write("STOP", "stop-001", "operator requested emergency stop")
    out = run("--once")
    assert "STOP_APPLIED" in out.stdout, out.stdout
    lines = calls.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, lines
    assert "chatgpt-emergency-control-bridge" in lines[0], lines

    out = run("--once")
    assert "UNCHANGED" in out.stdout, out.stdout
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1

    write("NOOP", "neutral-002", "neutral after stop; does not reset latch")
    out = run("--once")
    assert "NOOP" in out.stdout, out.stdout
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1

    write("STOP", "stop-001", "replay with changed payload")
    out = run("--once")
    assert "REPLAY_IGNORED" in out.stdout, out.stdout
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1

    write("RESET", "reset-001", "must never be accepted remotely")
    out = run("--once", check=False)
    assert out.returncode != 0
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1

    write("STOP", "pending-stop", "baseline must never swallow a live stop")
    out = run("--baseline", check=False)
    assert out.returncode != 0

cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
assert cfg["authority"]["allowed_remote_actions"] == ["STOP"]
assert cfg["authority"]["remote_reset_allowed"] is False
assert cfg["authority"]["remote_resume_allowed"] is False
assert cfg["economics"]["automatic_external_spend_eur"] == 0

src = BRIDGE.read_text(encoding="utf-8")
unit = UNIT.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")
assert "chacha-emergency-control" in src
assert "chacha-emergency-control" in unit
assert "/opt/chacha-dev/emergency-bridge/current/emergency-stop-controller.py" in unit
assert "--poll-seconds 10" in unit
assert "systemctl restart chacha-dev-emergency-control-bridge.service" in installer
assert "REMOTE_RESET=NO" in installer

print("CHACHA_DEV_V65_EMERGENCY_BRIDGE_ACTIVATION_ONLY=PASS")
print("CHACHA_DEV_V65_EMERGENCY_BRIDGE_REPLAY_PROTECTION=PASS")
print("CHACHA_DEV_V65_EMERGENCY_BRIDGE_OUT_OF_BAND=PASS")
print("CHACHA_DEV_V65_EMERGENCY_BRIDGE_ZERO_SPEND=PASS")
