from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .non_progress import AttemptSnapshot, NonProgressDetector
from .recovery import MultiAgentRecoveryRouter, RecoveryPlan, RecoveryRequest


@dataclass(frozen=True)
class RunGateDecision:
    action: str
    reason: str
    recovery_plan: RecoveryPlan | None = None


class GovernedRunGate:
    """Boundary intended for Scheduler/Run Controller integration.

    This class does not execute, retry, search or mutate. It decides whether an
    intended execution may proceed, must enter multi-agent recovery, or must
    remain blocked because no materially different strategy/evidence exists.
    """

    def __init__(
        self,
        detector: NonProgressDetector,
        recovery_router: MultiAgentRecoveryRouter,
    ) -> None:
        self._detector = detector
        self._recovery_router = recovery_router

    def decide(
        self,
        *,
        previous: AttemptSnapshot | None,
        current: AttemptSnapshot,
        incident_id: str,
        required_capabilities: tuple[str, ...],
        optional_capabilities: tuple[str, ...] = (),
        require_architecture_arbitration: bool = False,
    ) -> RunGateDecision:
        progress = self._detector.compare(previous, current)
        if progress.allow_execution:
            return RunGateDecision("EXECUTE", progress.reason)

        request = RecoveryRequest(
            incident_id=incident_id,
            hypothesis_id=current.hypothesis_id,
            required_capabilities=required_capabilities,
            optional_capabilities=optional_capabilities,
            require_architecture_arbitration=require_architecture_arbitration,
            evidence_delta=progress.evidence_delta,
            strategy_delta=progress.strategy_delta,
        )
        plan = self._recovery_router.route(request)

        if plan.status != "READY":
            return RunGateDecision(
                "BLOCKED",
                plan.reason,
                recovery_plan=plan,
            )

        return RunGateDecision(
            "RECOVERY_REQUIRED",
            progress.reason,
            recovery_plan=plan,
        )
