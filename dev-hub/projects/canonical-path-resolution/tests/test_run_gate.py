from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from canonical_path_resolution.non_progress import AttemptSnapshot, NonProgressDetector
from canonical_path_resolution.recovery import AgentCapability, MultiAgentRecoveryRouter
from canonical_path_resolution.run_gate import GovernedRunGate


class Catalogue:
    def __init__(self, agents):
        self._agents = agents

    def agents(self):
        return self._agents


def snap(*, evidence, strategy):
    return AttemptSnapshot(
        action="resolve-path",
        inputs={"component": "x", "key": "state_root"},
        state={"status": "UNRESOLVED"},
        evidence=evidence,
        strategy=strategy,
        hypothesis_id="h1",
    )


def gate(agents):
    return GovernedRunGate(
        NonProgressDetector(),
        MultiAgentRecoveryRouter(Catalogue(agents)),
    )


def test_identical_replay_is_never_returned_as_execute():
    before = snap(evidence={"registry": "missing"}, strategy={"resolver": "canonical"})
    current = snap(evidence={"registry": "missing"}, strategy={"resolver": "canonical"})
    decision = gate([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
        AgentCapability("assurer", frozenset({"technical-assurance"})),
    ]).decide(
        previous=before,
        current=current,
        incident_id="i1",
        required_capabilities=("technical-assurance",),
    )
    assert decision.action == "RECOVERY_REQUIRED"
    assert decision.recovery_plan is not None
    assert decision.recovery_plan.status == "READY"


def test_logician_equivalent_coordinator_alone_blocks_recovery():
    before = snap(evidence={"registry": "missing"}, strategy={"resolver": "canonical"})
    current = snap(evidence={"registry": "missing"}, strategy={"resolver": "canonical"})
    decision = gate([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
    ]).decide(
        previous=before,
        current=current,
        incident_id="i1",
        required_capabilities=(),
    )
    assert decision.action == "BLOCKED"
    assert decision.recovery_plan is not None
    assert decision.recovery_plan.reason == "COORDINATOR_CANNOT_RECOVER_ALONE"


def test_material_new_evidence_allows_execution():
    before = snap(evidence={"registry": "missing"}, strategy={"resolver": "canonical"})
    current = snap(evidence={"registry": "/runtime/x"}, strategy={"resolver": "canonical"})
    decision = gate([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
        AgentCapability("assurer", frozenset({"technical-assurance"})),
    ]).decide(
        previous=before,
        current=current,
        incident_id="i1",
        required_capabilities=("technical-assurance",),
    )
    assert decision.action == "EXECUTE"


def test_optional_research_is_not_automatic_fallback():
    before = snap(evidence={"registry": "missing"}, strategy={"resolver": "canonical"})
    current = snap(evidence={"registry": "missing"}, strategy={"resolver": "canonical"})
    decision = gate([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
        AgentCapability("assurer", frozenset({"technical-assurance"})),
        AgentCapability("watch", frozenset({"technology-watch"})),
    ]).decide(
        previous=before,
        current=current,
        incident_id="i1",
        required_capabilities=("technical-assurance",),
        optional_capabilities=(),
    )
    assert decision.action == "RECOVERY_REQUIRED"
    assert "technology-watch" not in decision.recovery_plan.capability_assignments
