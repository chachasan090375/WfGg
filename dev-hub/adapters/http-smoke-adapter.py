#!/usr/bin/env python3
"""ChaCha DEV HUB HTTP Smoke Adapter V1.

Read-only runtime adapter for deterministic HTTP GET/HEAD smoke checks. Input is
a chacha.dev/dispatch-envelope/v1 JSON object on stdin; output is exactly one
chacha.dev/task-result/v1 JSON object on stdout. The adapter never uses a shell,
never follows redirects, never accepts inline credentials, requires an explicit
host allowlist, and never self-verifies its own result.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
ADAPTER_ID = "http-smoke-adapter"
PROVIDER_ID = "http-smoke"
ALLOWED_METHODS = {"GET", "HEAD"}
DEFAULT_MAX_BYTES = 65536
ABSOLUTE_MAX_BYTES = 262144
DEFAULT_TIMEOUT = 10
ABSOLUTE_MAX_TIMEOUT = 30


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def safe_source(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def allowed_hosts() -> set[str]:
    raw = os.environ.get("CHACHA_HTTP_SMOKE_ALLOWED_HOSTS", "")
    return {item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip()}


def result(request: dict[str, Any], status: str, summary: str,
           evidence: list[dict[str, Any]] | None = None,
           outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    task = request.get("task") if isinstance(request.get("task"), dict) else {}
    return {
        "schema": OUTPUT_SCHEMA,
        "project": str(request.get("project") or "unknown"),
        "task_id": str(task.get("id") or "unknown"),
        "status": status,
        "producer": ADAPTER_ID,
        "observed_at": now_iso(),
        "summary": summary,
        "evidence": evidence or [],
        "verification": {
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "none",
            "observed_at": now_iso(),
            "notes": "Runtime adapters cannot self-verify; independent verification is required."
        },
        "outputs": outputs or [],
    }


def emit(payload: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


def blocked(request: dict[str, Any], reason: str, source: str = "adapter-policy") -> int:
    evidence = [{
        "kind": "report",
        "source": source,
        "digest": sha256_bytes(reason.encode("utf-8")),
        "details": {"reason": reason},
    }]
    return emit(result(request, "BLOCKED", reason, evidence))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def validate_request(request: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, "INPUT_SCHEMA_INVALID"
    task = request.get("task")
    if not isinstance(task, dict) or not task.get("id"):
        return None, "TASK_ID_MISSING"
    if task.get("permission") != "read":
        return None, "HTTP_SMOKE_REQUIRES_READ_PERMISSION"
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or not any(
        isinstance(item, dict)
        and item.get("provider") == PROVIDER_ID
        and item.get("adapter") == ADAPTER_ID
        for item in bindings
    ):
        return None, "HTTP_SMOKE_BINDING_MISSING"
    metadata = request.get("metadata")
    smoke = metadata.get("http_smoke") if isinstance(metadata, dict) else None
    if not isinstance(smoke, dict):
        return None, "HTTP_SMOKE_METADATA_MISSING"
    return smoke, None


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", f"INPUT_JSON_INVALID:{type(exc).__name__}"), 2)
    if not isinstance(request, dict):
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", "INPUT_ROOT_NOT_OBJECT"), 2)

    smoke, error = validate_request(request)
    if error:
        return blocked(request, error)
    assert smoke is not None

    url = str(smoke.get("url") or "")
    method = str(smoke.get("method") or "GET").upper()
    if method not in ALLOWED_METHODS:
        return blocked(request, f"HTTP_METHOD_NOT_ALLOWED:{method}")

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return blocked(request, "HTTP_URL_INVALID")
    if parsed.username is not None or parsed.password is not None:
        return blocked(request, "INLINE_CREDENTIALS_FORBIDDEN")

    host = parsed.hostname.lower().rstrip(".")
    hosts = allowed_hosts()
    if not hosts:
        return blocked(request, "HTTP_HOST_ALLOWLIST_EMPTY")
    if host not in hosts:
        return blocked(request, f"HTTP_HOST_NOT_ALLOWED:{host}", safe_source(url))

    try:
        expected = [int(x) for x in (smoke.get("expected_status") or [200])]
    except Exception:
        return blocked(request, "EXPECTED_STATUS_INVALID", safe_source(url))
    if not expected or any(code < 100 or code > 599 for code in expected):
        return blocked(request, "EXPECTED_STATUS_INVALID", safe_source(url))

    try:
        requested_max = int(smoke.get("max_bytes") or DEFAULT_MAX_BYTES)
    except Exception:
        return blocked(request, "MAX_BYTES_INVALID", safe_source(url))
    max_bytes = min(max(requested_max, 1), ABSOLUTE_MAX_BYTES)

    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    try:
        requested_timeout = int(policy.get("timeout_seconds") or DEFAULT_TIMEOUT)
    except Exception:
        requested_timeout = DEFAULT_TIMEOUT
    timeout = min(max(requested_timeout, 1), ABSOLUTE_MAX_TIMEOUT)

    clean_source = safe_source(url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    http_request = urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": "ChaCha-DEV-HUB-HTTP-Smoke/1"},
    )
    started = time.monotonic()
    status_code: int | None = None
    body = b""
    content_type: str | None = None
    transport_error: str | None = None

    try:
        with opener.open(http_request, timeout=timeout) as response:
            status_code = int(response.status)
            content_type = response.headers.get("Content-Type")
            body = response.read(max_bytes + 1) if method != "HEAD" else b""
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        content_type = exc.headers.get("Content-Type") if exc.headers else None
        try:
            body = exc.read(max_bytes + 1) if method != "HEAD" else b""
        except Exception:
            body = b""
    except urllib.error.URLError as exc:
        transport_error = type(exc.reason).__name__ if getattr(exc, "reason", None) is not None else "URLError"
    except Exception as exc:
        transport_error = type(exc).__name__

    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    if transport_error:
        digest = sha256_bytes(transport_error.encode("utf-8"))
        evidence = [{
            "kind": "url",
            "source": clean_source,
            "digest": digest,
            "details": {"method": method, "elapsed_ms": elapsed_ms, "transport_error": transport_error},
        }]
        return emit(result(request, "FAILED", "HTTP_SMOKE_TRANSPORT_FAILED", evidence))

    oversized = len(body) > max_bytes
    sampled = body[:max_bytes]
    evidence = [{
        "kind": "url",
        "source": clean_source,
        "digest": sha256_bytes(sampled),
        "details": {
            "method": method,
            "http_status": status_code,
            "expected_status": expected,
            "elapsed_ms": elapsed_ms,
            "bytes_sampled": len(sampled),
            "response_too_large": oversized,
            "content_type": content_type,
            "target_host": host,
        },
    }]
    output = [{
        "type": "artifact",
        "id": "http-smoke-result",
        "status": "OK" if status_code in expected and not oversized else "PARTIAL",
        "reason": f"HTTP {status_code}; expected={expected}; oversized={oversized}",
    }]

    if oversized:
        return emit(result(request, "FAILED", "HTTP_SMOKE_RESPONSE_TOO_LARGE", evidence, output))
    if status_code not in expected:
        return emit(result(request, "FAILED", f"HTTP_SMOKE_UNEXPECTED_STATUS:{status_code}", evidence, output))
    return emit(result(request, "OK", f"HTTP_SMOKE_OK:{status_code}", evidence, output))


if __name__ == "__main__":
    raise SystemExit(main())
