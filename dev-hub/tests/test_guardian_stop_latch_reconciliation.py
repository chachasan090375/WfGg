from __future__ import annotations
import importlib.util, json, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "dev-hub/bin/guardian-stop-latch-reconciler.py"
spec = importlib.util.spec_from_file_location("guardian_stop_latch_reconciler", MOD_PATH)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

FAKE_CLIENT = '''import json,sys
args=sys.argv
policy=args[args.index("--policy")+1]
kind="alerts" if "alerts" in args else "remediations"
status=args[args.index("--status")+1]
p=json.load(open(policy)); s=json.load(open(p["fake_scenario"]))
v=s.get(kind+":"+status,[])
if v=="__FAIL__": raise SystemExit(7)
print(json.dumps({"items":v}))
'''


def save(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def fixture(td: Path, scenario: dict, latch: dict | None):
    latch_path=td/"guardian-stop-required.json"; scenario_path=td/"scenario.json"
    policy=td/"policy.json"; config=td/"config.json"; client=td/"fake-client.py"
    save(scenario_path,scenario); client.write_text(FAKE_CLIENT,encoding="utf-8")
    save(policy,{"critical_stop_required_file":str(latch_path),"fake_scenario":str(scenario_path)})
    save(config,{"confirmation_delay_seconds":0,"managed_active_reasons":[
        "EXTERNAL_GUARDIAN_CRITICAL_ALERT","GUARDIAN_CORRECTIVE_DIRECTIVE_CRITICAL",
        "GUARDIAN_CRITICAL_SOURCE_CONFIRMED","GUARDIAN_STATE_UNAVAILABLE_FAIL_CLOSED"]})
    if latch is not None: save(latch_path,latch)
    return policy,config,client,latch_path


def clean_scenario():
    return {"alerts:OPEN":[],"remediations:OPEN":[],"remediations:DELIVERED":[]}


def test_stale_known_latch_clears_after_two_clean_snapshots():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw); policy,config,client,latch=fixture(td,clean_scenario(),{
            "schema":mod.LATCH_SCHEMA,"active":True,"reason":"GUARDIAN_CORRECTIVE_DIRECTIVE_CRITICAL",
            "directive_id":"old"})
        rc,out=mod.reconcile(policy,config,client,False); x=json.loads(latch.read_text())
        assert rc==0 and out["status"]=="PASS" and out["action"]=="CLEAR_STALE_LATCH",out
        assert x["active"] is False and x["previous_directive_id"]=="old",x


def test_critical_alert_keeps_latch_active():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw); s=clean_scenario();s["alerts:OPEN"]=[{"alert_id":"a1","severity":"CRITICAL"}]
        policy,config,client,latch=fixture(td,s,None)
        rc,out=mod.reconcile(policy,config,client,False);x=json.loads(latch.read_text())
        assert rc==0 and out["action"]=="KEEP_OR_SET_ACTIVE",out
        assert x["active"] is True and x["critical_sources"][0]["id"]=="a1",x


def test_critical_delivered_remediation_keeps_latch_active():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw);s=clean_scenario();s["remediations:DELIVERED"]=[{
            "directive_id":"r1","severity":"CRITICAL","source_alert_id":"a1"}]
        policy,config,client,latch=fixture(td,s,{"schema":mod.LATCH_SCHEMA,"active":False,"reason":"clear"})
        _,out=mod.reconcile(policy,config,client,False);x=json.loads(latch.read_text())
        assert out["action"]=="KEEP_OR_SET_ACTIVE",out
        assert x["active"] is True and x["critical_sources"][0]["id"]=="r1",x


def test_guardian_read_failure_fails_closed():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw);s=clean_scenario();s["alerts:OPEN"]="__FAIL__"
        policy,config,client,latch=fixture(td,s,{"schema":mod.LATCH_SCHEMA,"active":False,"reason":"clear"})
        rc,out=mod.reconcile(policy,config,client,False);x=json.loads(latch.read_text())
        assert rc==0 and out["status"]=="DEFERRED",out
        assert x["active"] is True and x["reason"]=="GUARDIAN_STATE_UNAVAILABLE_FAIL_CLOSED",x


def test_unknown_active_reason_is_never_cleared():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw);original={"schema":mod.LATCH_SCHEMA,"active":True,"reason":"HUMAN_OUT_OF_BAND_HOLD"}
        policy,config,client,latch=fixture(td,clean_scenario(),original)
        _,out=mod.reconcile(policy,config,client,False);x=json.loads(latch.read_text())
        assert out["status"]=="HOLD" and out["action"]=="UNRECOGNIZED_ACTIVE_LATCH_PRESERVED",out
        assert x==original,x


def test_dry_run_never_mutates_latch():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw);original={"schema":mod.LATCH_SCHEMA,"active":True,
            "reason":"GUARDIAN_CORRECTIVE_DIRECTIVE_CRITICAL","directive_id":"old"}
        policy,config,client,latch=fixture(td,clean_scenario(),original)
        _,out=mod.reconcile(policy,config,client,True);x=json.loads(latch.read_text())
        assert out["action"]=="DRY_RUN_CLEAR_STALE_LATCH",out
        assert x==original,x


def test_canonical_emergency_stop_path_is_forbidden():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw);scenario=td/"scenario.json";client=td/"fake-client.py"
        policy=td/"policy.json";config=td/"config.json"
        save(scenario,clean_scenario());client.write_text(FAKE_CLIENT,encoding="utf-8")
        save(policy,{"critical_stop_required_file":str(mod.CANONICAL_STOP),"fake_scenario":str(scenario)})
        save(config,{"confirmation_delay_seconds":0,"managed_active_reasons":[]})
        try: mod.reconcile(policy,config,client,False)
        except ValueError as exc: assert "CANONICAL_EMERGENCY_STOP_MUTATION_FORBIDDEN" in str(exc)
        else: raise AssertionError("canonical stop path was not rejected")


def test_policy_and_systemd_are_zero_spend_and_bounded():
    cfg=json.loads((ROOT/"dev-hub/config/guardian-stop-latch-reconciliation.v1.json").read_text())
    service=(ROOT/"dev-hub/systemd/chacha-dev-guardian-stop-latch-reconciliation.service").read_text()
    timer=(ROOT/"dev-hub/systemd/chacha-dev-guardian-stop-latch-reconciliation.timer").read_text()
    assert cfg["invariants"]["automatic_external_spend_eur"]==0
    assert "ReadWritePaths=/opt/chacha-dev/runtime/guardian /opt/chacha-dev/runtime/control" in service
    assert "OnUnitActiveSec=180s" in timer


if __name__ == "__main__":
    tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith("test_") and callable(v)]
    for name,fn in tests:
        fn(); print(name+"=PASS")
    print("CHACHA_DEV_GUARDIAN_STOP_LATCH_RECONCILIATION=PASS")
    print("TEST_COUNT="+str(len(tests)))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
