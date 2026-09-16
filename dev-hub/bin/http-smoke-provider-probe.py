#!/usr/bin/env python3
"""Independent provider-health probe for the http-smoke runtime.

The probe never invokes the adapter itself. It independently verifies that the
configured adapter executable exists and is executable, then performs a
loopback-only HTTP request using Python's urllib stack. Output conforms to
chacha.dev/provider-probe-result/v1 and is suitable for Platform Evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCHEMA = "chacha.dev/provider-probe-result/v1"
PROVIDER = "http-smoke"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def safe_source(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path or "/", "", ""))


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent HTTP smoke provider health probe")
    parser.add_argument("--url", required=True)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    parsed = urlsplit(args.url)
    checked_at = now_iso()
    blockers: list[str] = []
    status_code = None
    body = b""
    latency_ms = None

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        blockers.append("PROBE_URL_INVALID")
    elif not is_loopback(parsed.hostname):
        blockers.append("PROBE_TARGET_NOT_LOOPBACK")

    executable_digest = None
    if not args.executable.is_absolute():
        blockers.append("EXECUTABLE_PATH_NOT_ABSOLUTE")
    elif not args.executable.is_file():
        blockers.append("EXECUTABLE_MISSING")
    elif not os.access(args.executable, os.X_OK):
        blockers.append("EXECUTABLE_NOT_EXECUTABLE")
    else:
        executable_digest = file_digest(args.executable)

    if not blockers:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(args.url, method="GET", headers={"User-Agent": "ChaCha-DEV-HUB-HTTP-Smoke-Probe/1"})
        started = time.monotonic()
        try:
            with opener.open(request, timeout=max(0.5, min(args.timeout, 15.0))) as response:
                status_code = int(response.status)
                body = response.read(4097)
        except urllib.error.HTTPError as exc:
            status_code = int(exc.code)
            try:
                body = exc.read(4097)
            except Exception:
                body = b""
        except Exception as exc:
            blockers.append(f"PROBE_TRANSPORT:{type(exc).__name__}")
        latency_ms = round((time.monotonic() - started) * 1000, 3)

        if len(body) > 4096:
            blockers.append("PROBE_RESPONSE_TOO_LARGE")
            body = body[:4096]
        if status_code != 200:
            blockers.append(f"PROBE_HTTP_STATUS:{status_code}")

    state = "HEALTHY" if not blockers else "UNAVAILABLE"
    evidence_basis = {
        "provider": PROVIDER,
        "state": state,
        "source": safe_source(args.url),
        "status_code": status_code,
        "body_digest": bytes_digest(body),
        "executable_digest": executable_digest,
        "blockers": blockers,
    }
    raw = json.dumps(evidence_basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload = {
        "schema": SCHEMA,
        "provider": PROVIDER,
        "state": state,
        "source": "http-smoke-independent-probe",
        "checked_at": checked_at,
        "latency_ms": latency_ms,
        "reason": "healthy" if not blockers else ";".join(blockers),
        "details": {
            "target": safe_source(args.url),
            "http_status": status_code,
            "bytes_sampled": len(body),
            "body_digest": bytes_digest(body),
            "executable": str(args.executable),
            "executable_digest": executable_digest,
            "independent_from_adapter_execution": True,
            "loopback_only": True,
            "blockers": blockers,
        },
        "evidence_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PROVIDER_PROBE_RESULT={args.output}")
    print(f"PROVIDER={PROVIDER}")
    print(f"STATE={state}")
    for blocker in blockers:
        print(f"BLOCKER={blocker}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
