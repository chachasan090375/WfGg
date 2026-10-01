#!/usr/bin/env python3
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"dev-hub/bin/learning-coverage-auditor.py"
POLICY=ROOT/"dev-hub/config/learning-coverage-audit.v1.json"

def run(*args):
    return subprocess.run([sys.executable,str(TOOL),*[str(x) for x in args]],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)

def canon(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def key(project,digest,ctx): return hashlib.sha256(canon({"project_id":project,"result_digest":digest,"learning_context":ctx}).encode()).hexdigest()
def load(p): return json.loads(Path(p).read_text())

class LearningCoverageAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.markers=self.root/"markers";self.markers.mkdir()
        self.ctx={"schema":"chacha.dev/verified-evidence-learning-context/v1","deployment_id":"d1","source_id":"s1","surface_kind":"runtime",
                  "component_lineage":{"schema":"chacha.dev/component-lineage/v1","components":[{"kind":"component","component_id":"c1","version":"1"}]}}
    def tearDown(self): self.tmp.cleanup()
    def ledger(self,event):
        p=self.root/("ledger-"+str(len(list(self.root.glob("ledger-*.json"))))+".json")
        p.write_text(json.dumps({"schema":"chacha.dev/evidence-ledger/v1","project":"p1","history":[event]}));return p
    def event(self,**kw):
        x={"event":"task-result-ingested","task_id":"t1","result_status":"OK","verification_status":"VERIFIED","result_digest":"sha256:"+"a"*64,"learning_context":self.ctx}
        x.update(kw);return x
    def test_eligible_event_with_marker_is_covered(self):
        event=self.event();ledger=self.ledger(event);digest=event["result_digest"]
        marker=self.markers/(key("p1",digest,self.ctx)+".json");marker.write_text("{}")
        out=self.root/"out.json";p=run("--policy",POLICY,"--ledger",ledger,"--marker-root",self.markers,"--output",out)
        self.assertEqual(p.returncode,0,p.stdout);x=load(out)
        self.assertEqual(x["status"],"PASS");self.assertEqual(x["coverage_percent"],100.0);self.assertEqual(x["gap_count"],0)
        self.assertFalse(x["production_mutation"]);self.assertFalse(x["d1_write_performed"])

    def test_eligible_event_without_marker_blocks(self):
        ledger=self.ledger(self.event());out=self.root/"out.json"
        p=run("--policy",POLICY,"--ledger",ledger,"--marker-root",self.markers,"--output",out)
        self.assertEqual(p.returncode,20,p.stdout);x=load(out)
        self.assertEqual(x["status"],"BLOCK");self.assertEqual(x["gap_count"],1);self.assertEqual(x["covered_count"],0)

    def test_missing_lineage_is_advisory_not_false_gap(self):
        event=self.event();event["learning_context"]={"schema":"chacha.dev/verified-evidence-learning-context/v1"}
        ledger=self.ledger(event);out=self.root/"out.json"
        p=run("--policy",POLICY,"--ledger",ledger,"--marker-root",self.markers,"--output",out)
        self.assertEqual(p.returncode,0,p.stdout);x=load(out)
        self.assertEqual(x["status"],"PASS_WITH_ADVISORY");self.assertEqual(x["missing_context_count"],1);self.assertEqual(x["eligible_count"],0)
    def test_non_verified_event_is_not_eligible(self):
        event=self.event(verification_status="PENDING")
        ledger=self.ledger(event);out=self.root/"out.json"
        p=run("--policy",POLICY,"--ledger",ledger,"--marker-root",self.markers,"--output",out)
        self.assertEqual(p.returncode,0,p.stdout);x=load(out)
        self.assertEqual(x["status"],"PASS");self.assertEqual(x["not_eligible_count"],1);self.assertEqual(x["eligible_count"],0)

if __name__=="__main__": unittest.main()
