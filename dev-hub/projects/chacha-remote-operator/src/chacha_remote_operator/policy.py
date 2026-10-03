from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PolicyError(RuntimeError):
    pass


V02_SCHEMA = "chacha.dev/chacha-remote-operator-policy/v2"
V03_SCHEMA = "chacha.dev/chacha-remote-operator-policy/v3"
V02_OPERATION_IDS = (
    "git_status",
    "git_head",
    "git_tree",
    "service_is_active",
    "service_is_enabled",
    "uptime",
    "free_bytes",
    "uname",
)
V03_OPERATION_IDS = V02_OPERATION_IDS + ("guardian_check_event",)


@dataclass(frozen=True)
class OperatorPolicy:
    raw: dict[str, Any]
    source: Path

    @property
    def stop_state(self) -> Path:
        return Path(str(self.raw["canonical_stop_state"]))

    @property
    def audit_log(self) -> Path:
        return Path(str(self.raw["audit_log"]))

    @property
    def runtime_root(self) -> Path:
        configured = str(self.raw.get("runtime_root") or "").strip()
        return Path(configured).resolve(strict=False) if configured else self.audit_log.parent.resolve(strict=False)

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return tuple(Path(str(x)).resolve(strict=False) for x in self.raw.get("allowed_roots", []))

    @property
    def is_v02(self) -> bool:
        return self.raw.get("schema") in {V02_SCHEMA, V03_SCHEMA}

    def stop_active(self) -> bool:
        try:
            data = json.loads(self.stop_state.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "active" not in data or not isinstance(data["active"], bool):
                raise PolicyError("STOP_STATE_INVALID")
            return data["active"]
        except FileNotFoundError as exc:
            if self.is_v02:
                raise PolicyError("STOP_STATE_MISSING") from exc
            return False
        except PolicyError:
            raise
        except Exception as exc:
            raise PolicyError("STOP_STATE_UNREADABLE") from exc

    def require_operational(self) -> None:
        if self.stop_active():
            raise PolicyError("CANONICAL_STOP_ACTIVE")

    def resolve_read_path(self, raw_path: str) -> Path:
        if not raw_path or "\x00" in raw_path:
            raise PolicyError("PATH_INVALID")
        candidate = Path(raw_path).expanduser().resolve(strict=False)
        rendered = candidate.as_posix()
        for fragment in self.raw.get("blocked_path_fragments", []):
            if str(fragment) in rendered:
                raise PolicyError("PATH_SECRET_CLASS_BLOCKED")
        for root in self.allowed_roots:
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
        raise PolicyError("PATH_OUTSIDE_ALLOWLIST")

    def service_allowed(self, name: str) -> bool:
        return name in set(str(x) for x in self.raw.get("service_status_allowlist", []))

    def governed_operation_allowed(self, operation_id: str) -> bool:
        if self.raw.get("governed_operations_enabled") is not True:
            return False
        return operation_id in set(str(x) for x in self.raw.get("governed_operation_allowlist", []))

    # Legacy V0.1 raw command surface remains disabled in V0.2. This method exists only
    # for compatibility with the published V0.1 command_run tool.
    def command_profile(self, argv: list[str], cwd: str | None = None) -> dict[str, Any]:
        if self.raw.get("command_execution_enabled") is not True:
            raise PolicyError("COMMAND_EXECUTION_DISABLED")
        if not argv or len(argv) > 16 or any(not isinstance(x, str) or not x or "\x00" in x or len(x) > 512 for x in argv):
            raise PolicyError("COMMAND_ARGV_INVALID")
        if cwd is not None:
            self.resolve_read_path(cwd)
        for prefix in self.raw.get("command_allowlist", []):
            p = [str(x) for x in prefix]
            if argv[: len(p)] == p:
                return {"id": "legacy-prefix", "executable": argv[0]}
        raise PolicyError("COMMAND_NOT_ALLOWLISTED")

    def command_allowed(self, argv: list[str], cwd: str | None = None) -> bool:
        try:
            self.command_profile(argv, cwd)
            return True
        except PolicyError:
            return False


def default_policy_path() -> Path:
    configured = os.environ.get("CHACHA_REMOTE_OPERATOR_POLICY", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "config" / "policy.v1.json"


def load_policy(path: Path | None = None) -> OperatorPolicy:
    source = (path or default_policy_path()).resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema") not in {
        "chacha.dev/chacha-remote-operator-policy/v1",
        V02_SCHEMA,
        V03_SCHEMA,
    }:
        raise PolicyError("POLICY_SCHEMA_INVALID")
    if float(data.get("automatic_external_spend_eur", -1)) != 0:
        raise PolicyError("NONZERO_AUTOMATIC_EXTERNAL_SPEND_FORBIDDEN")
    if data.get("destructive_operations_enabled") is not False:
        raise PolicyError("DESTRUCTIVE_OPERATIONS_FORBIDDEN")
    if data.get("file_write_enabled") is not False:
        raise PolicyError("FILE_WRITE_FORBIDDEN")
    if data.get("service_mutation_enabled") is not False:
        raise PolicyError("SERVICE_MUTATION_FORBIDDEN")
    if data.get("git_mutation_enabled") is not False:
        raise PolicyError("GIT_MUTATION_FORBIDDEN")
    if data.get("schema") in {V02_SCHEMA, V03_SCHEMA}:
        if data.get("fail_closed") is not True:
            raise PolicyError("V02_FAIL_CLOSED_REQUIRED")
        if data.get("bind_host") != "127.0.0.1":
            raise PolicyError("V02_LOCALHOST_ONLY_REQUIRED")
        if data.get("external_network_access_enabled") is not False:
            raise PolicyError("V02_EXTERNAL_NETWORK_MUST_STAY_DISABLED")
        if data.get("guardian_required_for_governed_operations") is not True:
            raise PolicyError("V02_GUARDIAN_REQUIRED")
        if data.get("single_writer_command_lease") is not True:
            raise PolicyError("V02_SINGLE_WRITER_LEASE_REQUIRED")
        if data.get("command_execution_enabled") is not False:
            raise PolicyError("V02_RAW_COMMAND_EXECUTION_MUST_STAY_DISABLED")
        operations = [str(x) for x in data.get("governed_operation_allowlist", [])]
        expected = V03_OPERATION_IDS if data.get("schema") == V03_SCHEMA else V02_OPERATION_IDS
        if len(operations) != len(expected) or set(operations) != set(expected):
            raise PolicyError("GOVERNED_OPERATION_ALLOWLIST_MUST_BE_EXACT")
        if data.get("governed_operations_enabled") is not True:
            raise PolicyError("V02_GOVERNED_OPERATIONS_REQUIRED")
        stop_path = Path(str(data.get("canonical_stop_state") or ""))
        if not stop_path.is_absolute():
            raise PolicyError("V02_CANONICAL_STOP_PATH_INVALID")
    return OperatorPolicy(data, source)
