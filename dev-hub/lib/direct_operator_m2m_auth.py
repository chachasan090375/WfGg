from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


REGISTRY_SCHEMA = "chacha.dev/direct-operator-m2m-secret-registry/v1"
SIGNATURE_PREFIX = "sha256="
SERVICE_ID_RX = re.compile(r"[A-Za-z0-9._:-]{3,96}\Z")
NONCE_RX = re.compile(r"[A-Za-z0-9._:-]{16,128}\Z")
DIGEST_RX = re.compile(r"[0-9a-f]{64}\Z")


class MachineAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class MachineIdentity:
    service_id: str

    @property
    def operator_identity(self) -> str:
        return f"service:{self.service_id}"


def _header(headers: Mapping[str, Any] | Any, name: str) -> str:
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is not None:
            return str(value).strip()
    target = name.casefold()
    try:
        for key, value in headers.items():
            if str(key).casefold() == target:
                return str(value).strip()
    except Exception:
        pass
    return ""


def body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_message(method: str, path: str, timestamp: int, nonce: str, body_digest: str) -> bytes:
    method = str(method or "").upper().strip()
    path = str(path or "").strip()
    nonce = str(nonce or "").strip()
    body_digest = str(body_digest or "").lower().strip()
    if method not in {"GET", "POST"}:
        raise MachineAuthError("METHOD_INVALID")
    if not path.startswith("/") or "?" in path or "#" in path:
        raise MachineAuthError("PATH_INVALID")
    if not NONCE_RX.fullmatch(nonce):
        raise MachineAuthError("NONCE_INVALID")
    if not DIGEST_RX.fullmatch(body_digest):
        raise MachineAuthError("BODY_DIGEST_INVALID")
    return f"{method}\n{path}\n{int(timestamp)}\n{nonce}\n{body_digest}".encode("utf-8")


def _decode_secret(secret_b64: str) -> bytes:
    try:
        raw = base64.b64decode(str(secret_b64 or ""), validate=True)
    except Exception as exc:
        raise MachineAuthError("SECRET_ENCODING_INVALID") from exc
    if len(raw) < 32:
        raise MachineAuthError("SECRET_TOO_SHORT")
    return raw


def load_registry(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MachineAuthError("SECRET_REGISTRY_MISSING") from exc
    except Exception as exc:
        raise MachineAuthError("SECRET_REGISTRY_UNREADABLE") from exc
    if not isinstance(data, dict) or data.get("schema") != REGISTRY_SCHEMA:
        raise MachineAuthError("SECRET_REGISTRY_SCHEMA_INVALID")
    services = data.get("services")
    if not isinstance(services, dict) or not services:
        raise MachineAuthError("SECRET_REGISTRY_EMPTY")
    return data


def _service_record(registry: dict[str, Any], service_id: str) -> dict[str, Any]:
    if not SERVICE_ID_RX.fullmatch(service_id):
        raise MachineAuthError("SERVICE_ID_INVALID")
    record = (registry.get("services") or {}).get(service_id)
    if not isinstance(record, dict) or record.get("enabled") is not True:
        raise MachineAuthError("SERVICE_NOT_AUTHORIZED")
    return record


def _path_allowed(record: dict[str, Any], method: str, path: str) -> bool:
    method = method.upper()
    for rule in record.get("allow") or []:
        if not isinstance(rule, dict) or str(rule.get("method") or "").upper() != method:
            continue
        exact = str(rule.get("path") or "")
        prefix = str(rule.get("path_prefix") or "")
        if exact and path == exact:
            return True
        if prefix and path.startswith(prefix):
            return True
    return False


def signature(secret: bytes, method: str, path: str, timestamp: int, nonce: str, body_digest: str) -> str:
    msg = canonical_message(method, path, timestamp, nonce, body_digest)
    return SIGNATURE_PREFIX + hmac.new(secret, msg, hashlib.sha256).hexdigest()


def build_headers(
    service_id: str,
    secret: bytes,
    method: str,
    path: str,
    body: bytes = b"",
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    if not SERVICE_ID_RX.fullmatch(service_id):
        raise MachineAuthError("SERVICE_ID_INVALID")
    ts = int(time.time() if timestamp is None else timestamp)
    nonce_value = nonce or os.urandom(24).hex()
    digest = body_sha256(body)
    return {
        "X-ChaCha-Service-Id": service_id,
        "X-ChaCha-Timestamp": str(ts),
        "X-ChaCha-Nonce": nonce_value,
        "X-ChaCha-Body-SHA256": digest,
        "X-ChaCha-Signature": signature(secret, method, path, ts, nonce_value, digest),
    }


class FileNonceStore:
    def __init__(self, root: Path, ttl_seconds: int = 300) -> None:
        self.root = root
        self.ttl_seconds = max(30, min(int(ttl_seconds), 3600))

    def claim(self, service_id: str, nonce: str, now: int) -> bool:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        key = hashlib.sha256(f"{service_id}\n{nonce}".encode("utf-8")).hexdigest()
        path = self.root / key
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            return False
        try:
            os.write(fd, (str(int(now) + self.ttl_seconds) + "\n").encode("ascii"))
        finally:
            os.close(fd)
        return True

    def purge_expired(self, now: int) -> int:
        if not self.root.is_dir():
            return 0
        removed = 0
        for path in self.root.iterdir():
            if not path.is_file():
                continue
            try:
                expiry = int(path.read_text(encoding="ascii").strip())
            except Exception:
                continue
            if expiry < int(now):
                try:
                    path.unlink()
                    removed += 1
                except FileNotFoundError:
                    pass
        return removed


def verify_request(
    headers: Mapping[str, Any] | Any,
    method: str,
    path: str,
    body: bytes,
    *,
    registry_path: Path,
    nonce_claim: Callable[[str, str, int], bool],
    now: int | None = None,
    max_clock_skew_seconds: int = 30,
) -> MachineIdentity:
    service_id = _header(headers, "X-ChaCha-Service-Id")
    timestamp_raw = _header(headers, "X-ChaCha-Timestamp")
    nonce = _header(headers, "X-ChaCha-Nonce")
    supplied_digest = _header(headers, "X-ChaCha-Body-SHA256").lower()
    supplied_signature = _header(headers, "X-ChaCha-Signature").lower()
    if not all((service_id, timestamp_raw, nonce, supplied_digest, supplied_signature)):
        raise MachineAuthError("M2M_HEADERS_REQUIRED")
    try:
        timestamp = int(timestamp_raw)
    except Exception as exc:
        raise MachineAuthError("TIMESTAMP_INVALID") from exc
    current = int(time.time() if now is None else now)
    skew = max(1, min(int(max_clock_skew_seconds), 300))
    if abs(current - timestamp) > skew:
        raise MachineAuthError("TIMESTAMP_OUT_OF_WINDOW")
    if not NONCE_RX.fullmatch(nonce):
        raise MachineAuthError("NONCE_INVALID")
    actual_digest = body_sha256(body)
    if not hmac.compare_digest(supplied_digest, actual_digest):
        raise MachineAuthError("BODY_DIGEST_MISMATCH")
    registry = load_registry(registry_path)
    record = _service_record(registry, service_id)
    if not _path_allowed(record, method, path):
        raise MachineAuthError("M2M_ROUTE_FORBIDDEN")
    secret = _decode_secret(str(record.get("secret_b64") or ""))
    expected = signature(secret, method, path, timestamp, nonce, actual_digest)
    if not hmac.compare_digest(supplied_signature, expected):
        raise MachineAuthError("SIGNATURE_INVALID")
    if not nonce_claim(service_id, nonce, current):
        raise MachineAuthError("NONCE_REPLAYED")
    return MachineIdentity(service_id=service_id)
