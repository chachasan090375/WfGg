from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class RecoveryLedgerEntry:
    incident_id: str
    hypothesis_id: str
    action: str
    evidence_delta: bool
    strategy_delta: bool
    outcome: str
    evidence_refs: tuple[str, ...] = ()
    strategy_ref: str | None = None
    created_at: str = ""

    def with_timestamp(self) -> "RecoveryLedgerEntry":
        if self.created_at:
            return self
        return RecoveryLedgerEntry(
            incident_id=self.incident_id,
            hypothesis_id=self.hypothesis_id,
            action=self.action,
            evidence_delta=self.evidence_delta,
            strategy_delta=self.strategy_delta,
            outcome=self.outcome,
            evidence_refs=self.evidence_refs,
            strategy_ref=self.strategy_ref,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def as_record(self) -> Mapping[str, Any]:
        return asdict(self.with_timestamp())

    @property
    def is_zero_progress(self) -> bool:
        return not self.evidence_delta and not self.strategy_delta
