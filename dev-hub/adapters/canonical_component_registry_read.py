from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

POLICY_SCHEMA = "chacha.dev/canonical-component-registry-policy/v1"
INLINE_SCHEMA = "chacha.dev/canonical-component-registry/v1"


class JsonCanonicalComponentRegistry:
    """Read-only adapter over the unique Canonical Component Registry.

    The repository JSON is policy, not component truth. In production this
    adapter follows runtime_registry.canonical_snapshot and reads the runtime
    snapshot only. A direct inline registry is accepted only as an explicit
    test/fixture form.
    """

    def __init__(self, path: Path, snapshot_override: Path | None = None) -> None:
        self.path = Path(path)
        self.snapshot_override = Path(snapshot_override) if snapshot_override else None

    @staticmethod
    def _read(path: Path) -> Mapping[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"CCR_ROOT_NOT_OBJECT:{path}")
        return raw

    def _snapshot(self) -> Mapping[str, Any]:
        root = self._read(self.path)
        schema = root.get("schema")
        if schema == INLINE_SCHEMA:
            return root
        if schema != POLICY_SCHEMA:
            raise ValueError(f"CCR_POLICY_SCHEMA_INVALID:{schema}")

        runtime_registry = root.get("runtime_registry")
        if not isinstance(runtime_registry, dict):
            raise ValueError("CCR_RUNTIME_REGISTRY_POLICY_MISSING")
        configured = runtime_registry.get("canonical_snapshot")
        override = os.environ.get("CHACHA_CANONICAL_COMPONENT_SNAPSHOT")
        snapshot_path = self.snapshot_override or (Path(override) if override else None)
        if snapshot_path is None:
            if not isinstance(configured, str) or not configured.startswith("/"):
                raise ValueError("CCR_CANONICAL_SNAPSHOT_PATH_INVALID")
            snapshot_path = Path(configured)
        if not snapshot_path.is_file():
            raise FileNotFoundError(f"CCR_CANONICAL_SNAPSHOT_MISSING:{snapshot_path}")
        return self._read(snapshot_path)

    @staticmethod
    def _component_map(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        containers: list[Mapping[str, Any]] = [snapshot]
        nested = snapshot.get("registry")
        if isinstance(nested, dict):
            containers.append(nested)

        for container in containers:
            raw = container.get("components")
            if isinstance(raw, dict):
                return {
                    str(component_id): value
                    for component_id, value in raw.items()
                    if isinstance(value, dict)
                }
            if isinstance(raw, list):
                out: dict[str, Mapping[str, Any]] = {}
                for value in raw:
                    if not isinstance(value, dict):
                        continue
                    identity = value.get("identity") if isinstance(value.get("identity"), dict) else {}
                    component_id = str(
                        value.get("component_id")
                        or value.get("id")
                        or identity.get("component_id")
                        or identity.get("id")
                        or ""
                    ).strip()
                    if component_id:
                        out[component_id] = value
                if out:
                    return out
        raise ValueError("CCR_SNAPSHOT_COMPONENTS_INVALID")

    @staticmethod
    def _project_paths(component: Mapping[str, Any]) -> Mapping[str, Any]:
        paths = component.get("paths")
        if isinstance(paths, dict):
            return paths
        canonical_paths = component.get("canonical_paths")
        if isinstance(canonical_paths, dict):
            return canonical_paths
        return {}

    def get_component(self, component_id: str) -> Mapping[str, Any] | None:
        component = self._component_map(self._snapshot()).get(component_id)
        if component is None:
            return None
        if isinstance(component.get("paths"), dict):
            return component
        projected = dict(component)
        projected["paths"] = dict(self._project_paths(component))
        return projected

    def component_ids(self) -> Sequence[str]:
        return tuple(sorted(self._component_map(self._snapshot())))


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
