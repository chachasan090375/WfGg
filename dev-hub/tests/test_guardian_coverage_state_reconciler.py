from pathlib import Path
import importlib.util,json,tempfile
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location("m",ROOT/"lib"/"guardian_coverage_state_reconciler.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)

def run(data,component="x",active="prod"):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"coverage.json"; p.write_text(json.dumps(data)); return m.reconcile(component,active,p)

def test_healthy_current_component_is_resolved_pending_reset():
    o=run({"platform_revision":"prod","snapshot_id":"s","components":[{"component_id":"x","hook_active":True}]}); assert o["status"]=="RESOLVED_PENDING_RESET" and not o["global_latch_eligible"]

def test_missing_current_component_remains_production_blocker():
    o=run({"platform_revision":"prod","components":[]}); assert o["status"]=="PRODUCTION_APPLICABLE" and o["global_latch_eligible"]

def test_unhealthy_current_component_remains_production_blocker():
    o=run({"platform_revision":"prod","components":[{"component_id":"x","hook_active":False}]}); assert o["status"]=="PRODUCTION_APPLICABLE"

def test_snapshot_for_other_revision_fails_closed():
    o=run({"platform_revision":"other","components":[{"component_id":"x","hook_active":True}]}); assert o["status"]=="UNKNOWN_APPLICABILITY" and o["global_latch_eligible"]
