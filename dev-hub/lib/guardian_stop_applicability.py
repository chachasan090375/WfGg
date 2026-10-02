from __future__ import annotations

from typing import Any

PRODUCTION = "PRODUCTION_APPLICABLE"
CANDIDATE = "CANDIDATE_APPLICABLE"
STALE = "STALE_STOP_CANDIDATE"
UNKNOWN = "UNKNOWN_APPLICABILITY"


def classify(resolved: dict[str, Any], active_revision: str, live_candidate_revisions: set[str], stale_revisions: set[str]) -> dict[str, Any]:
    """Classify only from resolved canonical evidence; never infer identity."""
    if resolved.get("status") != "EVIDENCE_RESOLVED":
        return {"classification": UNKNOWN, "global_latch_eligible": True, "reason": resolved.get("reason", "EVIDENCE_NOT_RESOLVED")}
    revision = resolved.get("revision")
    if not revision:
        return {"classification": UNKNOWN, "global_latch_eligible": True, "reason": "REVISION_MISSING"}
    if revision == active_revision:
        return {"classification": PRODUCTION, "global_latch_eligible": True, "reason": "TARGETS_ACTIVE_PRODUCTION"}
    if revision in live_candidate_revisions:
        return {"classification": CANDIDATE, "global_latch_eligible": False, "reason": "TARGETS_LIVE_CANDIDATE"}
    if revision in stale_revisions:
        return {"classification": STALE, "global_latch_eligible": False, "reason": "TARGET_REVISION_SUPERSEDED_OR_ORPHANED"}
    return {"classification": UNKNOWN, "global_latch_eligible": True, "reason": "REVISION_LIFECYCLE_UNKNOWN"}
