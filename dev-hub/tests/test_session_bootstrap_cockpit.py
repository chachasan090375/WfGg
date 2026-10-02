from pathlib import Path
import importlib.util,json,tempfile
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location("m",ROOT/"lib"/"session_bootstrap_cockpit.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_bootstrap_recovers_active_without_chat_history():
  with tempfile.TemporaryDirectory() as d:
    root=Path(d);runtime=root/"runtime";current=root/"current";runtime.mkdir();current.mkdir()
    (current/".revision").write_text("abc123\n")
    (runtime/"guardian").mkdir();(runtime/"guardian"/"coverage-latest.json").write_text(json.dumps({"snapshot_id":"s1","platform_revision":"abc123"}))
    out=m.build(runtime,current)
    assert out["active_production"]["revision"]=="abc123"
    assert out["chat_history_required"] is False and out["read_only"] is True
    assert out["guardian"]["coverage_snapshot"]["snapshot_id"]=="s1"

def test_missing_active_fails_degraded_not_invented():
  with tempfile.TemporaryDirectory() as d:
    root=Path(d);runtime=root/"runtime";current=root/"current";runtime.mkdir();current.mkdir()
    out=m.build(runtime,current)
    assert out["status"]=="DEGRADED" and out["active_production"]["revision"] is None
