import json
import runpy
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))

gate=runpy.run_path(str(
    Path(__file__).resolve().parents[1]
    / "bin/universal-materialization-gate.py"
))

def trial(birth,allowed):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"registry.json"
        state={
            "schema":gate["DYNAMIC_SCHEMA"],
            "registrations":[{
                "component_id":"probe",
                "status":"REGISTERED_PENDING_ACTIVATION",
                "birth_contract":birth
            }],
            "history":[]
        }
        p.write_text(json.dumps(state))
        if allowed:
            gate["transition"](p,"probe","ACTIVE")
            assert json.loads(p.read_text())["registrations"][0]["status"]=="ACTIVE"
        else:
            try:
                gate["transition"](p,"probe","ACTIVE")
            except ValueError as e:
                assert "ACTIVATION_UMG_BIRTH_CONTRACT_NOT_VERIFIED" in str(e)
            else:
                raise AssertionError("UMG_ACTIVATION_BYPASS")
            assert json.loads(p.read_text())["registrations"][0]["status"]=="REGISTERED_PENDING_ACTIVATION"

def test_umg_activation_proof():
    trial({},False)
    trial({"complete":True,"controls":{"x":{"status":"BLOCK"}}},False)
    trial({"complete":True,"controls":{"x":{"status":"PASS"}}},True)

if __name__=="__main__":
    test_umg_activation_proof()
    print("UMG_ACTIVATION_PROOF_GATE=PASS")
