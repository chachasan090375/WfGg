from __future__ import annotations

import base64
import http.client
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

from .policy import OperatorPolicy, PolicyError


SERVICE_ID = "chacha-remote-operator-mcp"
CLIENT_REQUEST_ID_RX = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
PROJECT_RX = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
JOB_ID_RX = re.compile(r"doj-[0-9a-f]{32}\Z")
MAX_RESPONSE_BYTES = 1024 * 1024


class DirectOperatorBridgeError(RuntimeError):
    pass


def _contract_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "chatgpt-exposure.v1.json"


def _load_contract() -> dict[str, Any]:
    try:
        data = json.loads(_contract_path().read_text(encoding="utf-8"))
    except Exception as exc:
        raise DirectOperatorBridgeError("EXPOSURE_CONTRACT_UNREADABLE") from exc
    if not isinstance(data, dict) or data.get("schema") != "chacha.dev/chatgpt-remote-operator-exposure/v1":
        raise DirectOperatorBridgeError("EXPOSURE_CONTRACT_INVALID")
    return data


def _protocol_module():
    dev_hub = Path(__file__).resolve().parents[4]
    source = dev_hub / "lib" / "direct_operator_m2m_auth.py"
    spec = importlib.util.spec_from_file_location("chacha_direct_operator_m2m_auth", source)
    if spec is None or spec.loader is None:
        raise DirectOperatorBridgeError("M2M_PROTOCOL_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _target(contract: dict[str, Any]) -> dict[str, Any]:
    target = contract.get("direct_operator_target")
    if not isinstance(target, dict):
        raise DirectOperatorBridgeError("DIRECT_OPERATOR_TARGET_MISSING")
    if target.get("bridge_enabled") is not True:
        raise DirectOperatorBridgeError("DIRECT_OPERATOR_BRIDGE_DISABLED")
    if str(target.get("private_endpoint") or "") != "http://127.0.0.1:8792":
        raise DirectOperatorBridgeError("DIRECT_OPERATOR_TARGET_NOT_CANONICAL")
    if str(target.get("machine_to_machine_authentication") or "") != "HMAC_SHA256_RUNTIME_SECRET_CANDIDATE":
        raise DirectOperatorBridgeError("DIRECT_OPERATOR_M2M_AUTH_NOT_BOUND")
    if str(target.get("service_id") or "") != SERVICE_ID:
        raise DirectOperatorBridgeError("DIRECT_OPERATOR_SERVICE_ID_MISMATCH")
    if target.get("tailscale_identity_header_spoofing_forbidden") is not True:
        raise DirectOperatorBridgeError("TAILSCALE_HEADER_SPOOFING_GUARD_MISSING")
    if target.get("direct_central_orchestrator_bypass_forbidden") is not True:
        raise DirectOperatorBridgeError("CENTRAL_ORCHESTRATOR_BYPASS_GUARD_MISSING")
    if target.get("forced_channel") != "BUILD":
        raise DirectOperatorBridgeError("BUILD_CHANNEL_NOT_FORCED")
    if target.get("direct_mutation_authority") is not False or target.get("technical_decision_authority") is not False:
        raise DirectOperatorBridgeError("INTERFACE_AUTHORITY_EXPANSION_FORBIDDEN")
    return target


def _secret(protocol: Any, target: dict[str, Any]) -> bytes:
    path = Path(str(target.get("secret_registry") or ""))
    if not path.is_absolute():
        raise DirectOperatorBridgeError("M2M_SECRET_REGISTRY_PATH_INVALID")
    registry = protocol.load_registry(path)
    record = protocol._service_record(registry, SERVICE_ID)
    return protocol._decode_secret(str(record.get("secret_b64") or ""))


def _request(method: str, path: str, body: bytes, contract: dict[str, Any]) -> dict[str, Any]:
    target = _target(contract)
    protocol = _protocol_module()
    secret = _secret(protocol, target)
    headers = protocol.build_headers(SERVICE_ID, secret, method, path, body)
    if body:
        headers["Content-Type"] = "application/json; charset=utf-8"
    headers["Content-Length"] = str(len(body))
    connection = http.client.HTTPConnection("127.0.0.1", 8792, timeout=15)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise DirectOperatorBridgeError("DIRECT_OPERATOR_RESPONSE_TOO_LARGE")
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:
            raise DirectOperatorBridgeError("DIRECT_OPERATOR_RESPONSE_INVALID_JSON") from exc
        if not isinstance(payload, dict):
            raise DirectOperatorBridgeError("DIRECT_OPERATOR_RESPONSE_NOT_OBJECT")
        if response.status not in {200, 202}:
            status = str(payload.get("status") or "UNKNOWN")[:120]
            raise DirectOperatorBridgeError(f"DIRECT_OPERATOR_REJECTED:{response.status}:{status}")
        return payload
    except DirectOperatorBridgeError:
        raise
    except Exception as exc:
        raise DirectOperatorBridgeError("DIRECT_OPERATOR_UNAVAILABLE") from exc
    finally:
        connection.close()


def submit_intent(
    policy: OperatorPolicy,
    text: str,
    project: str,
    client_request_id: str,
) -> dict[str, Any]:
    try:
        policy.require_operational()
    except PolicyError as exc:
        raise DirectOperatorBridgeError(str(exc)) from exc
    text = str(text or "").strip()
    project = str(project or "").strip()
    client_request_id = str(client_request_id or "").strip()
    if not text or len(text.encode("utf-8")) > 32768:
        raise DirectOperatorBridgeError("INTENT_TEXT_INVALID")
    if not PROJECT_RX.fullmatch(project):
        raise DirectOperatorBridgeError("PROJECT_INVALID")
    if not CLIENT_REQUEST_ID_RX.fullmatch(client_request_id):
        raise DirectOperatorBridgeError("CLIENT_REQUEST_ID_REQUIRED")
    contract = _load_contract()
    path = str(_target(contract).get("intent_path") or "")
    if path != "/api/v1/m2m/intent":
        raise DirectOperatorBridgeError("INTENT_PATH_NOT_CANONICAL")
    body = json.dumps(
        {
            "text": text,
            "project": project,
            "channel": "BUILD",
            "client_request_id": client_request_id,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return _request("POST", path, body, contract)


def read_job(policy: OperatorPolicy, job_id: str) -> dict[str, Any]:
    try:
        policy.require_operational()
    except PolicyError as exc:
        raise DirectOperatorBridgeError(str(exc)) from exc
    job_id = str(job_id or "").strip()
    if not JOB_ID_RX.fullmatch(job_id):
        raise DirectOperatorBridgeError("JOB_ID_INVALID")
    contract = _load_contract()
    prefix = str(_target(contract).get("job_path_prefix") or "")
    if prefix != "/api/v1/m2m/jobs/":
        raise DirectOperatorBridgeError("JOB_PATH_NOT_CANONICAL")
    return _request("GET", prefix + job_id, b"", contract)
