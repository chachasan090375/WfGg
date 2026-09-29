from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class AgentCapability:
    agent_id: str
    capabilities: frozenset[str]
    enabled: bool = True
    healthy: bool = True


class CapabilityCatalogueProvider(Protocol):
    """Read-only adapter over the authoritative platform capability catalogue."""

    def agents(self) -> Sequence[AgentCapability]: ...


@dataclass(frozen=True)
class RecoveryRequest:
    incident_id: str
    hypothesis_id: str
    required_capabilities: tuple[str, ...]
    optional_capabilities: tuple[str, ...] = ()
    require_architecture_arbitration: bool = False
    evidence_delta: bool = False
    strategy_delta: bool = False


@dataclass(frozen=True)
class RecoveryPlan:
    status: str
    coordinator: str | None
    participants: tuple[str, ...]
    capability_assignments: Mapping[str, str]
    missing_capabilities: tuple[str, ...]
    reason: str


class MultiAgentRecoveryRouter:
    """Build a recovery cell from declared capabilities.

    The router knows capability names, not hard-coded agent identities. In
    particular, the causal-analysis coordinator is never accepted as a one-agent
    recovery cell: genuine recovery requires at least one distinct supporting
    participant.
    """

    COORDINATION_CAPABILITY = "causal-analysis"
    ARCHITECTURE_CAPABILITY = "architecture-arbitration"

    def __init__(self, catalogue: CapabilityCatalogueProvider) -> None:
        self._catalogue = catalogue

    def _eligible(self) -> list[AgentCapability]:
        return [a for a in self._catalogue.agents() if a.enabled and a.healthy]

    @staticmethod
    def _pick(agents: Iterable[AgentCapability], capability: str, *, exclude: frozenset[str] = frozenset()) -> AgentCapability | None:
        candidates = sorted(
            (a for a in agents if capability in a.capabilities and a.agent_id not in exclude),
            key=lambda a: a.agent_id,
        )
        return candidates[0] if candidates else None

    def route(self, request: RecoveryRequest) -> RecoveryPlan:
        agents = self._eligible()
        coordinator = self._pick(agents, self.COORDINATION_CAPABILITY)
        if coordinator is None:
            return RecoveryPlan(
                "BLOCKED_RECOVERY_CAPABILITY_GAP",
                None,
                (),
                {},
                (self.COORDINATION_CAPABILITY,),
                "NO_CAUSAL_ANALYSIS_COORDINATOR",
            )

        assignments: dict[str, str] = {self.COORDINATION_CAPABILITY: coordinator.agent_id}
        participants: set[str] = {coordinator.agent_id}
        missing: list[str] = []

        required = list(dict.fromkeys(request.required_capabilities))
        if request.require_architecture_arbitration and self.ARCHITECTURE_CAPABILITY not in required:
            required.append(self.ARCHITECTURE_CAPABILITY)

        for capability in required:
            if capability == self.COORDINATION_CAPABILITY:
                continue
            agent = self._pick(agents, capability)
            if agent is None:
                missing.append(capability)
                continue
            assignments[capability] = agent.agent_id
            participants.add(agent.agent_id)

        if missing:
            return RecoveryPlan(
                "BLOCKED_RECOVERY_CAPABILITY_GAP",
                coordinator.agent_id,
                tuple(sorted(participants)),
                assignments,
                tuple(sorted(missing)),
                "REQUIRED_SUPPORT_CAPABILITY_MISSING",
            )

        # Optional evidence providers are added when available; absence never
        # blocks recovery. This is where Technology Watch, isolated research,
        # UX, security, Foundries, etc. can participate based on incident needs.
        for capability in dict.fromkeys(request.optional_capabilities):
            agent = self._pick(agents, capability)
            if agent is not None:
                assignments[capability] = agent.agent_id
                participants.add(agent.agent_id)

        if len(participants) < 2:
            return RecoveryPlan(
                "BLOCKED_RECOVERY_CAPABILITY_GAP",
                coordinator.agent_id,
                tuple(sorted(participants)),
                assignments,
                (),
                "COORDINATOR_CANNOT_RECOVER_ALONE",
            )

        return RecoveryPlan(
            "READY",
            coordinator.agent_id,
            tuple(sorted(participants)),
            assignments,
            (),
            "CAPABILITY_DRIVEN_MULTI_AGENT_CELL_READY",
        )
