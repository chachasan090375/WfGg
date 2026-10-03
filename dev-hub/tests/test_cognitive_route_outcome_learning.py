import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin/cognitive-route-outcome-learning.py"
POL=json.loads((ROOT/"dev-hub/config/cognitive-route-outcome-learning.v1.json").read_text())
spec=importlib.util.spec_from_file_location("m",BIN);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def e(model,task,status="PASS",lat=5):
    return {"schema":"chacha.dev/cognitive-route-outcome/v1","model_id":model,"task_class":task,"status":status,"latency_seconds":lat}

def test_good_model_becomes_candidate():
    x=m.summarize(POL,[e("a","code",lat=5),e("a","code",lat=7),e("a","code",lat=6)])
    assert x["groups"][0]["recommendation"]=="PROMOTION_CANDIDATE"
    assert x["router_mutation_authorized"] is False

def test_bad_model_degrades():
    x=m.summarize(POL,[e("a","code","FAILED"),e("a","code","FAILED"),e("a","code")])
    assert x["groups"][0]["recommendation"]=="DEGRADE_CANDIDATE"

def test_low_evidence_holds():
    x=m.summarize(POL,[e("a","code")])
    assert x["groups"][0]["recommendation"]=="HOLD_INSUFFICIENT_EVIDENCE"

def test_zero_spend_and_no_mutation():
    x=m.summarize(POL,[e("a","code")])
    assert x["automatic_external_spend_eur"]==0 and x["registry_mutation_authorized"] is False
