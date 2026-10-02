from pathlib import Path
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("resolver", ROOT / "lib" / "guardian_stop_evidence_resolver.py")
resolver = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(resolver)


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_functional_resolves_revision_from_canonical_alert(tmp_path: Path) -> None:
    aid = "functional-guardian-func-test"
    write(tmp_path / "alerts" / f"{aid}.json", {"alert_id": aid, "target_revision": "abc123", "component": "central-orchestrator", "contract_id": "functional-x"})
    out = resolver.resolve_evidence({"alert_id": aid}, tmp_path)
    assert out["status"] == "EVIDENCE_RESOLVED"
    assert out["revision"] == "abc123"
    assert out["scope"] == "central-orchestrator"


def test_missing_scope_is_unknown_and_fail_closed(tmp_path: Path) -> None:
    aid = "functional-guardian-func-empty"
    write(tmp_path / "alerts" / f"{aid}.json", {"alert_id": aid, "severity": "CRITICAL", "status": "OPEN"})
    out = resolver.resolve_evidence({"alert_id": aid}, tmp_path)
    assert out["status"] == resolver.UNKNOWN
    assert out["reason"] == "INSUFFICIENT_CANONICAL_EVIDENCE"


def test_unknown_alert_type_never_guesses_from_name(tmp_path: Path) -> None:
    out = resolver.resolve_evidence({"alert_id": "looks-like-prod-active-deadbeef"}, tmp_path)
    assert out["status"] == resolver.UNKNOWN
    assert out["revision"] is None


def test_coverage_can_use_canonical_coverage_snapshot(tmp_path: Path) -> None:
    write(tmp_path / "coverage-latest.json", {"revision": "prodsha", "scope": "platform"})
    out = resolver.resolve_evidence({"alert_id": "coverage-stale-x"}, tmp_path)
    assert out["status"] == "EVIDENCE_RESOLVED"
    assert out["revision"] == "prodsha"


def test_lease_without_canonical_metadata_stays_unknown(tmp_path: Path) -> None:
    write(tmp_path / "alerts" / "lease-expired-x.json", {"alert_id": "lease-expired-x"})
    out = resolver.resolve_evidence({"alert_id": "lease-expired-x"}, tmp_path)
    assert out["status"] == resolver.UNKNOWN
