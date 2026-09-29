from __future__ import annotations

from typing import Any

from .operations import run_governed_operation
from .server import POLICY, mcp


@mcp.tool()
def governed_operation(operation_id: str, cwd: str | None = None, service: str | None = None) -> dict[str, Any]:
    """Execute one fixed read-only operation behind STOP, single-writer lease and Guardian PRE/POST."""
    return run_governed_operation(POLICY, operation_id, cwd=cwd, service=service)


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host=str(POLICY.raw.get("bind_host", "127.0.0.1")),
        port=int(POLICY.raw.get("port", 8765)),
        streamable_http_path=str(POLICY.raw.get("mcp_path", "/mcp")),
        json_response=True,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
