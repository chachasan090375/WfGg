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


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    event = data.get("event")
    return event if isinstance(event, dict) else data


def resolve_evidence(alert: dict[str, Any], guardian_root: Path) -> dict[str, Any]:
    """Resolve canonical provenance without guessing from alert names."""
    alert_id = str(alert.get("alert_id") or "")
    path = guardian_root / "alerts" / f"{alert_id}.json"
    data = _load(path) or alert
    event = _payload(data)
    evidence = [str(path)] if path.is_file() else []

    if alert_id.startswith("functional-"):
        revision = _first(event, "target_revision", "revision", "sha", "head_sha")
        scope = _first(event, "project_id", "scope", "component", "subject_role")
        contract = _first(event, "contract_id", "functional_contract_id", "receipt_id")
        if revision and scope and contract:
            return {"status":"EVIDENCE_RESOLVED","kind":"FUNCTIONAL","revision":revision,"scope":scope,"contract_id":contract,"evidence":evidence}

    elif alert_id.startswith("coverage-"):
        component = _first(event, "component_id", "component", "target_component")
        snapshot = _first(event, "snapshot_id")
        if component:
            return {"status":"EVIDENCE_RESOLVED","kind":"COVERAGE","revision":None,"scope":component,"contract_id":snapshot,"evidence":evidence,"runtime_scoped":True}

    elif alert_id.startswith("lease-expired-"):
        scope = _first(event, "project_id", "scope")
        contract = _first(event, "action_id", "run_id", "pre_event_id")
        if scope and contract:
            return {"status":"EVIDENCE_RESOLVED","kind":"LEASE","revision":None,"scope":scope,"contract_id":contract,"run_id":_first(event,"run_id"),"action_id":_first(event,"action_id"),"pre_event_id":_first(event,"pre_event_id"),"post_event_id":_first(event,"post_event_id"),"evidence":evidence,"lifecycle_resolution_required":True}

    return {"status":UNKNOWN,"kind":None,"revision":None,"scope":None,"contract_id":None,"evidence":evidence,"reason":"INSUFFICIENT_CANONICAL_EVIDENCE"}
