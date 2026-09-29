from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from canonical_path_resolution.non_progress import AttemptSnapshot, NonProgressDetector
from canonical_path_resolution.reconciler import FleetClassification, PathDriftReconciler
from canonical_path_resolution.recovery import AgentCapability, MultiAgentRecoveryRouter, RecoveryRequest
from canonical_path_resolution.resolver import CanonicalPathResolver, ResolutionStatus


class Registry:
    def __init__(self, components):
        self.components = components

    def get_component(self, component_id):
        return self.components.get(component_id)


class Observer:
    def __init__(self, observed):
        self.observed = observed

    def observe(self, component_id, key):
        return self.observed.get((component_id, key))


class Catalogue:
    def __init__(self, agents):
        self._agents = agents

    def agents(self):
        return self._agents


def snap(*, evidence, strategy, state=None, action="inspect", inputs=None, hypothesis="h1"):
    return AttemptSnapshot(
        action=action,
        inputs=inputs or {"component": "x"},
        state=state or {"status": "blocked"},
        evidence=evidence,
        strategy=strategy,
        hypothesis_id=hypothesis,
    )


def test_resolver_uses_registry_without_owning_registry_data():
    registry = Registry({"direct-operator": {"paths": {"state_root": "/opt/chacha-dev/runtime/direct-operator"}}})
    observer = Observer({("direct-operator", "state_root"): "/opt/chacha-dev/runtime/direct-operator"})
    result = CanonicalPathResolver(registry, observer).resolve("direct-operator", "state_root")
    assert result.status is ResolutionStatus.RESOLVED
    assert result.declared == result.observed


def test_unknown_required_path_stops_as_unresolved():
    registry = Registry({"x": {"paths": {}}})
    result = CanonicalPathResolver(registry).resolve("x", "state_root")
    assert result.status is ResolutionStatus.UNRESOLVED
    assert result.reason == "CANONICAL_PATH_UNRESOLVED"


def test_ambiguous_candidates_are_never_silently_chosen():
    registry = Registry({"x": {"paths": {"runtime_root": {"candidates": ["/a", "/b"]}}}})
    result = CanonicalPathResolver(registry).resolve("x", "runtime_root")
    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.declared == ["/a", "/b"]


def test_runtime_disagreement_is_drift_not_new_canonical_truth():
    registry = Registry({"x": {"paths": {"runtime_root": "/canonical"}}})
    observer = Observer({("x", "runtime_root"): "/observed"})
    result = CanonicalPathResolver(registry, observer).resolve("x", "runtime_root")
    assert result.status is ResolutionStatus.DRIFT
    assert result.declared == "/canonical"
    assert result.observed == "/observed"


def test_reconciler_classifies_drift_as_updatable_and_blocking():
    registry = Registry({"x": {"paths": {"runtime_root": "/canonical"}}})
    observer = Observer({("x", "runtime_root"): "/observed"})
    result = PathDriftReconciler(CanonicalPathResolver(registry, observer)).inspect("x", ["runtime_root"])
    assert result.classification is FleetClassification.UPDATABLE
    assert result.blocking is True


def test_identical_action_state_evidence_and_strategy_is_blocked():
    detector = NonProgressDetector()
    before = snap(evidence={"e": 1}, strategy={"s": 1})
    after = snap(evidence={"e": 1}, strategy={"s": 1})
    decision = detector.compare(before, after)
    assert decision.allow_execution is False
    assert decision.status == "BLOCKED_NON_PROGRESS"


def test_new_evidence_allows_reconsideration_without_retry_count_logic():
    detector = NonProgressDetector()
    before = snap(evidence={"e": 1}, strategy={"s": 1})
    after = snap(evidence={"e": 2}, strategy={"s": 1})
    decision = detector.compare(before, after)
    assert decision.allow_execution is True
    assert decision.evidence_delta is True
    assert decision.strategy_delta is False


def test_new_strategy_allows_reconsideration_without_fake_progress():
    detector = NonProgressDetector()
    before = snap(evidence={"e": 1}, strategy={"s": 1})
    after = snap(evidence={"e": 1}, strategy={"s": 2})
    decision = detector.compare(before, after)
    assert decision.allow_execution is True
    assert decision.evidence_delta is False
    assert decision.strategy_delta is True


def test_causal_coordinator_is_blocked_when_alone():
    catalogue = Catalogue([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
    ])
    plan = MultiAgentRecoveryRouter(catalogue).route(
        RecoveryRequest("i1", "h1", required_capabilities=())
    )
    assert plan.status == "BLOCKED_RECOVERY_CAPABILITY_GAP"
    assert plan.reason == "COORDINATOR_CANNOT_RECOVER_ALONE"


def test_recovery_cell_is_capability_driven_and_multi_agent():
    catalogue = Catalogue([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
        AgentCapability("technical-agent", frozenset({"technical-assurance"})),
        AgentCapability("research-agent", frozenset({"technology-watch"})),
        AgentCapability("isolated-research-agent", frozenset({"specialized-isolated-research"})),
    ])
    plan = MultiAgentRecoveryRouter(catalogue).route(
        RecoveryRequest(
            "i1",
            "h1",
            required_capabilities=("technical-assurance",),
            optional_capabilities=("technology-watch", "specialized-isolated-research"),
        )
    )
    assert plan.status == "READY"
    assert set(plan.participants) == {
        "reasoner",
        "technical-agent",
        "research-agent",
        "isolated-research-agent",
    }
    assert plan.capability_assignments["causal-analysis"] == "reasoner"
    assert plan.capability_assignments["technology-watch"] == "research-agent"


def test_missing_required_support_capability_blocks_instead_of_falling_back_to_search():
    catalogue = Catalogue([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
        AgentCapability("research-agent", frozenset({"technology-watch"})),
    ])
    plan = MultiAgentRecoveryRouter(catalogue).route(
        RecoveryRequest("i1", "h1", required_capabilities=("security-review",))
    )
    assert plan.status == "BLOCKED_RECOVERY_CAPABILITY_GAP"
    assert "security-review" in plan.missing_capabilities
    assert "technology-watch" not in plan.capability_assignments


def test_architecture_arbitration_is_required_only_when_requested():
    catalogue = Catalogue([
        AgentCapability("reasoner", frozenset({"causal-analysis"})),
        AgentCapability("technical-agent", frozenset({"technical-assurance"})),
        AgentCapability("council", frozenset({"architecture-arbitration"})),
    ])
    plan = MultiAgentRecoveryRouter(catalogue).route(
        RecoveryRequest(
            "i1",
            "h1",
            required_capabilities=("technical-assurance",),
            require_architecture_arbitration=True,
        )
    )
    assert plan.status == "READY"
    assert plan.capability_assignments["architecture-arbitration"] == "council"
