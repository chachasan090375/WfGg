from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class JsonCanonicalComponentRegistry:
    """Read-only adapter over the unique Canonical Component Registry."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _document(self) -> Mapping[str, Any]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("CCR_ROOT_NOT_OBJECT")
        if raw.get("schema") != "chacha.dev/canonical-component-registry/v1":
            raise ValueError("CCR_SCHEMA_INVALID")
        components = raw.get("components")
        if not isinstance(components, dict):
            raise ValueError("CCR_COMPONENTS_INVALID")
        return raw

    def get_component(self, component_id: str) -> Mapping[str, Any] | None:
        component = (self._document().get("components") or {}).get(component_id)
        return component if isinstance(component, dict) else None


class FilesystemRuntimePathObserver:
    """Verify declared local paths without ever promoting observations to truth."""

    def __init__(self, registry: JsonCanonicalComponentRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _single_declared(value: Any) -> Any:
        if isinstance(value, dict) and "candidates" in value:
            values = [v for v in value.get("candidates") or [] if v not in (None, "")]
            unique: list[Any] = []
            for value_item in values:
                if value_item not in unique:
                    unique.append(value_item)
            return unique[0] if len(unique) == 1 else None
        return value

    @staticmethod
    def _path_exists(value: str) -> bool:
        path = Path(value)
        return path.exists() or path.is_symlink()

    def observe(self, component_id: str, key: str) -> Any | None:
        component = self.registry.get_component(component_id)
        if not component:
            return None
        paths = component.get("paths") or {}
        if not isinstance(paths, dict):
            return None
        declared = self._single_declared(paths.get(key))
        if isinstance(declared, str) and declared.startswith("/"):
            return declared if self._path_exists(declared) else None
        if isinstance(declared, list) and all(isinstance(x, str) and x.startswith("/") for x in declared):
            return declared if all(self._path_exists(x) for x in declared) else None
        return None


class FleetObservatoryCatalogue:
    """Capability catalogue projected from the existing Fleet Observatory snapshot."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _capability_values(row: Mapping[str, Any]) -> frozenset[str]:
        values: set[str] = set()
        candidates: list[Any] = [
            row.get("capabilities"),
            row.get("declared_capabilities"),
            row.get("effective_capabilities"),
        ]
        scorecard = row.get("scorecard")
        if isinstance(scorecard, dict):
            candidates.append(scorecard.get("capabilities"))
        for candidate in candidates:
            if isinstance(candidate, dict):
                values.update(str(k) for k, enabled in candidate.items() if enabled)
            elif isinstance(candidate, (list, tuple, set)):
                values.update(str(v) for v in candidate if str(v).strip())
        return frozenset(values)

    def agents(self) -> Sequence[Any]:
        from canonical_path_resolution.recovery import AgentCapability

        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows = payload.get("agents") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []

        agents: list[AgentCapability] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            agent_id = str(row.get("agent_id") or row.get("id") or row.get("name") or "").strip()
            if not agent_id:
                continue
            status = str(row.get("status") or "").upper()
            health = str(row.get("health") or "").upper()
            enabled = row.get("enabled", True) is not False and status not in {"DISABLED", "RETIRED", "PURGED"}
            healthy = (
                row.get("healthy", True) is not False
                and status not in {"FAILED", "BLOCKED", "DOWN"}
                and health not in {"FAILED", "BLOCKED", "DOWN", "UNHEALTHY"}
            )
            agents.append(
                AgentCapability(
                    agent_id=agent_id,
                    capabilities=self._capability_values(row),
                    enabled=enabled,
                    healthy=healthy,
                )
            )
        return tuple(agents)
