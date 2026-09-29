from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/candidate_runtime_pilot.py"


def module():
    spec = importlib.util.spec_from_file_location("candidate_runtime_pilot", TOOL)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_rewrite_ccr_snapshot_isolates_paths(tmp_path):
    m = module()
    candidate = tmp_path / "candidate"
    runtime = tmp_path / "pilot-runtime"
    snapshot = {
        "components": [
            {"component_id": "chacha-dev-platform", "paths": {
                "source_root": "/active/source",
                "runtime_root": "/active/runtime",
                "state_root": "/active/state",
            }}
        ]
    }
    out = m.rewrite_ccr_snapshot(snapshot, "chacha-dev-platform", candidate, runtime)
    row = out["components"][0]
    assert row["paths"]["source_root"] == str(candidate)
    assert row["paths"]["runtime_root"] == str(runtime)
    assert row["paths"]["state_root"] == str(runtime / "state/chacha-dev-platform")
    assert snapshot["components"][0]["paths"]["source_root"] == "/active/source"


def test_active_identity_detects_current_symlink_move(tmp_path):
    m = module()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / ".revision").write_text("aaa\n", encoding="utf-8")
    (b / ".revision").write_text("bbb\n", encoding="utf-8")
    current = tmp_path / "current"
    current.symlink_to(a)
    before = m.active_identity(current)
    current.unlink()
    current.symlink_to(b)
    try:
        m.assert_active_unchanged(current, before)
    except RuntimeError as exc:
        assert "ACTIVE_CHANGED_DURING_PILOT" in str(exc)
    else:
        raise AssertionError("symlink move must be detected")


def test_overlay_configs_keeps_every_pilot_write_root_isolated(tmp_path):
    m = module()
    candidate = tmp_path / "candidate"
    cfg = candidate / "dev-hub/config"
    active = tmp_path / "active-runtime"
    pilot = tmp_path / "pilot"
    project = "chacha-dev-platform"

    (active / "control").mkdir(parents=True)
    (active / "agent-evolution").mkdir(parents=True)
    (active / "control/emergency-stop.json").write_text('{"active":false}\n', encoding="utf-8")
    (active / "agent-evolution/fleet-observatory-latest.json").write_text('{"agents":[]}\n', encoding="utf-8")
    write(active / "canonical-registry/canonical-component-registry.json", {
        "components": [{"component_id": project, "paths": {
            "source_root": "/active/source",
            "runtime_root": str(active),
            "state_root": str(active / "state/chacha-dev-platform"),
        }}]
    })

    write(cfg / "canonical-component-registry.v1.json", {
        "schema": m.CCR_POLICY_SCHEMA,
        "runtime_registry": {
            "canonical_snapshot": str(active / "canonical-registry/canonical-component-registry.json")
        },
    })
    write(cfg / "project-control.v1.json", {
        "schema": m.PROJECT_CONTROL_POLICY_SCHEMA,
        "runtime": {},
    })
    write(cfg / "control-plane-state.v1.json", {
        "schema": "chacha.dev/control-plane-state-policy/v1",
        "storage": {"runtime_root": str(active / "state")},
    })
    write(cfg / "run-controller.v1.json", {
        "schema": m.RUN_CONTROLLER_POLICY_SCHEMA,
        "locking": {"root": str(active / "locks")},
        "dispatch": {"work_root": str(active / "runs")},
        "workspace": {"root": str(active / "projects")},
        "guardian": {"runtime_root": str(active)},
    })
    write(cfg / "direct-operator.v1.json", {
        "schema": m.DIRECT_OPERATOR_POLICY_SCHEMA,
        "bind": "127.0.0.1",
        "port": 8792,
        "runtime_root": str(active / "direct-operator"),
        "authentication": {"mode": "TAILSCALE_SERVE_IDENTITY"},
    })

    result = m.overlay_configs(candidate, pilot, project, 8793, active)
    pilot_runtime = pilot / "runtime"
    pc = m.load(cfg / "project-control.v1.json")
    rc = m.load(cfg / "run-controller.v1.json")
    direct = m.load(cfg / "direct-operator.v1.json")
    ccr = m.load(cfg / "canonical-component-registry.v1.json")

    for value in pc["runtime"].values():
        assert str(value).startswith(str(pilot_runtime))
    assert rc["locking"]["root"].startswith(str(pilot_runtime))
    assert rc["dispatch"]["work_root"].startswith(str(pilot_runtime))
    assert rc["workspace"]["root"].startswith(str(pilot_runtime))
    assert rc["guardian"]["runtime_root"] == str(active)
    assert direct["port"] == 8793
    assert direct["runtime_root"].startswith(str(pilot_runtime))
    assert ccr["runtime_registry"]["canonical_snapshot"] == result["ccr_snapshot"]
    assert (pilot_runtime / "control/emergency-stop.json").is_symlink()
    assert (pilot_runtime / "agent-evolution/fleet-observatory-latest.json").is_symlink()
