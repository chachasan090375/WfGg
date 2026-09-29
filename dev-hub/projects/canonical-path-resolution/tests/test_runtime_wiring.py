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
from canonical_path_resolution.resolver import CanonicalPathResolver


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
