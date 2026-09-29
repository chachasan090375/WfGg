from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping, Protocol


CANONICAL_PATH_KEYS = frozenset(
    {
        "source_root",
        "release_root",
        "current_link",
        "runtime_root",
        "state_root",
        "evidence_root",
        "persistent_root",
        "writable_roots",
        "systemd_unit",
        "endpoints",
        "ports",
    }
)


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    RESOLVED_UNVERIFIED = "RESOLVED_UNVERIFIED"
    DRIFT = "DRIFT"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    BLOCKED_POLICY = "BLOCKED_POLICY"


class ComponentRegistryProvider(Protocol):
    """Read-only adapter over the authoritative Canonical Component Registry."""

    def get_component(self, component_id: str) -> Mapping[str, Any] | None: ...


class RuntimePathObserver(Protocol):
    """Optional read-only runtime verifier. It owns no canonical truth."""

    def observe(self, component_id: str, key: str) -> Any | None: ...


@dataclass(frozen=True)
class Resolution:
    component_id: str
    key: str
    status: ResolutionStatus
    declared: Any = None
    observed: Any = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {
            ResolutionStatus.RESOLVED,
            ResolutionStatus.RESOLVED_UNVERIFIED,
        }


def _normalise(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("/"):
        return str(PurePosixPath(value))
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_normalise(v) for v in value)
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    return value


class CanonicalPathResolver:
    """Resolve semantic locations without repository-wide rediscovery.

    The resolver never persists component data. The registry provider remains
    the only authority. Runtime observation can verify or contradict a declared
    value, but can never silently promote an observed value to canonical truth.
    """

    def __init__(
        self,
        registry: ComponentRegistryProvider,
        observer: RuntimePathObserver | None = None,
        *,
        blocked_keys: frozenset[str] = frozenset(),
    ) -> None:
        self._registry = registry
        self._observer = observer
        self._blocked_keys = blocked_keys

    def resolve(self, component_id: str, key: str, *, verify: bool = True) -> Resolution:
        if key not in CANONICAL_PATH_KEYS:
            return Resolution(
                component_id,
                key,
                ResolutionStatus.UNRESOLVED,
                reason="UNKNOWN_CANONICAL_PATH_KEY",
            )
        if key in self._blocked_keys:
            return Resolution(
                component_id,
                key,
                ResolutionStatus.BLOCKED_POLICY,
                reason="RUNTIME_VERIFICATION_BLOCKED_BY_POLICY",
            )

        component = self._registry.get_component(component_id)
        if not component:
            return Resolution(
                component_id,
                key,
                ResolutionStatus.UNRESOLVED,
                reason="COMPONENT_NOT_IN_CANONICAL_REGISTRY",
            )

        paths = component.get("paths") or {}
        candidates = paths.get(key)
        if candidates is None or candidates == "" or candidates == []:
            return Resolution(
                component_id,
                key,
                ResolutionStatus.UNRESOLVED,
                reason="CANONICAL_PATH_UNRESOLVED",
            )

        # A registry may expose explicit candidate sets while migration data is
        # being reconciled. Never choose one silently.
        if isinstance(candidates, Mapping) and "candidates" in candidates:
            values = [_normalise(v) for v in candidates.get("candidates", []) if v not in (None, "")]
            unique = []
            for value in values:
                if value not in unique:
                    unique.append(value)
            if len(unique) != 1:
                return Resolution(
                    component_id,
                    key,
                    ResolutionStatus.AMBIGUOUS,
                    declared=unique,
                    reason="CANONICAL_PATH_AMBIGUOUS",
                )
            declared = unique[0]
        else:
            declared = _normalise(candidates)

        if not verify or self._observer is None:
            return Resolution(
                component_id,
                key,
                ResolutionStatus.RESOLVED_UNVERIFIED,
                declared=declared,
                reason="RUNTIME_NOT_VERIFIED",
            )

        observed = self._observer.observe(component_id, key)
        if observed is None:
            return Resolution(
                component_id,
                key,
                ResolutionStatus.RESOLVED_UNVERIFIED,
                declared=declared,
                reason="NO_RUNTIME_OBSERVATION",
            )

        observed = _normalise(observed)
        if observed != declared:
            return Resolution(
                component_id,
                key,
                ResolutionStatus.DRIFT,
                declared=declared,
                observed=observed,
                reason="PATH_DRIFT",
            )

        return Resolution(
            component_id,
            key,
            ResolutionStatus.RESOLVED,
            declared=declared,
            observed=observed,
        )
