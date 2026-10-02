from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEV_HUB = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(DEV_HUB / "adapters"))

from canonical_component_registry_read import (
    FilesystemRuntimePathObserver,
    JsonCanonicalComponentRegistry,
)
from canonical_path_resolution.non_progress import AttemptSnapshot, NonProgressDetector
from canonical_path_resolution.recovery import AgentCapability, MultiAgentRecoveryRouter
from canonical_path_resolution.resolver import CanonicalPathResolver
from canonical_path_resolution.run_gate import GovernedRunGate


class _Catalogue:
    def __init__(self, agents):
        self._agents = agents

    def agents(self):
        return self._agents


def _load_governed_project_control():
    path = DEV_HUB / "bin/governed-project-control.py"
    spec = importlib.util.spec_from_file_location("governed_project_control", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_central_wrapper():
    path = DEV_HUB / "bin/central-interface-controller.py"
    spec = importlib.util.spec_from_file_location("governed_central_interface", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_policy_redirects_to_canonical_runtime_snapshot(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    snapshot = tmp_path / "canonical-component-registry.json"
    snapshot.write_text(json.dumps({
        "schema": "chacha.dev/canonical-component-registry-snapshot/v1",
        "components": [
            {
                "component_id": "p",
                "paths": {
                    "source_root": str(source),
                    "runtime_root": str(tmp_path / "runtime"),
                    "state_root": str(tmp_path / "runtime/state/p")
                }
            }
        ]
    }), encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({
        "schema": "chacha.dev/canonical-component-registry-policy/v1",
        "runtime_registry": {
            "canonical_snapshot": "/not-used-in-test.json"
        }
    }), encoding="utf-8")

    registry = JsonCanonicalComponentRegistry(policy, snapshot_override=snapshot)
    result = CanonicalPathResolver(
        registry,
        FilesystemRuntimePathObserver(registry),
    ).resolve("p", "source_root", verify=True)
    assert result.ok
    assert result.status.value == "RESOLVED"
    assert result.declared == str(source)
    assert registry.component_ids() == ("p",)


def test_registry_runtime_snapshot_change_is_observed_without_policy_change(tmp_path):
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    source_a.mkdir()
    source_b.mkdir()
    snapshot = tmp_path / "canonical-component-registry.json"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({
        "schema": "chacha.dev/canonical-component-registry-policy/v1",
        "runtime_registry": {"canonical_snapshot": "/not-used-in-test.json"}
    }), encoding="utf-8")

    def write_snapshot(source):
        snapshot.write_text(json.dumps({
            "schema": "chacha.dev/canonical-component-registry-snapshot/v1",
            "components": [{"component_id": "p", "paths": {"source_root": str(source)}}]
        }), encoding="utf-8")

    registry = JsonCanonicalComponentRegistry(policy, snapshot_override=snapshot)
    observer = FilesystemRuntimePathObserver(registry)
    resolver = CanonicalPathResolver(registry, observer)
    write_snapshot(source_a)
    before = resolver.resolve("p", "source_root", verify=True)
    write_snapshot(source_b)
    after = resolver.resolve("p", "source_root", verify=True)
    assert before.ok and after.ok
    assert before.declared == str(source_a)
    assert after.declared == str(source_b)


def test_governed_central_wrapper_forces_governed_project_control(tmp_path):
    module = _load_central_wrapper()
    args = [
        "--repo-root", str(tmp_path),
        "--project-control", "/tmp/ungoverned.py",
        "status", "--project", "chacha-dev-platform",
    ]
    command = module.governed_argv(args)
    assert command[1] == str(tmp_path / "dev-hub/bin/central-interface-controller-core.py")
    assert command[2:4] == [
        "--project-control",
        str(tmp_path / "dev-hub/bin/governed-project-control.py"),
    ]
    assert "/tmp/ungoverned.py" not in command


def test_identical_material_inputs_are_stable(tmp_path):
    module = _load_governed_project_control()
    graph_a = tmp_path / "a.json"
    graph_b = tmp_path / "b.json"
    graph_a.write_text('{"x":1}\n', encoding="utf-8")
    graph_b.write_text('{"x":1}\n', encoding="utf-8")
    first = module._normalised_inputs([
        "--repo-root", "/one",
        "--json", "schedule", "--project", "wfgg",
        "--graph", str(graph_a),
    ])
    second = module._normalised_inputs([
        "--repo-root", "/two",
        "--json", "schedule", "--project", "wfgg",
        "--graph", str(graph_b),
    ])
    assert first == second


def test_material_evidence_change_changes_inputs(tmp_path):
    module = _load_governed_project_control()
    graph = tmp_path / "graph.json"
    graph.write_text('{"x":1}\n', encoding="utf-8")
    before = module._normalised_inputs([
        "schedule", "--project", "wfgg", "--graph", str(graph),
    ])
    graph.write_text('{"x":2}\n', encoding="utf-8")
    after = module._normalised_inputs([
        "schedule", "--project", "wfgg", "--graph", str(graph),
    ])
    assert before != after


def test_non_execute_gate_never_invokes_downstream(monkeypatch, tmp_path):
    module = _load_governed_project_control()
    called = {"delegate": False}

    def forbidden_delegate(*args, **kwargs):
        called["delegate"] = True
        raise AssertionError("downstream must not be invoked")

    monkeypatch.setattr(module, "_delegate", forbidden_delegate)
    monkeypatch.setattr(module, "_preflight", lambda argv: ({
        "action": "RECOVERY_REQUIRED",
        "reason": "SAME_ACTION_INPUTS_STATE_WITHOUT_NEW_EVIDENCE_OR_STRATEGY",
        "project": "wfgg",
        "operation": "schedule",
        "resolution": {"status": "RESOLVED"},
        "run_key": "same-run",
        "recovery_plan": {
            "status": "READY",
            "coordinator": "logicien",
            "participants": ["logicien", "sentinelle"],
        },
    }, object()))
    monkeypatch.setattr(sys, "argv", [
        "governed-project-control.py",
        "--repo-root", str(tmp_path),
        "--json", "schedule", "--project", "wfgg",
    ])
    assert module.main() == 2
    assert called["delegate"] is False


def test_logicien_equivalent_cannot_recover_alone():
    previous = AttemptSnapshot(
        action="schedule",
        inputs={"graph": "same"},
        state={"revision": "same"},
        evidence={"proof": "same"},
        strategy={"gate": "canonical"},
        hypothesis_id="h1",
    )
    current = AttemptSnapshot(
        action="schedule",
        inputs={"graph": "same"},
        state={"revision": "same"},
        evidence={"proof": "same"},
        strategy={"gate": "canonical"},
        hypothesis_id="h1",
    )
    gate = GovernedRunGate(
        NonProgressDetector(),
        MultiAgentRecoveryRouter(_Catalogue([
            AgentCapability("logicien", frozenset({"causal-analysis"})),
        ])),
    )
    decision = gate.decide(
        previous=previous,
        current=current,
        incident_id="wfgg:schedule:same-run",
        required_capabilities=(),
    )
    assert decision.action == "BLOCKED"
    assert decision.recovery_plan is not None
    assert decision.recovery_plan.reason == "COORDINATOR_CANNOT_RECOVER_ALONE"
