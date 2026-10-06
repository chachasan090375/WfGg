from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
WORKER=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
LATCH=(ROOT/"dev-hub/bin/guardian-stop-latch-reconciler.py").read_text(encoding="utf-8")


def test_applied_coverage_remediation_can_reopen_on_real_recurrence():
    assert "async function reactivateAppliedRemediation" in WORKER
    assert "SET status='OPEN',attempt_count=0,delivered_at=NULL,applied_at=NULL" in WORKER
    assert "await reactivateAppliedRemediation(env,directiveId);" in WORKER


def test_active_heartbeat_closes_orphan_coverage_alerts():
    assert "async function resolveOrphanCoverageAlerts" in WORKER
    assert "UPDATE guardian_alerts SET status='ACKED' WHERE alert_id=?1 AND status='OPEN'" in WORKER
    assert "resolvedAlerts=await resolveOrphanCoverageAlerts(env,activeIds);" in WORKER
    assert "resolved_alerts:resolvedAlerts" in WORKER


def test_local_latch_is_fail_closed_and_canonical_stop_is_forbidden():
    assert "GUARDIAN_STATE_UNAVAILABLE_FAIL_CLOSED" in LATCH
    assert "CANONICAL_EMERGENCY_STOP_MUTATION_FORBIDDEN" in LATCH
    assert '"canonical_emergency_stop_mutated": False' in LATCH


def test_reconciler_is_guardian_coverage_component():
    import json
    manifest=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text())
    row=next(x for x in manifest["expected_components"] if x["component_id"]=="guardian-critical-state-reconciler")
    assert row["criticality"]=="CRITICAL" and row["kind"]=="controller",row
    assert row["proof"]["file"]=="dev-hub/bin/guardian-stop-latch-reconciler.py",row
    assert row["proof"]["marker"] in LATCH,row


def test_platform_qualification_is_capability_path_scoped():
    workflow=(ROOT/".github/workflows/dev-hub-platform-qualification.yml").read_text(encoding="utf-8")
    assert "- 'dev-hub/**'" in workflow
    assert "- '.github/workflows/dev-hub-platform-qualification.yml'" in workflow
    assert "workflow_dispatch:" in workflow
    for legacy in (
        "roadmap-train-*",
        "roadmap-master-train-*",
        "roadmap-functional-*",
        "dev-hub-v*",
    ):
        assert legacy not in workflow


if __name__ == "__main__":
    tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith("test_") and callable(v)]
    for name,fn in tests: fn(); print(name+"=PASS")
    print("CHACHA_DEV_GUARDIAN_CRITICAL_STATE_RECONCILIATION=PASS")
    print("TEST_COUNT="+str(len(tests)))
