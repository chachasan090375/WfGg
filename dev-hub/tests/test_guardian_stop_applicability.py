from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("applicability", ROOT / "lib" / "guardian_stop_applicability.py")
a = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(a)

ACTIVE = "prod"


def resolved(revision):
    return {"status": "EVIDENCE_RESOLVED", "revision": revision}


def test_active_revision_is_global_production_blocker():
    out = a.classify(resolved(ACTIVE), ACTIVE, set(), set())
    assert out["classification"] == a.PRODUCTION
    assert out["global_latch_eligible"] is True


def test_live_candidate_is_scoped_not_global():
    out = a.classify(resolved("candidate"), ACTIVE, {"candidate"}, set())
    assert out["classification"] == a.CANDIDATE
    assert out["global_latch_eligible"] is False


def test_stale_revision_is_not_global():
    out = a.classify(resolved("old"), ACTIVE, set(), {"old"})
    assert out["classification"] == a.STALE
    assert out["global_latch_eligible"] is False


def test_unknown_revision_fails_closed():
    out = a.classify(resolved("mystery"), ACTIVE, set(), set())
    assert out["classification"] == a.UNKNOWN
    assert out["global_latch_eligible"] is True


def test_unresolved_evidence_fails_closed():
    out = a.classify({"status": a.UNKNOWN, "reason": "NO_EVIDENCE"}, ACTIVE, set(), set())
    assert out["classification"] == a.UNKNOWN
    assert out["global_latch_eligible"] is True
