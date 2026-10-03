#!/usr/bin/env python3
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json"

def test_every_guardian_proof_is_materialized():
    data=json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows=data.get("expected_components") or []
    assert rows, "expected_components empty"
    missing=[]
    for row in rows:
        proof=row.get("proof") or {}
        checks=[{"file":proof.get("file"),"marker":proof.get("marker")}]
        checks.extend(x for x in (proof.get("checks") or []) if isinstance(x,dict))
        for check in checks:
            rel=check.get("file");marker=check.get("marker");path=ROOT/str(rel or "")
            if not rel or not marker or not path.is_file():
                missing.append((row.get("component_id"),rel,marker,"missing-file-or-proof"));continue
            text=path.read_text(encoding="utf-8",errors="ignore")
            if marker not in text:missing.append((row.get("component_id"),rel,marker,"marker-not-found"))
    assert not missing, missing

def test_central_interface_split_is_fully_covered():
    data=json.loads(MANIFEST.read_text(encoding="utf-8"))
    row=next(x for x in data["expected_components"] if x.get("component_id")=="central-interface-controller")
    proof=row["proof"]
    assert proof["file"]=="dev-hub/bin/central-interface-controller.py"
    checks={(x["file"],x["marker"]) for x in proof.get("checks") or []}
    assert ("dev-hub/bin/central-interface-controller-core.py",'RECEIPT_SCHEMA="chacha.dev/central-interface-receipt/v1"') in checks
    assert any(f=="dev-hub/bin/central-interface-controller.py" and "governed-project-control.py" in m for f,m in checks)


def test_registered_adapter_proof_matches_run_controller():
    data=json.loads(MANIFEST.read_text(encoding="utf-8"))
    row=next(x for x in data["expected_components"] if x.get("component_id")=="class:registered-adapters")
    assert row["proof"]["file"]=="dev-hub/bin/run-controller.py",row
    assert row["proof"]["marker"]=="ADAPTER_PERMISSION_UNSUPPORTED",row

if __name__=="__main__":
    tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith("test_") and callable(v)]
    for name,fn in tests:
        fn(); print(name+"=PASS")
    print("CHACHA_DEV_GUARDIAN_COVERAGE_PROOF_INTEGRITY=PASS")
    print("TEST_COUNT="+str(len(tests)))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
