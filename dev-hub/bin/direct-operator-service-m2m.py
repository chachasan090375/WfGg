#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HERE = Path(__file__).resolve()
DEV_HUB = HERE.parents[1]
LIB = DEV_HUB / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import direct_operator_m2m_auth as m2m  # noqa: E402


M2M_CONFIG_SCHEMA = "chacha.dev/direct-operator-machine-ingress/v1"
M2M_INTENT_PATH = "/api/v1/m2m/intent"
M2M_JOB_PREFIX = "/api/v1/m2m/jobs/"


def load_base_module():
    source = HERE.with_name("direct-operator-service.py")
    spec = importlib.util.spec_from_file_location("chacha_direct_operator_base", source)
    if spec is None or spec.loader is None:
        raise SystemExit("DIRECT_OPERATOR_BASE_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_base_module()


def load_route_authority(relative_path: str, route_id: str) -> dict[str, Any]:
    rel = Path(str(relative_path or ""))
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit("DIRECT_OPERATOR_M2M_ROUTE_AUTHORITY_PATH_INVALID")
    source = DEV_HUB.parent / rel
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit("DIRECT_OPERATOR_M2M_ROUTE_AUTHORITY_UNREADABLE") from exc
    if data.get("schema") != "chacha.dev/canonical-route-authority/v1":
        raise SystemExit("DIRECT_OPERATOR_M2M_ROUTE_AUTHORITY_SCHEMA_INVALID")
    if (data.get("principles") or {}).get("unknown_route_fails_closed") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_ROUTE_FAIL_CLOSED_REQUIRED")
    route = next((x for x in data.get("routes") or [] if isinstance(x, dict) and x.get("route_id") == route_id), None)
    if not route:
        raise SystemExit("DIRECT_OPERATOR_M2M_ROUTE_NOT_CANONICAL")
    if route.get("class") != "FUNCTIONAL_INTENT":
        raise SystemExit("DIRECT_OPERATOR_M2M_ROUTE_CLASS_INVALID")
    chain = list(route.get("chain") or [])
    expected = ["chacha-remote-operator-mcp", "direct-operator-m2m", "functional-translator", "central-orchestrator", "scheduler", "run-controller", "registered-adapter"]
    pos = -1
    for node in expected:
        try:
            pos = chain.index(node, pos + 1)
        except ValueError as exc:
            raise SystemExit("DIRECT_OPERATOR_M2M_ROUTE_CHAIN_INVALID:" + node) from exc
    return route

def load_m2m_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit("DIRECT_OPERATOR_M2M_CONFIG_UNREADABLE") from exc
    if not isinstance(data, dict) or data.get("schema") != M2M_CONFIG_SCHEMA:
        raise SystemExit("DIRECT_OPERATOR_M2M_CONFIG_SCHEMA_INVALID")
    if data.get("enabled") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_INGRESS_DISABLED")
    transport = data.get("transport") or {}
    if transport.get("kind") != "LOOPBACK_HTTP" or transport.get("bind") != "127.0.0.1":
        raise SystemExit("DIRECT_OPERATOR_M2M_LOOPBACK_REQUIRED")
    if transport.get("public_ingress_forbidden") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_PUBLIC_INGRESS_GUARD_REQUIRED")
    auth = data.get("authentication") or {}
    if auth.get("mode") != "HMAC_SHA256_RUNTIME_SECRET":
        raise SystemExit("DIRECT_OPERATOR_M2M_AUTH_MODE_INVALID")
    if auth.get("secret_in_git_forbidden") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_SECRET_POLICY_INVALID")
    if auth.get("tailscale_identity_header_spoofing_forbidden") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_TAILSCALE_SPOOF_GUARD_REQUIRED")
    contract = data.get("service_contract") or {}
    if contract.get("forced_channel") != "BUILD":
        raise SystemExit("DIRECT_OPERATOR_M2M_BUILD_ONLY_REQUIRED")
    if contract.get("arbitrary_http_forbidden") is not True or contract.get("arbitrary_command_forbidden") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_ARBITRARY_OPERATION_GUARD_REQUIRED")
    if contract.get("direct_central_orchestrator_call_forbidden") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_CENTRAL_BYPASS_GUARD_REQUIRED")
    if contract.get("direct_mutation_authority") is not False or contract.get("technical_decision_authority") is not False:
        raise SystemExit("DIRECT_OPERATOR_M2M_AUTHORITY_EXPANSION_FORBIDDEN")
    governance = data.get("governance") or {}
    route_id = str(contract.get("canonical_route_id") or "")
    if not route_id:
        raise SystemExit("DIRECT_OPERATOR_M2M_CANONICAL_ROUTE_REQUIRED")
    load_route_authority(str(governance.get("canonical_route_authority") or ""), route_id)
    if governance.get("unknown_route_fails_closed") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_UNKNOWN_ROUTE_FAIL_CLOSED_REQUIRED")
    if governance.get("fallback_on_policy_denied_forbidden") is not True:
        raise SystemExit("DIRECT_OPERATOR_M2M_POLICY_DENIAL_FALLBACK_GUARD_REQUIRED")
    if float(governance.get("automatic_external_spend_eur", -1)) != 0:
        raise SystemExit("DIRECT_OPERATOR_M2M_NONZERO_SPEND_FORBIDDEN")
    stop_path = Path(str(governance.get("canonical_user_stop_state") or ""))
    if not stop_path.is_absolute():
        raise SystemExit("DIRECT_OPERATOR_M2M_CANONICAL_STOP_PATH_REQUIRED")
    return data


def stop_active(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return True
    return not isinstance(payload, dict) or payload.get("active") is not False


class M2MHandler(BASE.Handler):
    @property
    def m2m_config(self) -> dict[str, Any]:
        return self.server.m2m_config  # type: ignore[attr-defined]

    @property
    def nonce_store(self) -> m2m.FileNonceStore:
        return self.server.m2m_nonce_store  # type: ignore[attr-defined]

    def _m2m_identity(self, method: str, path: str, body: bytes) -> m2m.MachineIdentity | None:
        cfg = self.m2m_config
        auth = cfg.get("authentication") or {}
        registry = Path(str(auth.get("secret_registry") or ""))
        if not registry.is_absolute():
            self.json(HTTPStatus.FORBIDDEN, {"status": "FORBIDDEN", "reason": "M2M_REGISTRY_INVALID"})
            return None
        try:
            self.nonce_store.purge_expired(int(BASE.time.time()))
            return m2m.verify_request(
                self.headers,
                method,
                path,
                body,
                registry_path=registry,
                nonce_claim=self.nonce_store.claim,
                max_clock_skew_seconds=int(auth.get("max_clock_skew_seconds") or 30),
            )
        except m2m.MachineAuthError as exc:
            self.json(HTTPStatus.FORBIDDEN, {"status": "FORBIDDEN", "reason": str(exc)})
            return None

    def _read_json_body(self) -> tuple[bytes, dict[str, Any]] | None:
        maxb = int(self.st.policy.get("max_request_bytes") or 65536)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            length = 0
        if length <= 0 or length > maxb:
            self.json(413, {"status": "INVALID_SIZE"})
            return None
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self.json(400, {"status": "INVALID_JSON"})
            return None
        if not isinstance(body, dict):
            self.json(400, {"status": "OBJECT_REQUIRED"})
            return None
        return raw, body

    def _m2m_post_intent(self) -> None:
        parsed = self._read_json_body()
        if parsed is None:
            return
        raw, body = parsed
        identity = self._m2m_identity("POST", M2M_INTENT_PATH, raw)
        if identity is None:
            return
        cfg = self.m2m_config
        governance = cfg.get("governance") or {}
        stop_path = Path(str(governance.get("canonical_user_stop_state") or ""))
        if governance.get("canonical_user_stop_must_be_clear") is not True or stop_active(stop_path):
            return self.json(423, {"status": "BLOCKED", "reason": "CANONICAL_STOP_ACTIVE_OR_UNREADABLE"})
        text = str(body.get("text") or "").strip()
        project = str(body.get("project") or "").strip()
        client_request_id = str(body.get("client_request_id") or "").strip()
        if not text:
            return self.json(400, {"status": "TEXT_REQUIRED"})
        if not client_request_id:
            return self.json(400, {"status": "CLIENT_REQUEST_ID_REQUIRED"})
        default_project = str(self.st.policy.get("default_project") or "chacha-dev-platform")
        project = BASE.stable_project(project, default_project)
        operator = identity.operator_identity
        try:
            jid, created = self.st.accept_intent(text, project, operator, client_request_id, "BUILD")
        except ValueError as exc:
            return self.json(400, {"status": str(exc)})
        except RuntimeError as exc:
            return self.json(409, {"status": str(exc)})
        if created:
            threading.Thread(
                target=self.st.process,
                args=(jid, text, project, operator, "BUILD"),
                daemon=True,
            ).start()
        state = BASE.load(self.st.job_path(jid)).get("state") or "QUEUED"
        return self.json(
            202,
            {
                "status": "ACCEPTED",
                "job_id": jid,
                "state": state,
                "project_id": project,
                "channel": "BUILD",
                "client_request_id": client_request_id,
                "deduplicated": not created,
                "machine_identity": identity.service_id,
                "interface_direct_technical_decision": False,
                "interface_direct_mutation": False,
            },
        )

    def _m2m_get_job(self, path: str) -> None:
        identity = self._m2m_identity("GET", path, b"")
        if identity is None:
            return
        jid = path[len(M2M_JOB_PREFIX) :]
        if not BASE.re.fullmatch(r"doj-[0-9a-f]{32}", jid):
            return self.json(400, {"status": "JOB_ID_INVALID"})
        job_path = self.st.job_path(jid)
        if not job_path.is_file():
            return self.json(404, {"status": "NOT_FOUND"})
        job = BASE.load(job_path)
        if str(job.get("operator") or "") != identity.operator_identity:
            return self.json(403, {"status": "FORBIDDEN", "reason": "JOB_NOT_OWNED_BY_SERVICE"})
        job["progress"] = self.st.progress.snapshot()
        return self.json(200, job)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith(M2M_JOB_PREFIX):
            return self._m2m_get_job(path)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == M2M_INTENT_PATH:
            return self._m2m_post_intent()
        return super().do_POST()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("/opt/chacha-dev/platform/current"))
    parser.add_argument("--runtime-root", type=Path, default=Path("/opt/chacha-dev/runtime"))
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument(
        "--m2m-config",
        type=Path,
        default=DEV_HUB / "config" / "direct-operator-machine-ingress.v1.json",
    )
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    runtime = args.runtime_root.resolve()
    policy = BASE.load(args.policy)
    if policy.get("schema") != BASE.POLICY_SCHEMA:
        raise SystemExit("DIRECT_OPERATOR_POLICY_SCHEMA_INVALID")
    bind = str(policy.get("bind") or "")
    if bind not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("DIRECT_OPERATOR_LOOPBACK_BIND_REQUIRED")
    auth = policy.get("authentication") or {}
    if str(auth.get("mode")) != "TAILSCALE_SERVE_IDENTITY":
        raise SystemExit("DIRECT_OPERATOR_TAILSCALE_IDENTITY_REQUIRED")
    if not BASE.authorized_users(Path(str(auth.get("authorized_users_file") or ""))):
        raise SystemExit("DIRECT_OPERATOR_AUTHORIZED_USER_REQUIRED")
    m2m_config = load_m2m_config(args.m2m_config)
    m2m_auth = m2m_config.get("authentication") or {}
    nonce_root = Path(str(m2m_auth.get("nonce_store") or ""))
    if not nonce_root.is_absolute():
        raise SystemExit("DIRECT_OPERATOR_M2M_NONCE_STORE_INVALID")
    server = ThreadingHTTPServer((bind, int(policy.get("port") or 8792)), M2MHandler)
    server.state = BASE.State(repo, runtime, policy)  # type: ignore[attr-defined]
    server.m2m_config = m2m_config  # type: ignore[attr-defined]
    server.m2m_nonce_store = m2m.FileNonceStore(  # type: ignore[attr-defined]
        nonce_root,
        int(m2m_auth.get("nonce_ttl_seconds") or 300),
    )
    print("CHACHA_DEV_DIRECT_OPERATOR=READY", flush=True)
    print("CHACHA_DEV_DIRECT_OPERATOR_M2M=READY", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
