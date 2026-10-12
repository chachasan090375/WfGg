"""Common, fail-closed interpretation of a Guardian client response."""
from __future__ import annotations


def response_blockers(value: object, returncode: int) -> list[str]:
    if not isinstance(value, dict):
        return ["GUARDIAN_RESPONSE_INVALID"]
    verdict = str(value.get("verdict") or value.get("status") or "UNAVAILABLE")
    if verdict in {"BLOCK", "CRITICAL"}:
        return ["GUARDIAN_" + verdict]
    if returncode != 0:
        return ["GUARDIAN_CLIENT_EXIT_STATUS:" + str(returncode)]
    if verdict not in {"PASS", "WARNING"}:
        return ["GUARDIAN_UNAVAILABLE_FAIL_CLOSED"]
    for key in ("remediation_required", "stop_recommended"):
        if key in value and not isinstance(value[key], bool):
            return ["GUARDIAN_DIRECTIVE_FLAG_INVALID:" + key]
        if value.get(key) is True:
            return ["GUARDIAN_REMEDIATION_OR_STOP_REQUIRED"]
    return []
