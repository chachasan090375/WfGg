import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "architecture-specialist-adapter.py"

spec = importlib.util.spec_from_file_location("architecture_specialist_adapter", ADAPTER)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def status_envelope():
    return {
        "schema": "chacha.dev/dispatch-envelope/v1",
        "project": "fixture",
        "transition": "DESIGN->DESIGN",
        "run_id": "fixture-run",
        "wave": 1,
        "task": {
            "id": "architecture-specialist:status",
            "kind": "runtime-status",
            "description": "fixture",
            "owner_role": "sre-observability-engineer",
            "permission": "read",
            "outputs": [],
            "verification": {"mode": "machine"},
        },
        "bindings": [{
            "capability": "architecture-audit",
            "provider": "chacha-dev-architect",
            "adapter": "architecture-specialist-adapter",
            "fallback_used": False,
            "health_state": "HEALTHY",
        }],
        "policy_context": {
            "resource_class": "light",
            "requires_storage_preflight": False,
            "human_approval_required": False,
            "approval_id": None,
            "timeout_seconds": 30,
        },
        "workspace": None,
        "metadata": {"architecture_specialist": {"action": "status"}},
    }


def design_envelope(root: pathlib.Path):
    project = "wfgg-radar"
    req_id = "REQ-1"
    td = root / project / "technical-design"
    td.mkdir(parents=True, exist_ok=True)
    req = td / f"{req_id}.requirement.json"
    manifest = td / f"{req_id}.manifest.v3.json"
    plan = td / f"{req_id}.technical-design.json"
    req.write_text(json.dumps({
        "schema": "chacha.dev/product-requirement/v1",
        "project": project,
        "id": req_id,
        "title": "x",
        "objective": "x",
        "functional_requirements": ["x"],
        "acceptance_criteria": ["x"],
        "constraints": [],
        "source": {"kind": "other", "reference": "fixture"},
    }))
    manifest.write_text(json.dumps({
        "schema": "chacha.dev/project-manifest/v3",
        "identity": {"slug": project},
        "ownership": {},
        "components": [{"id": "radar-worker", "type": "worker-edge", "path": "radar-worker"}],
        "dependencies": [],
    }))
    plan.write_text(json.dumps({
        "schema": "chacha.dev/technical-design-plan/v1",
        "project": project,
        "requirement_id": req_id,
        "affected_components": ["radar-worker"],
        "specialist_assignments": [{
            "role": "backend-api-architect",
            "primary": True,
            "reason": ["fixture"],
            "capabilities": ["api-contract-review"],
            "responsibilities": ["design"],
            "outputs": ["api-contract"],
            "review_roles": ["test-engineer"],
        }],
        "architecture_decisions": [{
            "id": "API_CONTRACT",
            "owner_role": "backend-api-architect",
            "status": "REQUIRED",
            "question": "q",
            "required_output": "api-contract",
            "constraints": [],
        }],
        "cross_reviews": [],
        "implementation_gate": {
            "code_generation_allowed": False,
            "blocking_reasons": ["specialist-design-fragments-not-yet-produced"],
            "required_before_implementation": ["all-primary-specialist-contracts-complete"],
        },
    }))
    return {
        "schema": "chacha.dev/dispatch-envelope/v1",
        "project": project,
        "transition": "PRODUCT_REQUIREMENT->TECHNICAL_DESIGN",
        "run_id": "run-1",
        "wave": 1,
        "task": {
            "id": "design:backend-api-architect",
            "kind": "artifact",
            "description": "fixture",
            "owner_role": "backend-api-architect",
            "permission": "plan",
            "outputs": [{"type": "artifact", "id": "technical-design-fragment:backend-api-architect"}],
            "verification": {"mode": "independent-agent"},
        },
        "bindings": [{
            "capability": "architecture-audit",
            "provider": "chacha-dev-architect",
            "adapter": "architecture-specialist-adapter",
            "fallback_used": False,
            "health_state": "HEALTHY",
        }],
        "policy_context": {
            "resource_class": "light",
            "requires_storage_preflight": False,
            "human_approval_required": False,
            "approval_id": None,
            "timeout_seconds": 180,
        },
        "workspace": None,
        "metadata": {
            "specialist_role": "backend-api-architect",
            "design_outputs": ["api-contract"],
            "technical_design_context": {
                "requirement_path": str(req),
                "manifest_path": str(manifest),
                "technical_design_plan_path": str(plan),
                "requirement_id": req_id,
                "project": project,
            },
        },
    }


class ArchitectureSpecialistAdapterContract(unittest.TestCase):
    def test_status_contract(self):
        action, data, err = mod.validate_request(status_envelope())
        self.assertIsNone(err)
        self.assertEqual(action, "status")
        self.assertEqual(data["action"], "status")

    def test_binding_must_be_healthy(self):
        req = status_envelope()
        req["bindings"][0]["health_state"] = "DEGRADED"
        _action, _data, err = mod.validate_request(req)
        self.assertEqual(err, "ARCHITECT_PROVIDER_NOT_HEALTHY")

    def test_design_requires_plan_permission_and_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            req = design_envelope(root)
            with mock.patch.object(mod, "PLANS_ROOT", root):
                action, data, err = mod.validate_request(req)
                self.assertIsNone(err)
                self.assertEqual(action, "design")
                self.assertEqual(data["role"], "backend-api-architect")
                model_context, _run_dir = mod.build_model_context(req, data["role"], data["context"])
                self.assertEqual(model_context["project"], "wfgg-radar")
                self.assertEqual(model_context["artifact_kind"], "design-fragment")
                self.assertEqual(
                    model_context["technical_design"]["assignment"]["role"],
                    "backend-api-architect",
                )
            req["task"]["permission"] = "workspace-write"
            _action, _data, err = mod.validate_request(req)
            self.assertEqual(err, "ARCHITECT_DESIGN_PERMISSION_REQUIRED:plan")

    def test_context_paths_cannot_escape_runtime_plan_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            req = design_envelope(root)
            req["metadata"]["technical_design_context"]["manifest_path"] = "/etc/passwd"
            with mock.patch.object(mod, "PLANS_ROOT", root):
                with self.assertRaisesRegex(ValueError, "MANIFEST_PATH_OUTSIDE_RUNTIME_PLAN_ROOT"):
                    mod.build_model_context(
                        req,
                        "backend-api-architect",
                        req["metadata"]["technical_design_context"],
                    )

    def test_custom_agent_has_zero_tools(self):
        agent = mod.custom_agent_markdown()
        self.assertIn("tools: []", agent)
        self.assertIn("Do not call tools", agent)

    def test_backend_output_identity_is_enforced(self):
        context = {
            "project": "wfgg-radar",
            "requirement_id": "REQ-1",
            "task_id": "design:backend-api-architect",
            "role": "backend-api-architect",
            "artifact_kind": "design-fragment",
        }
        artifact = {
            "schema": mod.SPECIALIST_SCHEMA,
            "project": "wfgg-radar",
            "requirement_id": "REQ-1",
            "task_id": "design:backend-api-architect",
            "role": "backend-api-architect",
            "artifact_kind": "design-fragment",
            "status": "PROPOSED",
            "summary": "x",
            "decisions": [],
            "recommendations": [],
            "risks": [],
            "unresolved_questions": [],
            "acceptance_obligations": [],
            "implementation_constraints": [],
            "source_references": [],
        }
        mod.validate_specialist_artifact(artifact, context)
        artifact["project"] = "other"
        with self.assertRaisesRegex(ValueError, "ARCHITECT_SPECIALIST_IDENTITY_MISMATCH:project"):
            mod.validate_specialist_artifact(artifact, context)

    def test_no_shell_or_implicit_permission_bypass(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system(", source)
        self.assertNotIn("--dangerously-skip-permissions", source)
        self.assertIn("--sandbox", source)
        self.assertIn("--agent", source)

    def test_model_context_is_bounded(self):
        context = {
            "project": "wfgg-radar",
            "requirement_id": "REQ-1",
            "task_id": "x",
            "role": "backend-api-architect",
            "artifact_kind": "design-fragment",
            "blob": "x" * (mod.MAX_PROMPT_BYTES + 1),
        }
        with self.assertRaisesRegex(ValueError, "ARCHITECT_CONTEXT_TOO_LARGE"):
            mod.prompt_for(context)


if __name__ == "__main__":
    unittest.main()
