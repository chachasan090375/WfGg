from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from canonical_path_resolution.non_progress import AttemptSnapshot, NonProgressDetector


def test_state_change_is_material_progress():
    previous = AttemptSnapshot(
        action="inspect",
        inputs={"component": "x"},
        state={"status": "QUEUED"},
        evidence={"job": "j1"},
        strategy={"mode": "canonical"},
        hypothesis_id="h1",
    )
    current = AttemptSnapshot(
        action="inspect",
        inputs={"component": "x"},
        state={"status": "RUNNING"},
        evidence={"job": "j1"},
        strategy={"mode": "canonical"},
        hypothesis_id="h1",
    )
    decision = NonProgressDetector().compare(previous, current)
    assert decision.allow_execution is True
    assert decision.state_delta is True
    assert decision.evidence_delta is False
    assert decision.strategy_delta is False
