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
    evidence_delta: bool
    strategy_delta: bool
    reason: str


class NonProgressDetector:
    """Prevent blind replay when nothing material changed.

    Retry counts are intentionally not the primary decision mechanism. A caller
    may impose an independent hard ceiling as a safety guard.
    """

    def compare(
        self,
        previous: AttemptSnapshot | None,
        current: AttemptSnapshot,
    ) -> NonProgressDecision:
        if previous is None:
            return NonProgressDecision(True, "FIRST_ATTEMPT", True, True, "NO_PREVIOUS_ATTEMPT")

        same_action = previous.action_fingerprint == current.action_fingerprint
        same_state = previous.state_fingerprint == current.state_fingerprint
        evidence_delta = previous.evidence_fingerprint != current.evidence_fingerprint
        strategy_delta = previous.strategy_fingerprint != current.strategy_fingerprint

        if same_action and same_state and not evidence_delta and not strategy_delta:
            return NonProgressDecision(
                False,
                "BLOCKED_NON_PROGRESS",
                False,
                False,
                "SAME_ACTION_INPUTS_STATE_WITHOUT_NEW_EVIDENCE_OR_STRATEGY",
            )

        if not evidence_delta and not strategy_delta:
            return NonProgressDecision(
                False,
                "RECOVERY_REQUIRED",
                False,
                False,
                "NO_EVIDENCE_DELTA_AND_NO_STRATEGY_DELTA",
            )

        return NonProgressDecision(
            True,
            "PROGRESS_POSSIBLE",
            evidence_delta,
            strategy_delta,
            "MATERIAL_DELTA_PRESENT",
        )
