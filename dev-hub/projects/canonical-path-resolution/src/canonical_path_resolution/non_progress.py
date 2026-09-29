from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AttemptSnapshot:
    action: str
    inputs: Mapping[str, Any]
    state: Mapping[str, Any]
    evidence: Mapping[str, Any]
    strategy: Mapping[str, Any]
    hypothesis_id: str

    @property
    def action_fingerprint(self) -> str:
        return _digest({"action": self.action, "inputs": self.inputs})

    @property
    def state_fingerprint(self) -> str:
        return _digest(self.state)

    @property
    def evidence_fingerprint(self) -> str:
        return _digest(self.evidence)

    @property
    def strategy_fingerprint(self) -> str:
        return _digest(self.strategy)


@dataclass(frozen=True)
class NonProgressDecision:
    allow_execution: bool
    status: str
    state_delta: bool
    evidence_delta: bool
    strategy_delta: bool
    reason: str


class NonProgressDetector:
    """Prevent blind replay when nothing material changed.

    Progress is evidence-driven: state, evidence or strategy must materially
    change. Retry counts are intentionally not the primary decision mechanism;
    callers may still impose an independent hard ceiling as a safety guard.
    """

    def compare(
        self,
        previous: AttemptSnapshot | None,
        current: AttemptSnapshot,
    ) -> NonProgressDecision:
        if previous is None:
            return NonProgressDecision(
                True,
                "FIRST_ATTEMPT",
                True,
                True,
                True,
                "NO_PREVIOUS_ATTEMPT",
            )

        same_action = previous.action_fingerprint == current.action_fingerprint
        state_delta = previous.state_fingerprint != current.state_fingerprint
        evidence_delta = previous.evidence_fingerprint != current.evidence_fingerprint
        strategy_delta = previous.strategy_fingerprint != current.strategy_fingerprint

        if same_action and not state_delta and not evidence_delta and not strategy_delta:
            return NonProgressDecision(
                False,
                "BLOCKED_NON_PROGRESS",
                False,
                False,
                False,
                "SAME_ACTION_INPUTS_STATE_WITHOUT_NEW_EVIDENCE_OR_STRATEGY",
            )

        if not state_delta and not evidence_delta and not strategy_delta:
            return NonProgressDecision(
                False,
                "RECOVERY_REQUIRED",
                False,
                False,
                False,
                "NO_STATE_EVIDENCE_OR_STRATEGY_DELTA",
            )

        return NonProgressDecision(
            True,
            "PROGRESS_POSSIBLE",
            state_delta,
            evidence_delta,
            strategy_delta,
            "MATERIAL_DELTA_PRESENT",
        )
