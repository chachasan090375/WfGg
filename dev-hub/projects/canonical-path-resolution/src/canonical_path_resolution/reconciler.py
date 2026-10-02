from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .resolver import CanonicalPathResolver, Resolution, ResolutionStatus


class FleetClassification(str, Enum):
    COMPLIANT = "COMPLIANT"
    UPDATABLE = "UPDATABLE"
    SUPERSEDED = "SUPERSEDED"
    ORPHAN = "ORPHAN"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True)
class DriftResult:
    component_id: str
    resolutions: tuple[Resolution, ...]
    classification: FleetClassification
    blocking: bool


class PathDriftReconciler:
    """Read-only reconciliation. It proposes/classifies; it never mutates paths."""

    def __init__(self, resolver: CanonicalPathResolver) -> None:
        self._resolver = resolver

    def inspect(self, component_id: str, keys: Iterable[str]) -> DriftResult:
        resolutions = tuple(self._resolver.resolve(component_id, key, verify=True) for key in keys)
        statuses = {r.status for r in resolutions}

        if ResolutionStatus.AMBIGUOUS in statuses:
            classification = FleetClassification.INCOMPATIBLE
            blocking = True
        elif ResolutionStatus.DRIFT in statuses:
            classification = FleetClassification.UPDATABLE
            blocking = True
        elif ResolutionStatus.UNRESOLVED in statuses:
            # Absence of canonical identity/location is treated as ORPHAN until
            # governed recovery proves it belongs elsewhere or is incompatible.
            classification = FleetClassification.ORPHAN
            blocking = True
        elif ResolutionStatus.BLOCKED_POLICY in statuses:
            classification = FleetClassification.INCOMPATIBLE
            blocking = True
        else:
            classification = FleetClassification.COMPLIANT
            blocking = False

        return DriftResult(component_id, resolutions, classification, blocking)
