import datetime,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin/model-capability-confidence.py"
POL=json.loads((ROOT/"dev-hub/config/model-capability-confidence.v1.json").read_text())
spec=importlib.util.spec_from_file_location("m",BIN);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=datetime.datetime(2026,10,2,tzinfo=datetime.timezone.utc)

def o(result="PASS",days=0):
    t=NOW-datetime.timedelta(days=days)
    return {"schema":"chacha.dev/model-capability-observation/v1","model_id":"m","capability":"code-review","result":result,"observed_at":t.isoformat()}

def test_three_fresh_passes_verify():
    x=m.compute(POL,[o(),o(),o()],NOW);assert x["entries"][0]["state"]=="VERIFIED"

def test_stale_evidence_cannot_verify():
    x=m.compute(POL,[o(days=40),o(days=40),o(days=40)],NOW);assert x["entries"][0]["state"]=="STALE"

def test_negative_evidence_reduces_confidence():
    x=m.compute(POL,[o(),o("FAILED"),o("FAILED")],NOW);assert x["entries"][0]["state"]=="UNTRUSTED"

def test_confidence_never_grants_authority():
    x=m.compute(POL,[o(),o(),o()],NOW);assert x["execution_authority"] is False and x["automatic_external_spend_eur"]==0
