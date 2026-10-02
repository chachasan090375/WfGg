from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence

from .reconciler import DriftResult, FleetClassification, PathDriftReconciler


class CanonicalFleetProvider(Protocol):
    """Read-only enumeration from the same Canonical Component Registry."""

    def component_ids(self) -> Sequence[str]: ...


@dataclass(frozen=True)
class FleetAuditReport:
    results: tuple[DriftResult, ...]
    counts: Mapping[str, int]
    blocking_components: tuple[str, ...]


class CanonicalFleetPathAudit:
    def __init__(self, fleet: CanonicalFleetProvider, reconciler: PathDriftReconciler) -> None:
        self._fleet = fleet
        self._reconciler = reconciler

    def run(self, keys: Iterable[str]) -> FleetAuditReport:
        key_tuple = tuple(keys)
        results = tuple(
            self._reconciler.inspect(component_id, key_tuple)
            for component_id in sorted(set(self._fleet.component_ids()))
        )
        counts = {classification.value: 0 for classification in FleetClassification}
        for result in results:
            counts[result.classification.value] += 1
        blocking = tuple(result.component_id for result in results if result.blocking)
        return FleetAuditReport(results, counts, blocking)
