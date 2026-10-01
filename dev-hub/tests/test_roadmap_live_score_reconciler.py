import hashlib,importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin/roadmap-live-score-reconciler.py"
POL=json.loads((ROOT/"dev-hub/config/roadmap-live-score-reconciler.v1.json").read_text())
spec=importlib.util.spec_from_file_location("m",BIN);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ROAD={"schema":"chacha.dev/autonomy-gap-roadmap/v1","gaps":[{"id":"provider-independence","progress":35,"status":"RED","state":"OLD","evidence":"old"}]}

def ref(tmp):
    p=Path(tmp)/"e.json";p.write_text('{"ok":true}\n');d="sha256:"+hashlib.sha256(p.read_bytes()).hexdigest();return {"path":str(p),"digest":d}

def test_evidence_backed_update_applies():
    with tempfile.TemporaryDirectory() as td:
        u={"schema":"chacha.dev/roadmap-gap-update-set/v1","updates":[{"gap_id":"provider-independence","progress":80,"status":"ORANGE","state":"SHADOW","evidence_summary":"pilot","evidence_refs":[ref(td)]}]}
        x=m.reconcile(POL,ROAD,u);assert x["gaps"][0]["progress"]==80 and x["source_roadmap_mutated"] is False

def test_missing_evidence_blocks():
    u={"schema":"chacha.dev/roadmap-gap-update-set/v1","updates":[{"gap_id":"provider-independence","progress":80,"status":"ORANGE","evidence_refs":[]}]}
    try:m.reconcile(POL,ROAD,u);assert False
    except ValueError as e:assert "EVIDENCE_REQUIRED" in str(e)

def test_progress_range_blocks():
    with tempfile.TemporaryDirectory() as td:
        u={"schema":"chacha.dev/roadmap-gap-update-set/v1","updates":[{"gap_id":"provider-independence","progress":101,"status":"GREEN","evidence_refs":[ref(td)]}]}
        try:m.reconcile(POL,ROAD,u);assert False
        except ValueError as e:assert "PROGRESS_RANGE" in str(e)
