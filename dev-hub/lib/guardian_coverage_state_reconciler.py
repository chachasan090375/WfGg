from __future__ import annotations
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict): raise ValueError("INVALID_COVERAGE_SNAPSHOT")
    return data


def reconcile(component_id: str, active_revision: str, coverage_path: Path) -> dict[str, Any]:
    snap=_load(coverage_path)
    if snap.get("platform_revision") != active_revision:
        return {"status":"UNKNOWN_APPLICABILITY","global_latch_eligible":True,"reason":"COVERAGE_SNAPSHOT_NOT_ACTIVE_REVISION"}
    rows=[x for x in snap.get("components",[]) if isinstance(x,dict) and x.get("component_id")==component_id]
    if not rows:
        return {"status":"PRODUCTION_APPLICABLE","global_latch_eligible":True,"reason":"COMPONENT_ABSENT_FROM_ACTIVE_COVERAGE","snapshot_id":snap.get("snapshot_id")}
    row=rows[0]
    if row.get("hook_active") is True:
        return {"status":"RESOLVED_PENDING_RESET","global_latch_eligible":False,"reason":"ACTIVE_COVERAGE_NOW_HEALTHY","snapshot_id":snap.get("snapshot_id"),"observed_at":snap.get("observed_at")}
    return {"status":"PRODUCTION_APPLICABLE","global_latch_eligible":True,"reason":"ACTIVE_COVERAGE_NOT_HEALTHY","snapshot_id":snap.get("snapshot_id")}
