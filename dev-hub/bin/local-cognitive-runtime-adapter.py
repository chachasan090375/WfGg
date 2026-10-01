#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, socket, urllib.request
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/local-cognitive-runtime-policy/v1"
REQUEST_SCHEMA = "chacha.dev/local-cognitive-request/v1"
PROVIDER_MANIFEST_SCHEMA = "chacha.dev/local-cognitive-provider-manifest/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
RESOURCE_SCHEMA = "chacha.dev/local-resource-snapshot/v1"
CATALOG_SCHEMA = "chacha.dev/cognitive-model-catalog/v1"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_NOT_OBJECT:" + str(path))
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

def require_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("schema") != POLICY_SCHEMA:
        raise ValueError("POLICY_SCHEMA_MISMATCH")
    if policy.get("runtime") != "llama.cpp":
        raise ValueError("RUNTIME_NOT_LLAMA_CPP")
    endpoint = policy.get("endpoint") or {}
    host = str(endpoint.get("host") or "")
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("ENDPOINT_NOT_LOOPBACK")
    if bool(policy.get("rpc_allowed")):
        raise ValueError("RPC_FORBIDDEN")
    if str(policy.get("reasoning") or "") != "off":
        raise ValueError("REASONING_MUST_BE_OFF")
    if float(policy.get("automatic_external_spend_eur") or 0) != 0:
        raise ValueError("NONZERO_EXTERNAL_SPEND")
    return policy


def artifacts(policy: dict[str, Any]) -> tuple[Path, Path]:
    exe = Path(str(policy.get("executable") or ""))
    model = Path(str(policy.get("model_artifact") or ""))
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise ValueError("EXECUTABLE_NOT_READY")
    if not model.is_file():
        raise ValueError("MODEL_ARTIFACT_MISSING")
    if sha256(exe) != str(policy.get("executable_digest") or ""):
        raise ValueError("EXECUTABLE_DIGEST_MISMATCH")
    if sha256(model) != str(policy.get("model_digest") or ""):
        raise ValueError("MODEL_DIGEST_MISMATCH")
    return exe, model

def server_argv(policy: dict[str, Any]) -> list[str]:
    policy = require_policy(policy)
    exe, model = artifacts(policy)
    endpoint = policy["endpoint"]
    limits = policy.get("limits") or {}
    argv = [str(exe), "-m", str(model), "--host", str(endpoint["host"]),
            "--port", str(int(endpoint["port"])), "-c", str(int(limits["context_tokens"])),
            "-t", str(int(limits["threads"])), "-tb", str(int(limits["threads_batch"])),
            "-b", str(int(limits["batch_size"])), "-np", str(int(limits["parallel_slots"])),
            "--reasoning", "off", "--no-webui", "--no-slots"]
    if any(x == "--rpc" or x.startswith("--rpc=") for x in argv):
        raise ValueError("RPC_FORBIDDEN")
    return argv


def provider_manifest(policy: dict[str, Any]) -> dict[str, Any]:
    require_policy(policy)
    exe, model = artifacts(policy)
    res = policy.get("resources") or {}
    return {"schema": PROVIDER_MANIFEST_SCHEMA, "provider_id": policy["provider_id"],
            "execution": "vps", "inference_network_access": "none", "cost_class": "owned",
            "automatic_external_spend_eur": 0, "executable": str(exe), "model_artifact": str(model),
            "model_digest": sha256(model), "capabilities": list(policy.get("capabilities") or []),
            "memory_required_mb": int(res["memory_required_mb"]), "disk_required_mb": int(res["disk_required_mb"]),
            "structured_adapter": True, "rollback_ready": True,
            "production_activation_authorized": False}

def resource_snapshot(policy: dict[str, Any]) -> dict[str, Any]:
    require_policy(policy)
    mem_kb = 0
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            mem_kb = int(line.split()[1]); break
    model = Path(str(policy["model_artifact"]))
    stat = os.statvfs(str(model.parent if model.parent.exists() else Path("/")))
    return {"schema": RESOURCE_SCHEMA, "available_memory_mb": mem_kb // 1024,
            "free_disk_mb": (stat.f_bavail * stat.f_frsize) // (1024 * 1024),
            "automatic_external_spend_eur": 0}


def health_snapshot(policy: dict[str, Any]) -> dict[str, Any]:
    require_policy(policy); artifacts(policy)
    endpoint = policy["endpoint"]
    url = f"http://{endpoint['host']}:{int(endpoint['port'])}/health"
    state = "UNAVAILABLE"; payload: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if str(payload.get("status") or "").lower() in {"ok", "pass"}:
            state = "HEALTHY"
    except Exception:
        state = "UNAVAILABLE"
    return {"schema": HEALTH_SCHEMA, "providers": {policy["provider_id"]:
            {"state": state, "source": "native-local-loopback-probe", "endpoint": url,
             "artifact_digests_verified": True}}, "automatic_external_spend_eur": 0}

def request_local(policy: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    require_policy(policy); artifacts(policy)
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError("REQUEST_SCHEMA_MISMATCH")
    limits = policy.get("limits") or {}; cap = int(limits.get("max_output_tokens") or 64)
    asked = max(1, int(request.get("max_tokens") or cap)); max_tokens = min(asked, cap)
    messages = request.get("messages") or []
    if not messages or not all(isinstance(x, dict) for x in messages):
        raise ValueError("MESSAGES_REQUIRED")
    guardrail = str(policy.get("system_guardrail") or "").strip()
    if not guardrail:
        raise ValueError("SYSTEM_GUARDRAIL_REQUIRED")
    if str(messages[0].get("role") or "") == "system":
        merged = guardrail + "\n\n" + str(messages[0].get("content") or "")
        governed_messages = [{"role": "system", "content": merged}, *messages[1:]]
    else:
        governed_messages = [{"role": "system", "content": guardrail}, *messages]
    endpoint = policy["endpoint"]
    body = {"model": "native-local", "messages": governed_messages, "temperature": 0,
            "max_tokens": max_tokens, "stream": False}
    if request.get("response_format"):
        body["response_format"] = request["response_format"]
    url = f"http://{endpoint['host']}:{int(endpoint['port'])}/v1/chat/completions"
    http = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(http, timeout=int(limits.get("request_timeout_seconds") or 30)) as response:
        raw = json.loads(response.read().decode("utf-8"))
    msg = ((raw.get("choices") or [{}])[0].get("message") or {})
    return {"schema": "chacha.dev/local-cognitive-response/v1", "status": "PASS",
            "provider_id": policy["provider_id"], "gateway": "native-local",
            "content": msg.get("content", ""), "reasoning_content": msg.get("reasoning_content"),
            "usage": raw.get("usage") or {}, "max_tokens_effective": max_tokens,
            "production_activation_authorized": False, "automatic_external_spend_eur": 0}

def catalog(policy: dict[str, Any], health: dict[str, Any]) -> dict[str, Any]:
    require_policy(policy); artifacts(policy)
    provider = policy["provider_id"]
    state = ((health.get("providers") or {}).get(provider) or {}).get("state", "UNKNOWN")
    scoring = policy.get("scoring") or {}
    return {"schema": CATALOG_SCHEMA, "models": [{
        "id": str(policy.get("model_id") or "native-local:qwen3.5-0.8b-q4_0"),
        "gateway": "native-local", "provider": provider, "model": str(policy.get("model_name") or "Qwen3.5-0.8B-Q4_0"),
        "model_tiers": list(policy.get("model_tiers") or ["local-private", "local-light"]),
        "status": "PILOT", "health_state": state, "quota_state": "AVAILABLE",
        "cost_class": "owned", "locality": "local", "context_window": int((policy.get("limits") or {})["context_tokens"]),
        "quality_score": float(scoring.get("quality_score", 50)),
        "latency_score": float(scoring.get("latency_score", 35)),
        "evidence_score": float(scoring.get("evidence_score", 85))}],
        "sources": [{"gateway": "native-local", "observed_at": "runtime-probe"}],
        "automatic_external_spend_eur": 0, "network_access_performed": False}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--policy", type=Path, required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("argv", "manifest", "resources", "health", "catalog"):
        p = sub.add_parser(name); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("request"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    sub.add_parser("exec")
    a = ap.parse_args(); policy = require_policy(load(a.policy))
    if a.cmd == "exec":
        argv = server_argv(policy); os.execv(argv[0], argv)
    if a.cmd == "argv":
        out = {"schema": "chacha.dev/local-cognitive-runtime-argv/v1", "argv": server_argv(policy),
               "rpc_allowed": False, "production_activation_authorized": False, "automatic_external_spend_eur": 0}
    elif a.cmd == "manifest": out = provider_manifest(policy)
    elif a.cmd == "resources": out = resource_snapshot(policy)
    elif a.cmd == "health": out = health_snapshot(policy)
    elif a.cmd == "request": out = request_local(policy, load(a.input))
    elif a.cmd == "catalog":
        health = health_snapshot(policy); out = catalog(policy, health)
    else: raise ValueError("UNKNOWN_COMMAND")
    save(a.output, out)
    print("LOCAL_COGNITIVE_RUNTIME=" + str(out.get("status") or "PASS"))
    print("PRODUCTION_ACTIVATION_AUTHORIZED=NO")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
