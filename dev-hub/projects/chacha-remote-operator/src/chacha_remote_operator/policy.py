from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PolicyError(RuntimeError):
    pass


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

    def stop_active(self) -> bool:
        try:
            data = json.loads(self.stop_state.read_text(encoding="utf-8"))
            return bool(data.get("active"))
        except FileNotFoundError:
            return False
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

    def command_profile(self, argv: list[str], cwd: str | None = None) -> dict[str, Any]:
        if self.raw.get("command_execution_enabled") is not True:
            raise PolicyError("COMMAND_EXECUTION_DISABLED")
        if not argv or len(argv) > 16 or any(not isinstance(x, str) or not x or "\x00" in x or len(x) > 512 for x in argv):
            raise PolicyError("COMMAND_ARGV_INVALID")
        if cwd is not None:
            self.resolve_read_path(cwd)
        profiles = self.raw.get("command_profiles") or []
        if profiles:
            executable = argv[0]
            args = argv[1:]
            for raw_profile in profiles:
                profile = dict(raw_profile)
                if executable != str(profile.get("executable") or ""):
                    continue
                if profile.get("cwd_required") is True and cwd is None:
                    continue
                exact = profile.get("exact_args")
                if exact is not None:
                    if args == [str(x) for x in exact]:
                        return profile
                    continue
                prefix = [str(x) for x in (profile.get("prefix_args") or [])]
                if args[: len(prefix)] != prefix:
                    continue
                tail = args[len(prefix):]
                if profile.get("service_argument_after_prefix") is True:
                    if len(tail) == 1 and self.service_allowed(tail[0]):
                        return profile
                    continue
                allowed_tail = set(str(x) for x in (profile.get("allowed_trailing_args") or []))
                if all(x in allowed_tail for x in tail):
                    return profile
            raise PolicyError("COMMAND_NOT_ALLOWLISTED")

        # V0.1 compatibility only. V0.2 policies must use command_profiles.
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
        "chacha.dev/chacha-remote-operator-policy/v2",
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
    if data.get("schema") == "chacha.dev/chacha-remote-operator-policy/v2":
        if data.get("guardian_required_for_command_execution") is not True:
            raise PolicyError("V02_GUARDIAN_REQUIRED")
        if not data.get("command_profiles"):
            raise PolicyError("V02_COMMAND_PROFILES_REQUIRED")
    return OperatorPolicy(data, source)
