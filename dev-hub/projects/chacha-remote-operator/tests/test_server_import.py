from pathlib import Path
import tomllib

from chacha_remote_operator import __version__
from chacha_remote_operator.server import POLICY, mcp


def test_server_import_and_policy_binding() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared_version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert __version__ == declared_version
    assert mcp is not None
    assert POLICY.raw["schema"] == "chacha.dev/chacha-remote-operator-policy/v1"
    assert POLICY.raw["mode"] == "PILOT_READ_ONLY"
    assert POLICY.raw["bind_host"] == "127.0.0.1"
    assert POLICY.raw["command_execution_enabled"] is False
    assert POLICY.raw["destructive_operations_enabled"] is False
    assert float(POLICY.raw["automatic_external_spend_eur"]) == 0
