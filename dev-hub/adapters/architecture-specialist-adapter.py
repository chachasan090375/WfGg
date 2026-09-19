#!/usr/bin/env python3
"""ChaCha DEV HUB Architecture Specialist Adapter V1.

Provider-specific, planning-only runtime for ChaCha Dev Architect specialist roles.

The adapter invokes the already-installed Antigravity CLI wrapper in headless mode
through a workspace-scoped custom agent with an empty tools list. The model gets a
self-contained, bounded design context and can return only a structured technical
design artifact. It cannot choose its executable, access production through this
adapter, write project source code, or self-verify its output.

Supported actions:
- status: read-only runtime/version probe
- inference-probe: planning-only structured model smoke probe
- design: planning-only specialist design/review/ADR artifact
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
SPECIALIST_SCHEMA = "chacha.dev/architecture-specialist-output/v1"
ADAPTER_ID = "architecture-specialist-adapter"
PROVIDER_ID = "chacha-dev-architect"

BACKEND = Path("/usr/local/bin/agy-dev")
MODEL = os.environ.get("CHACHA_DEV_ARCHITECT_MODEL", "gemini-3.8-flash-medium")
PLANS_ROOT = Path(os.environ.get("CHACHA_DEV_PLANS_ROOT", "/opt/chacha-dev/runtime/plans"))
RESULT_ROOT = Path(os.environ.get(
    "CHACHA_DEV_ARCHITECT_RESULT_ROOT",
    "/opt/chacha-dev/runtime/technical-design-results",
))
MAX_INPUT_BYTES = 192 * 1024
MAX_PROMPT_BYTES = 64 * 1024
MAX_BACKEND_STDOUT = 512 * 1024
ABSOLUTE_MAX_TIMEOUT = 300

SPECIALIST_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema", "project", "requirement_id", "task_id", "role",
        "artifact_kind", "status", "summary", "decisions", "recommendations",
        "risks", "unresolved_questions", "acceptance_obligations",
        "implementation_constraints", "source_references",
    ],
    "properties": {
        "schema": {"const": SPECIALIST_SCHEMA},
        "project": {"type": "string", "minLength": 1},
        "requirement_id": {"type": "string", "minLength": 1},
        "task_id": {"type": "string", "minLength": 1},
        "role": {"type": "string", "minLength": 1},
        "artifact_kind": {"enum": ["design-fragment", "cross-review", "adr-set"]},
        "status": {"enum": ["PROPOSED", "BLOCKED"]},
        "summary": {"type": "string", "minLength": 1},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id", "decision", "rationale", "confidence",
                    "alternatives", "evidence_needed",
                ],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "decision": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                    "confidence": {"enum": ["LOW", "MEDIUM", "HIGH"]},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "evidence_needed": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "recommendations": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "severity", "description", "mitigation"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "severity": {"enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
                    "description": {"type": "string", "minLength": 1},
                    "mitigation": {"type": "string", "minLength": 1},
                },
            },
        },
        "unresolved_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question", "owner", "blocking"],
                "properties": {
                    "question": {"type": "string", "minLength": 1},
                    "owner": {
                        "enum": ["product-owner", "specialist", "runtime-evidence", "cross-review"]
                    },
                    "blocking": {"type": "boolean"},
                },
            },
        },
        "acceptance_obligations": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "implementation_constraints": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "source_references": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "reviewed_roles": {
            "type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True
        },
        "adr_records": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title", "status", "decision", "consequences"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "status": {"enum": ["PROPOSED", "ACCEPTED", "DEFERRED"]},
                    "decision": {"type": "string", "minLength": 1},
                    "consequences": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)[:160] or "unknown"


def result(
    request: dict[str, Any],
    status: str,
    summary: str,
    evidence: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
            "notes": "Architecture specialist output requires independent verification and cross-review.",
        },
        "outputs": outputs or [],
    }


def emit(value: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


def blocked(request: dict[str, Any], reason: str) -> int:
    return emit(
        result(
            request,
            "BLOCKED",
            reason,
            [{
                "kind": "report",
                "source": "architecture-specialist-adapter-policy",
                "digest": sha256_bytes(reason.encode("utf-8")),
                "details": {"reason": reason},
            }],
        ),
        2,
    )


def run(
    argv: list[str],
    *,
    timeout: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
        cwd=str(cwd) if cwd else None,
        env=env or os.environ.copy(),
    )


def timeout_from(request: dict[str, Any]) -> int:
    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    try:
        value = int(policy.get("timeout_seconds") or 180)
    except Exception:
        value = 180
    return max(30, min(value, ABSOLUTE_MAX_TIMEOUT))


def validate_binding(request: dict[str, Any]) -> str | None:
    bindings = request.get("bindings")
    if not isinstance(bindings, list):
        return "ARCHITECT_BINDING_MISSING"
    matches = [
        x for x in bindings
        if isinstance(x, dict)
        and x.get("provider") == PROVIDER_ID
        and x.get("adapter") == ADAPTER_ID
    ]
    if not matches:
        return "ARCHITECT_BINDING_MISSING"
    if any(x.get("health_state") != "HEALTHY" for x in matches):
        return "ARCHITECT_PROVIDER_NOT_HEALTHY"
    return None


def validate_request(request: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, None, "INPUT_SCHEMA_INVALID"
    if not isinstance(request.get("task"), dict) or not (request.get("task") or {}).get("id"):
        return None, None, "TASK_ID_MISSING"
    err = validate_binding(request)
    if err:
        return None, None, err
    task = request["task"]
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    runtime = metadata.get("architecture_specialist")
    if isinstance(runtime, dict) and runtime.get("action") == "status":
        if task.get("permission") != "read":
            return None, None, "ARCHITECT_STATUS_PERMISSION_REQUIRED:read"
        return "status", runtime, None
    if isinstance(runtime, dict) and runtime.get("action") == "inference-probe":
        if task.get("permission") != "plan":
            return None, None, "ARCHITECT_INFERENCE_PROBE_PERMISSION_REQUIRED:plan"
        return "inference-probe", runtime, None

    context = metadata.get("technical_design_context")
    role = str(metadata.get("specialist_role") or task.get("owner_role") or "")
    if not isinstance(context, dict):
        return None, None, "TECHNICAL_DESIGN_CONTEXT_MISSING"
    if task.get("permission") != "plan":
        return None, None, "ARCHITECT_DESIGN_PERMISSION_REQUIRED:plan"
    if not role:
        return None, None, "SPECIALIST_ROLE_MISSING"
    return "design", {"context": context, "role": role, "metadata": metadata}, None


def backend_status() -> tuple[dict[str, Any], str | None]:
    if not BACKEND.is_file() or not os.access(BACKEND, os.X_OK):
        return {"backend": str(BACKEND), "available": False}, "ARCHITECT_BACKEND_MISSING"
    try:
        proc = run([str(BACKEND), "--version"], timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"backend": str(BACKEND), "available": False}, f"ARCHITECT_BACKEND_ERROR:{type(exc).__name__}"
    version = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not version:
        return {
            "backend": str(BACKEND), "available": False,
            "returncode": proc.returncode,
        }, "ARCHITECT_BACKEND_VERSION_FAILED"
    return {
        "backend": str(BACKEND),
        "available": True,
        "version": version.splitlines()[0][:200],
        "backend_sha256": sha256_file(BACKEND),
        "model": MODEL,
    }, None


def under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def load_bounded_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}_MISSING")
    size = path.stat().st_size
    if size <= 0 or size > MAX_INPUT_BYTES:
        raise ValueError(f"{label}_SIZE_INVALID")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"{label}_JSON_INVALID:{type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}_ROOT_INVALID")
    return value


def context_paths(project: str, context: dict[str, Any]) -> tuple[Path, Path, Path, str]:
    requirement = Path(str(context.get("requirement_path") or ""))
    manifest = Path(str(context.get("manifest_path") or ""))
    plan = Path(str(context.get("technical_design_plan_path") or ""))
    requirement_id = str(context.get("requirement_id") or "")
    expected_root = PLANS_ROOT / safe_name(project) / "technical-design"
    for path, label in (
        (requirement, "REQUIREMENT_PATH"),
        (manifest, "MANIFEST_PATH"),
        (plan, "TECHNICAL_DESIGN_PLAN_PATH"),
    ):
        if not path.is_absolute() or not under_root(path, expected_root):
            raise ValueError(f"{label}_OUTSIDE_RUNTIME_PLAN_ROOT")
    if not requirement_id:
        raise ValueError("REQUIREMENT_ID_MISSING")
    return requirement, manifest, plan, requirement_id


def compact_manifest(manifest: dict[str, Any], affected: set[str]) -> dict[str, Any]:
    components = [
        c for c in manifest.get("components") or []
        if isinstance(c, dict) and str(c.get("id") or "") in affected
    ]
    return {
        "schema": manifest.get("schema"),
        "identity": manifest.get("identity"),
        "ownership": manifest.get("ownership"),
        "components": components,
        "dependencies": manifest.get("dependencies") or [],
        "security": manifest.get("security") or {},
        "data": manifest.get("data") or {},
        "observability": manifest.get("observability") or {},
        "recovery": manifest.get("recovery") or {},
        "technology_policy": manifest.get("technology_policy") or {},
    }


def previous_artifacts(run_dir: Path, current_role: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not run_dir.is_dir():
        return out
    for path in sorted(run_dir.glob("*.json")):
        try:
            x = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(x, dict) or x.get("schema") != SPECIALIST_SCHEMA:
            continue
        if x.get("role") == current_role and x.get("artifact_kind") == "design-fragment":
            continue
        out.append({
            "role": x.get("role"),
            "artifact_kind": x.get("artifact_kind"),
            "status": x.get("status"),
            "summary": x.get("summary"),
            "decisions": x.get("decisions") or [],
            "risks": x.get("risks") or [],
            "unresolved_questions": x.get("unresolved_questions") or [],
            "acceptance_obligations": x.get("acceptance_obligations") or [],
            "implementation_constraints": x.get("implementation_constraints") or [],
            "reviewed_roles": x.get("reviewed_roles") or [],
            "adr_records": x.get("adr_records") or [],
        })
    return out


def expected_artifact_kind(task_id: str, role: str) -> str:
    if task_id.startswith("design-review:"):
        return "cross-review"
    if role == "documentation-adr-agent":
        return "adr-set"
    return "design-fragment"


def build_model_context(
    request: dict[str, Any],
    role: str,
    context: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    project = str(request.get("project") or "")
    requirement_path, manifest_path, plan_path, requirement_id = context_paths(project, context)
    requirement = load_bounded_json(requirement_path, "REQUIREMENT")
    manifest = load_bounded_json(manifest_path, "MANIFEST")
    plan = load_bounded_json(plan_path, "TECHNICAL_DESIGN_PLAN")

    if requirement.get("project") != project or plan.get("project") != project:
        raise ValueError("ARCHITECT_CONTEXT_PROJECT_MISMATCH")
    if requirement.get("id") != requirement_id or plan.get("requirement_id") != requirement_id:
        raise ValueError("ARCHITECT_CONTEXT_REQUIREMENT_MISMATCH")

    assignment = next(
        (x for x in plan.get("specialist_assignments") or []
         if isinstance(x, dict) and x.get("role") == role),
        None,
    )
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    task_id = str((request.get("task") or {}).get("id") or "")
    review_roles = [str(x) for x in metadata.get("review_subject_roles") or []]

    if assignment is None and not task_id.startswith("design-review:"):
        raise ValueError("SPECIALIST_ASSIGNMENT_NOT_FOUND")

    decisions = [
        x for x in plan.get("architecture_decisions") or []
        if isinstance(x, dict) and x.get("owner_role") == role
    ]
    affected = {str(x) for x in plan.get("affected_components") or []}

    run_id = safe_name(str(request.get("run_id") or "run"))
    run_dir = RESULT_ROOT / safe_name(project) / safe_name(requirement_id) / run_id

    model_context = {
        "project": project,
        "requirement_id": requirement_id,
        "task_id": task_id,
        "role": role,
        "artifact_kind": expected_artifact_kind(task_id, role),
        "requirement": requirement,
        "manifest": compact_manifest(manifest, affected),
        "technical_design": {
            "affected_components": sorted(affected),
            "assignment": assignment,
            "owned_architecture_decisions": decisions,
            "cross_reviews": plan.get("cross_reviews") or [],
            "implementation_gate": plan.get("implementation_gate") or {},
        },
        "task_metadata": {
            "design_outputs": metadata.get("design_outputs") or [],
            "review_subject_roles": review_roles,
        },
        "prior_specialist_artifacts": previous_artifacts(run_dir, role),
    }
    return model_context, run_dir


def custom_agent_markdown() -> str:
    return """---
name: chacha-architecture-specialist
description: Planning-only ChaCha DEV architecture specialist. Produces structured design artifacts from supplied context.
tools: []
mainAgent: true
subagent: false
---
You are a specialist inside ChaCha DEV's architecture control plane.

Rules:
- Work only from the JSON context supplied in the prompt.
- Do not call tools, commands, web, MCP, files, or external systems.
- Do not generate implementation code.
- Do not claim runtime facts that are not in the supplied context.
- Preserve explicit product requirements and must-preserve constraints.
- Existing architecture is preferred unless a documented requirement justifies change.
- Mark uncertainty explicitly; blocking uncertainty belongs in unresolved_questions.
- Never claim verification. Your output is a proposal requiring independent review.
- Return only the JSON object required by the provided JSON schema.
"""


def prompt_for(model_context: dict[str, Any]) -> str:
    prefix = (
        "Produce the architecture specialist artifact for the following ChaCha DEV context. "
        "Resolve only decisions owned by your role. Cross-review tasks must critique the supplied "
        "prior artifacts and identify conflicts. ADR tasks must synthesize consequential decisions "
        "without silently resolving unresolved product questions. "
        "Every recommendation must respect acceptance criteria and implementation constraints.\n\n"
        "CONTEXT_JSON=\n"
    )
    raw = json.dumps(model_context, ensure_ascii=False, separators=(",", ":"))
    prompt = prefix + raw
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError("ARCHITECT_CONTEXT_TOO_LARGE")
    return prompt


def parse_backend_envelope(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(raw) > MAX_BACKEND_STDOUT:
        raise ValueError("ARCHITECT_BACKEND_OUTPUT_TOO_LARGE")
    text = raw.decode("utf-8", "strict").strip()
    try:
        envelope = json.loads(text, strict=False)
    except Exception as exc:
        raise ValueError(f"ARCHITECT_BACKEND_ENVELOPE_INVALID:{type(exc).__name__}") from exc
    if not isinstance(envelope, dict):
        raise ValueError("ARCHITECT_BACKEND_ENVELOPE_NOT_OBJECT")
    if envelope.get("status") != "SUCCESS":
        raise ValueError("ARCHITECT_BACKEND_STATUS_NOT_SUCCESS")
    structured = envelope.get("structured_output")
    response = envelope.get("response")
    if isinstance(structured, dict):
        artifact = structured
    elif isinstance(response, dict):
        artifact = response
    elif isinstance(response, str):
        try:
            artifact = json.loads(response.strip(), strict=False)
        except Exception as exc:
            raise ValueError(f"ARCHITECT_SPECIALIST_JSON_INVALID:{type(exc).__name__}") from exc
    else:
        raise ValueError("ARCHITECT_SPECIALIST_RESPONSE_MISSING")
    if not isinstance(artifact, dict):
        raise ValueError("ARCHITECT_SPECIALIST_RESPONSE_NOT_OBJECT")
    return envelope, artifact


def validate_specialist_artifact(
    artifact: dict[str, Any],
    model_context: dict[str, Any],
) -> None:
    required = {
        "schema", "project", "requirement_id", "task_id", "role", "artifact_kind",
        "status", "summary", "decisions", "recommendations", "risks",
        "unresolved_questions", "acceptance_obligations", "implementation_constraints",
        "source_references",
    }
    missing = sorted(required - set(artifact))
    if missing:
        raise ValueError("ARCHITECT_SPECIALIST_FIELDS_MISSING:" + ",".join(missing))
    exact = {
        "schema": SPECIALIST_SCHEMA,
        "project": model_context["project"],
        "requirement_id": model_context["requirement_id"],
        "task_id": model_context["task_id"],
        "role": model_context["role"],
        "artifact_kind": model_context["artifact_kind"],
    }
    for key, expected in exact.items():
        if artifact.get(key) != expected:
            raise ValueError(f"ARCHITECT_SPECIALIST_IDENTITY_MISMATCH:{key}")
    if artifact.get("status") not in {"PROPOSED", "BLOCKED"}:
        raise ValueError("ARCHITECT_SPECIALIST_STATUS_INVALID")
    for key in (
        "decisions", "recommendations", "risks", "unresolved_questions",
        "acceptance_obligations", "implementation_constraints", "source_references",
    ):
        if not isinstance(artifact.get(key), list):
            raise ValueError(f"ARCHITECT_SPECIALIST_FIELD_NOT_LIST:{key}")


def classify_backend_failure(stdout: bytes, stderr: bytes) -> str:
    text = (stdout + b"\n" + stderr).decode("utf-8", "replace").lower()
    checks = [
        ("quota", ("quota", "429", "resource_exhausted")),
        ("model", ("model not found", "unknown model", "unsupported model", "invalid model")),
        ("sandbox", ("nsjail", "sandbox", "appcontainer", "sandbox-exec")),
        ("agent", ("agent not found", "unknown agent", "invalid agent")),
        ("auth", ("unauthenticated", "authentication", "api key", "permission denied")),
        ("location", ("location", "region", "country")),
        ("network", ("network", "connection", "dns", "timeout")),
        ("schema", ("json schema", "structured output", "schema")),
    ]
    for label, needles in checks:
        if any(x in text for x in needles):
            return label
    return "unknown"


def execute_design(request: dict[str, Any], design: dict[str, Any]) -> int:
    status, status_error = backend_status()
    if status_error:
        return blocked(request, status_error)

    role = str(design["role"])
    context = design["context"]
    try:
        model_context, run_dir = build_model_context(request, role, context)
        prompt = prompt_for(model_context)
    except ValueError as exc:
        return blocked(request, str(exc))

    timeout = timeout_from(request)
    with tempfile.TemporaryDirectory(prefix="chacha-architect-") as td:
        workspace = Path(td)
        agent_dir = workspace / ".agents" / "agents" / "chacha-architecture-specialist"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "agent.md").write_text(custom_agent_markdown(), encoding="utf-8")
        schema_path = workspace / "specialist-output.schema.json"
        schema_path.write_text(
            json.dumps(SPECIALIST_JSON_SCHEMA, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["CI"] = "1"
        env["NO_COLOR"] = "1"
        try:
            proc = run(
                [
                    str(BACKEND),
                    "-p", prompt,
                    "--model", MODEL,
                    "--agent", "chacha-architecture-specialist",
                    "--output-format", "json",
                    "--json-schema", str(schema_path),
                    "--print-timeout", f"{timeout}s",
                    "--sandbox",
                ],
                timeout=timeout + 20,
                cwd=workspace,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return emit(result(request, "FAILED", "ARCHITECT_BACKEND_TIMEOUT"))
        except OSError as exc:
            return emit(result(request, "FAILED", f"ARCHITECT_BACKEND_START_FAILED:{type(exc).__name__}"))

    if proc.returncode != 0:
        digest = sha256_bytes(proc.stdout[:65536] + proc.stderr[:65536])
        return emit(result(request, "FAILED", "ARCHITECT_BACKEND_FAILED", [{
            "kind": "command",
            "source": "local://antigravity-headless",
            "digest": digest,
            "details": {
                "returncode": proc.returncode,
                "backend_version": status.get("version"),
                "model": MODEL,
                "failure_class": classify_backend_failure(proc.stdout, proc.stderr),
            },
        }]))

    try:
        backend_envelope, artifact = parse_backend_envelope(proc.stdout)
        validate_specialist_artifact(artifact, model_context)
    except (UnicodeDecodeError, ValueError) as exc:
        return emit(result(request, "FAILED", str(exc)))

    run_dir.mkdir(parents=True, exist_ok=True)
    task_id = safe_name(model_context["task_id"])
    artifact_path = run_dir / f"{task_id}.json"
    tmp = artifact_path.with_suffix(".json.tmp")
    raw = json.dumps(artifact, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    tmp.write_bytes(raw)
    os.chmod(tmp, 0o640)
    os.replace(tmp, artifact_path)
    digest = sha256_file(artifact_path)

    blocking_questions = [
        q for q in artifact.get("unresolved_questions") or []
        if isinstance(q, dict) and q.get("blocking") is True
    ]
    task_status = "BLOCKED" if artifact.get("status") == "BLOCKED" or blocking_questions else "OK"

    usage = backend_envelope.get("usage") if isinstance(backend_envelope.get("usage"), dict) else {}
    evidence = [{
        "kind": "report",
        "source": str(artifact_path),
        "digest": digest,
        "details": {
            "role": role,
            "artifact_kind": artifact.get("artifact_kind"),
            "backend": "antigravity",
            "backend_version": status.get("version"),
            "model": MODEL,
            "conversation_id": backend_envelope.get("conversation_id"),
            "usage": {
                k: usage.get(k) for k in (
                    "input_tokens", "output_tokens", "thinking_tokens",
                    "cache_read_tokens", "total_tokens",
                ) if isinstance(usage.get(k), (int, float))
            },
            "tool_access": "DENIED_BY_CUSTOM_AGENT",
            "implementation_execution": False,
            "blocking_questions": len(blocking_questions),
        },
    }]
    outputs = [{
        "type": x.get("type"),
        "id": x.get("id"),
        "status": "UNVERIFIED",
        "reason": "Specialist proposal produced; independent verification and cross-review required.",
    } for x in (request.get("task") or {}).get("outputs") or [] if isinstance(x, dict)]

    summary = "ARCHITECT_SPECIALIST_DESIGN_PRODUCED" if task_status == "OK" else "ARCHITECT_SPECIALIST_DESIGN_BLOCKED"
    return emit(result(request, task_status, summary, evidence, outputs), 0 if task_status == "OK" else 2)


def execute_inference_probe(request: dict[str, Any]) -> int:
    status, status_error = backend_status()
    if status_error:
        return blocked(request, status_error)

    probe_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "probe", "tool_use"],
        "properties": {
            "schema": {"const": "chacha.dev/architecture-specialist-inference-probe/v1"},
            "probe": {"const": "PASS"},
            "tool_use": {"const": False},
        },
    }
    prompt = (
        "This is a ChaCha DEV runtime contract probe. Do not use tools. "
        "Return only the JSON object required by the supplied JSON schema with "
        "probe=PASS and tool_use=false."
    )
    timeout = timeout_from(request)
    with tempfile.TemporaryDirectory(prefix="chacha-architect-probe-") as td:
        workspace = Path(td)
        agent_dir = workspace / ".agents" / "agents" / "chacha-architecture-specialist"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "agent.md").write_text(custom_agent_markdown(), encoding="utf-8")
        schema_path = workspace / "probe.schema.json"
        schema_path.write_text(json.dumps(probe_schema, indent=2) + "\n", encoding="utf-8")
        env = os.environ.copy()
        env["CI"] = "1"
        env["NO_COLOR"] = "1"
        try:
            proc = run(
                [
                    str(BACKEND),
                    "-p", prompt,
                    "--model", MODEL,
                    "--agent", "chacha-architecture-specialist",
                    "--output-format", "json",
                    "--json-schema", str(schema_path),
                    "--print-timeout", f"{timeout}s",
                    "--sandbox",
                ],
                timeout=timeout + 20,
                cwd=workspace,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return emit(result(request, "FAILED", "ARCHITECT_INFERENCE_PROBE_TIMEOUT"))
        except OSError as exc:
            return emit(result(request, "FAILED", f"ARCHITECT_INFERENCE_PROBE_START_FAILED:{type(exc).__name__}"))

    digest = sha256_bytes(proc.stdout[:MAX_BACKEND_STDOUT] + proc.stderr[:65536])
    if proc.returncode != 0:
        return emit(result(request, "FAILED", "ARCHITECT_INFERENCE_PROBE_BACKEND_FAILED", [{
            "kind": "command",
            "source": "local://antigravity-headless/inference-probe",
            "digest": digest,
            "details": {
                "returncode": proc.returncode,
                "backend_version": status.get("version"),
                "model": MODEL,
                "failure_class": classify_backend_failure(proc.stdout, proc.stderr),
            },
        }]))
    try:
        envelope, artifact = parse_backend_envelope(proc.stdout)
    except (UnicodeDecodeError, ValueError) as exc:
        return emit(result(request, "FAILED", str(exc)))
    if artifact != {
        "schema": "chacha.dev/architecture-specialist-inference-probe/v1",
        "probe": "PASS",
        "tool_use": False,
    }:
        return emit(result(request, "FAILED", "ARCHITECT_INFERENCE_PROBE_RESPONSE_INVALID"))

    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    return emit(result(request, "OK", "ARCHITECTURE_SPECIALIST_INFERENCE_PROBE_PASS", [{
        "kind": "report",
        "source": "local://antigravity-headless/inference-probe",
        "digest": digest,
        "details": {
            "backend": "antigravity",
            "backend_version": status.get("version"),
            "model": MODEL,
            "conversation_id": envelope.get("conversation_id"),
            "tool_access": "DENIED_BY_CUSTOM_AGENT",
            "sandbox": True,
            "structured_output": True,
            "usage": {
                k: usage.get(k) for k in (
                    "input_tokens", "output_tokens", "thinking_tokens",
                    "cache_read_tokens", "total_tokens",
                ) if isinstance(usage.get(k), (int, float))
            },
        },
    }], [{
        "type": "gate",
        "id": "architecture-specialist-inference-runtime",
        "status": "UNVERIFIED",
        "reason": "Structured planning-only inference passed; independent verification required.",
    }]))


def execute_status(request: dict[str, Any]) -> int:
    status, error = backend_status()
    raw = json.dumps(status, sort_keys=True, separators=(",", ":")).encode("utf-8")
    evidence = [{
        "kind": "metric",
        "source": "local://architecture-specialist-runtime/status",
        "digest": sha256_bytes(raw),
        "details": status,
    }]
    if error:
        return emit(result(request, "BLOCKED", error, evidence), 2)
    return emit(result(request, "OK", "ARCHITECTURE_SPECIALIST_RUNTIME_READY", evidence, [{
        "type": "artifact",
        "id": "architecture-specialist-runtime-status",
        "status": "UNVERIFIED",
        "reason": "Runtime/version observed locally; inference path not exercised by status probe.",
    }]))


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", f"INPUT_JSON_INVALID:{type(exc).__name__}"), 2)
    if not isinstance(request, dict):
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", "INPUT_ROOT_NOT_OBJECT"), 2)

    action, data, error = validate_request(request)
    if error:
        return blocked(request, error)
    assert action and data is not None
    if action == "status":
        return execute_status(request)
    if action == "inference-probe":
        return execute_inference_probe(request)
    return execute_design(request, data)


if __name__ == "__main__":
    raise SystemExit(main())
