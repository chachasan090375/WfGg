from __future__ import annotations

import json
from pathlib import Path
from typing import Any

UNKNOWN = "UNKNOWN_APPLICABILITY"


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def resolve_evidence(alert: dict[str, Any], guardian_root: Path) -> dict[str, Any]:
    """Resolve scope evidence without guessing from an alert id."""
    alert_id = str(alert.get("alert_id") or "")
    candidates: list[Path] = []
    if alert_id.startswith("functional-"):
        candidates += [guardian_root / "alerts" / f"{alert_id}.json"]
        candidates += list((guardian_root / "functional-acceptance").glob(f"*{alert_id}*.json")) if (guardian_root / "functional-acceptance").exists() else []
    elif alert_id.startswith("lease-expired-"):
        candidates += [guardian_root / "alerts" / f"{alert_id}.json"]
        candidates += list((guardian_root / "leases").glob("*.json")) if (guardian_root / "leases").exists() else []
    elif alert_id.startswith("coverage-"):
        candidates += [guardian_root / "alerts" / f"{alert_id}.json"]
        candidates += [guardian_root / "coverage-latest.json"]
    else:
        candidates += [guardian_root / "alerts" / f"{alert_id}.json"]

    seen: list[str] = []
    for path in candidates:
        data = _load(path)
        if not data:
            continue
        seen.append(str(path))
        revision = _first(data, "target_revision", "revision", "sha", "head_sha")
        scope = _first(data, "scope", "project", "component", "target_component")
        contract = _first(data, "contract_id", "functional_contract_id", "lease_id")
        if revision or scope or contract:
            return {"status": "EVIDENCE_RESOLVED", "revision": revision, "scope": scope, "contract_id": contract, "evidence": seen}

    return {"status": UNKNOWN, "revision": None, "scope": None, "contract_id": None, "evidence": seen, "reason": "INSUFFICIENT_CANONICAL_EVIDENCE"}
