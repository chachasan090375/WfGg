#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CONTROL_SCHEMA = "chacha.dev/platform-control-plane-report/v1"
POLICY_SCHEMA = "chacha.dev/platform-control-plane-policy/v1"
ATTEST_SCHEMA = "chacha.dev/conversation-provider-zero-cost-attestation/v1"
JOB_SCHEMA = "chacha.dev/direct-operator-job/v1"
RESPONSE_SCHEMA = "chacha.dev/human-interface-response/v1"
CONTROL_PREFIX = "CONTROL_PLANE_ONLY"
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
_MISSING = object()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load(path: Path, default: Any = _MISSING) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not _MISSING:
            return default
        raise


def atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def parse_iso(value: Any) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def safe_path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def authorized_users(direct_policy: dict[str, Any]) -> set[str]:
    auth = direct_policy.get("authentication") if isinstance(direct_policy.get("authentication"), dict) else {}
    path = Path(str(auth.get("authorized_users_file") or ""))
    data = load(path, {"authorized_logins": []})
    if not isinstance(data, dict):
        return set()
    return {str(v).strip().casefold() for v in data.get("authorized_logins") or [] if str(v).strip()}


def control_request(text: str) -> bool:
    return str(text or "").lstrip().upper().startswith(CONTROL_PREFIX)


class ControlPlane:
    def __init__(self, repo: Path, runtime: Path, direct_policy: dict[str, Any], policy: dict[str, Any]):
        self.repo = repo
        self.runtime = runtime
        self.direct_policy = direct_policy
        self.policy = policy
        self.jobs = Path(str(policy.get("jobs_root") or runtime / "direct-operator/control-plane-jobs"))
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.session_path = Path(str(policy.get("session_path") or runtime / "direct-operator/session.json"))
        self.stop_path = Path(str(policy.get("emergency_stop_path") or runtime / "control/emergency-stop.json"))
        dialogue = direct_policy.get("dialogue_orchestrator") if isinstance(direct_policy.get("dialogue_orchestrator"), dict) else {}
        raw_dialogue_policy = Path(str(dialogue.get("policy") or "dev-hub/config/dialogue-orchestrator.v1.json"))
        self.dialogue_policy_path = raw_dialogue_policy if raw_dialogue_policy.is_absolute() else repo / raw_dialogue_policy
        self.attestation_path = Path(str(dialogue.get("zero_cost_attestation") or runtime / "provider-economics/agy-conversation-zero-cost.json"))
        self.allowed_response_root = Path(str(policy.get("allowed_response_root") or runtime / "direct-operator"))

    def last_response(self) -> dict[str, Any] | None:
        session = load(self.session_path, {})
        if not isinstance(session, dict):
            return None
        raw = str(session.get("last_response_path") or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = self.allowed_response_root / path
        if not safe_path_under(path, self.allowed_response_root) or not path.is_file():
            return None
        value = load(path, None)
        return value if isinstance(value, dict) else None

    def zero_cost(self) -> dict[str, Any]:
        dialogue_policy = load(self.dialogue_policy_path, {})
        provider = dialogue_policy.get("provider") if isinstance(dialogue_policy, dict) and isinstance(dialogue_policy.get("provider"), dict) else {}
        provider_id = str(provider.get("id") or "")
        backend = Path(str(provider.get("backend") or ""))
        attestation = load(self.attestation_path, None)
        base = {
            "provider_id": provider_id,
            "backend": str(backend),
            "backend_present": bool(backend.is_file() and os.access(backend, os.X_OK)),
            "attestation_path": str(self.attestation_path),
            "attestation_present": isinstance(attestation, dict),
            "cost_class": None,
            "quota_available": None,
            "valid_until": None,
            "reset_at": None,
            "eligible": False,
            "status": "MISSING",
            "reason": "ZERO_COST_ATTESTATION_MISSING",
        }
        if not isinstance(attestation, dict):
            return base
        base.update({
            "cost_class": attestation.get("cost_class"),
            "quota_available": attestation.get("quota_available"),
            "valid_until": attestation.get("valid_until"),
            "reset_at": attestation.get("reset_at"),
        })
        if attestation.get("schema") != ATTEST_SCHEMA or attestation.get("provider_id") != provider_id or attestation.get("status") != "PASS":
            base.update(status="INVALID", reason="ZERO_COST_ATTESTATION_INVALID")
            return base
        try:
            spend = float(attestation.get("automatic_external_spend_eur"))
        except Exception:
            spend = -1.0
        if spend != 0:
            base.update(status="INVALID", reason="ZERO_COST_ATTESTATION_NONZERO_SPEND")
            return base
        cost = str(attestation.get("cost_class") or "").lower()
        allowed = {str(x).lower() for x in provider.get("allowed_zero_cost_classes") or []}
        if cost not in allowed:
            base.update(status="INVALID", reason="COST_CLASS_NOT_AUTOMATIC_ZERO")
            return base
        if cost == "quota":
            if attestation.get("quota_available") is not True:
                base.update(status="EXHAUSTED", reason="FREE_QUOTA_NOT_CONFIRMED")
                return base
            valid_until = parse_iso(attestation.get("valid_until"))
            if valid_until is None or valid_until <= dt.datetime.now(dt.timezone.utc):
                base.update(status="STALE", reason="ZERO_COST_ATTESTATION_EXPIRED")
                return base
        base.update(status="PASS", reason="ZERO_COST_ATTESTED", eligible=True)
        return base

    def domain(self, last: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(last, dict):
            return {"status": "UNKNOWN", "reason": "NO_PRIOR_RESPONSE"}
        next_action = str(last.get("next_action") or "")
        central = last.get("brain_receipt") if isinstance(last.get("brain_receipt"), dict) else {}
        decision = central.get("decision") if isinstance(central.get("decision"), dict) else {}
        blocked = "DOMAIN_EXECUTION_VERIFICATION_REQUIRED" in next_action.upper()
        return {
            "status": "BLOCKED" if blocked else "OBSERVED",
            "next_action": next_action,
            "execution_project_id": last.get("execution_project_id"),
            "central_status": central.get("status"),
            "reason": "DOMAIN_EXECUTION_VERIFICATION_REQUIRED" if blocked else None,
            "decision": decision,
        }

    def adapters(self, last: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(last, dict):
            return {"status": "UNKNOWN", "reason": "NO_PRIOR_RESPONSE"}
        next_action = str(last.get("next_action") or "")
        blocked = "ADAPTER_ENABLEMENT_REQUIRED" in next_action.upper()
        return {
            "status": "BLOCKED" if blocked else "OBSERVED",
            "next_action": next_action,
            "reason": "ADAPTER_ENABLEMENT_REQUIRED" if blocked else None,
        }

    def emergency_stop(self) -> dict[str, Any]:
        value = load(self.stop_path, {})
        if not isinstance(value, dict):
            return {"status": "UNKNOWN", "active": None}
        active = value.get("active") is True
        return {"status": "ACTIVE" if active else "INACTIVE", "active": active, "path": str(self.stop_path)}

    def report(self) -> dict[str, Any]:
        last = self.last_response()
        zero = self.zero_cost()
        domain = self.domain(last)
        adapters = self.adapters(last)
        stop = self.emergency_stop()
        causes = []
        if domain.get("status") == "BLOCKED":
            causes.append("DOMAIN_EXECUTION_VERIFICATION_REQUIRED")
        if adapters.get("status") == "BLOCKED":
            causes.append("ADAPTER_ENABLEMENT_REQUIRED")
        if not zero.get("eligible"):
            causes.append(str(zero.get("reason") or "ZERO_COST_UNAVAILABLE"))
        platform_status = "PASS" if not causes else "DEGRADED"
        return {
            "schema": CONTROL_SCHEMA,
            "observed_at": now_iso(),
            "status": "PASS",
            "platform_status": platform_status,
            "mode": "LOCAL_DETERMINISTIC_NO_PROVIDER",
            "project_id": "chacha-dev-platform",
            "domain_execution": domain,
            "adapters": adapters,
            "zero_cost": zero,
            "provider_health": {
                "provider_id": zero.get("provider_id"),
                "backend_present": zero.get("backend_present"),
                "zero_cost_eligible": zero.get("eligible"),
                "status": "AVAILABLE" if zero.get("backend_present") and zero.get("eligible") else "UNAVAILABLE",
            },
            "quota": {
                "provider_id": zero.get("provider_id"),
                "cost_class": zero.get("cost_class"),
                "quota_available": zero.get("quota_available"),
                "valid_until": zero.get("valid_until"),
                "reset_at": zero.get("reset_at"),
                "status": zero.get("status"),
            },
            "emergency_stop": stop,
            "root_causes": causes,
            "automatic_external_spend_eur": 0,
            "provider_invoked": False,
            "technology_watch_invoked": False,
            "central_orchestrator_invoked": False,
        }

    def refresh_zero_cost(self) -> dict[str, Any]:
        cfg = self.policy.get("zero_cost_refresh") if isinstance(self.policy.get("zero_cost_refresh"), dict) else {}
        evidence_raw = str(cfg.get("local_evidence_path") or "").strip()
        if not evidence_raw:
            return {
                "schema": "chacha.dev/zero-cost-attestation-refresh/v1",
                "status": "BLOCKED",
                "reason": "LOCAL_ZERO_COST_EVIDENCE_NOT_CONFIGURED",
                "attestation_mutated": False,
                "automatic_external_spend_eur": 0,
            }
        evidence_path = Path(evidence_raw)
        evidence = load(evidence_path, None)
        try:
            spend = float(evidence.get("automatic_external_spend_eur")) if isinstance(evidence, dict) else -1.0
        except Exception:
            spend = -1.0
        if not isinstance(evidence, dict) or evidence.get("verified") is not True or spend != 0:
            return {
                "schema": "chacha.dev/zero-cost-attestation-refresh/v1",
                "status": "BLOCKED",
                "reason": "LOCAL_ZERO_COST_EVIDENCE_INVALID",
                "attestation_mutated": False,
                "automatic_external_spend_eur": 0,
            }
        allowed = {"schema", "provider_id", "status", "cost_class", "quota_available", "valid_until", "reset_at", "automatic_external_spend_eur"}
        attestation = {k: evidence[k] for k in allowed if k in evidence}
        if attestation.get("schema") != ATTEST_SCHEMA or attestation.get("status") != "PASS":
            return {"schema": "chacha.dev/zero-cost-attestation-refresh/v1", "status": "BLOCKED", "reason": "LOCAL_ZERO_COST_EVIDENCE_SCHEMA_INVALID", "attestation_mutated": False, "automatic_external_spend_eur": 0}
        atomic(self.attestation_path, attestation)
        return {"schema": "chacha.dev/zero-cost-attestation-refresh/v1", "status": "PASS", "reason": "LOCAL_EVIDENCE_APPLIED", "attestation_mutated": True, "attestation": self.zero_cost(), "automatic_external_spend_eur": 0}

    def render_message(self, report: dict[str, Any]) -> str:
        zero = report.get("zero_cost") or {}
        domain = report.get("domain_execution") or {}
        adapters = report.get("adapters") or {}
        return (
            "Control Plane local exécuté sans modèle ni provider.\n"
            f"Domaine: {domain.get('status')} ({domain.get('reason') or domain.get('next_action') or 'aucun blocage observé'}).\n"
            f"Adapter: {adapters.get('status')} ({adapters.get('reason') or 'aucun blocage observé'}).\n"
            f"Zero-cost: {zero.get('status')} ({zero.get('reason')}); provider={zero.get('provider_id')}; quota={zero.get('quota_available')}; reset={zero.get('reset_at') or 'inconnu'}.\n"
            "Ces états sont observés indépendamment; aucune causalité n'est inventée."
        )

    def submit(self, text: str, operator: str, project: str) -> tuple[str, dict[str, Any]]:
        report = self.report()
        jid = "cpj-" + uuid.uuid4().hex
        message = self.render_message(report)
        response = {
            "schema": RESPONSE_SCHEMA,
            "request_id": "cpr-" + uuid.uuid4().hex,
            "responded_at": now_iso(),
            "route": "LOCAL_CONTROL_PLANE",
            "command": "CONTROL_PLANE_ONLY",
            "project_id": project,
            "execution_project_id": project,
            "status": "PASS",
            "authority": "platform-control-plane-diagnostics",
            "brain_decision_obtained": False,
            "next_action": "AWAIT_USER_DIRECTIVE",
            "message": message,
            "conversation": {"schema": "chacha.dev/conversation-response/v1", "kind": "INFO", "message": message, "status": "PASS", "next_action": "AWAIT_USER_DIRECTIVE", "requires_user_response": False},
            "control_plane": report,
            "interface_direct_technical_decision": False,
            "interface_direct_mutation": False,
            "automatic_external_spend_eur": 0,
        }
        job = {"schema": JOB_SCHEMA, "job_id": jid, "created_at": now_iso(), "updated_at": now_iso(), "state": "COMPLETE", "operator": operator, "project_id": project, "channel": "BUILD", "response": response}
        atomic(self.jobs / (jid + ".json"), job)
        return jid, job


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "ChaChaControlPlaneGateway/1.0"

    @property
    def app(self) -> "Gateway":
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def send_json(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def control_identity(self) -> str | None:
        auth = self.app.direct_policy.get("authentication") if isinstance(self.app.direct_policy.get("authentication"), dict) else {}
        header = str(auth.get("login_header") or "Tailscale-User-Login")
        identity = str(self.headers.get(header) or "").strip().casefold()
        if identity and identity in self.app.users:
            return identity
        self.send_json(HTTPStatus.FORBIDDEN, {"status": "FORBIDDEN", "reason": "TAILSCALE_IDENTITY_REQUIRED"})
        return None

    def proxy(self, method: str, body: bytes | None = None) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.app.core_port, timeout=180)
        headers = {k: v for k, v in self.headers.items() if k.casefold() not in HOP_HEADERS and k.casefold() not in {"host", "content-length"}}
        if body is not None:
            headers["Content-Length"] = str(len(body))
        try:
            conn.request(method, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for key, value in resp.getheaders():
                lk = key.casefold()
                if lk in HOP_HEADERS or lk in {"content-length", "connection"}:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self.send_json(502, {"status": "CORE_UNAVAILABLE", "reason": type(exc).__name__})
        finally:
            conn.close()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            return self.send_json(200, {"status": "PASS", "component": "direct-operator-control-plane-gateway", "core_port": self.app.core_port})
        if path.startswith("/api/v1/control-plane/"):
            if not self.control_identity():
                return
            if path == "/api/v1/control-plane/status":
                return self.send_json(200, self.app.control.report())
            if path in {"/api/v1/control-plane/quotas", "/api/v1/control-plane/zero-cost", "/api/v1/control-plane/domain", "/api/v1/control-plane/adapters", "/api/v1/control-plane/provider-health"}:
                report = self.app.control.report()
                key = {"quotas": "quota", "zero-cost": "zero_cost", "domain": "domain_execution", "adapters": "adapters", "provider-health": "provider_health"}[path.rsplit("/", 1)[-1]]
                return self.send_json(200, {"schema": CONTROL_SCHEMA, "observed_at": report["observed_at"], key: report[key], "automatic_external_spend_eur": 0})
            return self.send_json(404, {"status": "NOT_FOUND"})
        if path.startswith("/api/v1/jobs/cpj-"):
            if not self.control_identity():
                return
            jid = path.rsplit("/", 1)[-1]
            target = self.app.control.jobs / (jid + ".json")
            if not target.is_file():
                return self.send_json(404, {"status": "NOT_FOUND"})
            return self.send_json(200, load(target, {"status": "NOT_FOUND"}))
        return self.proxy("GET")

    def do_POST(self) -> None:
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except Exception:
            size = 0
        if size < 0 or size > int(self.app.direct_policy.get("max_request_bytes") or 65536):
            return self.send_json(413, {"status": "INVALID_SIZE"})
        body = self.rfile.read(size) if size else b""
        path = urlparse(self.path).path
        if path == "/api/v1/control-plane/zero-cost/refresh":
            if not self.control_identity():
                return
            return self.send_json(200, self.app.control.refresh_zero_cost())
        if path == "/api/v1/intent":
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                payload = None
            if isinstance(payload, dict) and control_request(str(payload.get("text") or "")):
                identity = self.control_identity()
                if not identity:
                    return
                project = str(payload.get("project") or "chacha-dev-platform")
                jid, _job = self.app.control.submit(str(payload.get("text") or ""), identity, project)
                return self.send_json(202, {"status": "ACCEPTED", "job_id": jid, "state": "COMPLETE", "project_id": project, "channel": "BUILD", "client_request_id": payload.get("client_request_id"), "deduplicated": False, "control_plane_local": True})
        return self.proxy("POST", body)


class Gateway:
    def __init__(self, repo: Path, runtime: Path, direct_policy_path: Path, control_policy_path: Path):
        self.repo = repo
        self.runtime = runtime
        self.direct_policy_path = direct_policy_path
        self.direct_policy = load(direct_policy_path, {})
        self.control_policy = load(control_policy_path, {})
        if not isinstance(self.control_policy, dict) or self.control_policy.get("schema") != POLICY_SCHEMA:
            raise SystemExit("CONTROL_PLANE_POLICY_SCHEMA_INVALID")
        if str(self.direct_policy.get("bind") or "") not in {"127.0.0.1", "::1", "localhost"}:
            raise SystemExit("DIRECT_OPERATOR_LOOPBACK_BIND_REQUIRED")
        self.users = authorized_users(self.direct_policy)
        if not self.users:
            raise SystemExit("DIRECT_OPERATOR_AUTHORIZED_USER_REQUIRED")
        self.public_port = int(self.direct_policy.get("port") or 8792)
        self.core_port = int(self.control_policy.get("core_port") or 8793)
        if self.public_port == self.core_port:
            raise SystemExit("CONTROL_PLANE_CORE_PORT_MUST_DIFFER")
        self.control = ControlPlane(repo, runtime, self.direct_policy, self.control_policy)
        self.core: subprocess.Popen[str] | None = None

    def start_core(self) -> None:
        core_policy = dict(self.direct_policy)
        core_policy["bind"] = "127.0.0.1"
        core_policy["port"] = self.core_port
        runtime_policy = self.control.jobs.parent / "control-plane-core-policy.json"
        atomic(runtime_policy, core_policy)
        core_script = self.repo / str(self.control_policy.get("core_script") or "dev-hub/bin/direct-operator-service.py")
        self.core = subprocess.Popen([sys.executable, str(core_script), "--repo-root", str(self.repo), "--runtime-root", str(self.runtime), "--policy", str(runtime_policy)], cwd=str(self.repo))
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.core.poll() is not None:
                raise SystemExit("DIRECT_OPERATOR_CORE_EXITED")
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.core_port, timeout=1)
                conn.request("GET", "/healthz")
                response = conn.getresponse()
                response.read()
                conn.close()
                if response.status == 200:
                    return
            except Exception:
                time.sleep(0.15)
        raise SystemExit("DIRECT_OPERATOR_CORE_START_TIMEOUT")

    def stop_core(self) -> None:
        if self.core is None or self.core.poll() is not None:
            return
        self.core.terminate()
        try:
            self.core.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.core.kill()
            self.core.wait(timeout=2)

    def serve(self) -> int:
        self.start_core()
        server = ThreadingHTTPServer(("127.0.0.1", self.public_port), GatewayHandler)
        server.app = self  # type: ignore[attr-defined]

        def shutdown(_signum: int, _frame: Any) -> None:
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        print("CHACHA_DEV_CONTROL_PLANE_GATEWAY=READY", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            self.stop_core()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("/opt/chacha-dev/platform/current"))
    parser.add_argument("--runtime-root", type=Path, default=Path("/opt/chacha-dev/runtime"))
    parser.add_argument("--direct-policy", type=Path, required=True)
    parser.add_argument("--control-policy", type=Path, required=True)
    args = parser.parse_args()
    app = Gateway(args.repo_root.resolve(), args.runtime_root.resolve(), args.direct_policy, args.control_policy)
    return app.serve()


if __name__ == "__main__":
    raise SystemExit(main())
