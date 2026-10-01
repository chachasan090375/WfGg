#!/usr/bin/env python3
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"dev-hub/bin/foundry-pilot-change-set.py"
POLICY=ROOT/"dev-hub/config/foundry-pilot-change-set.v1.json"

def cmd(*args,cwd=None):
    return subprocess.run([str(x) for x in args],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
def git(repo,*args):
    p=cmd("git",*args,cwd=repo)
    if p.returncode: raise RuntimeError(p.stderr)
    return p.stdout.strip()
def load(p): return json.loads(Path(p).read_text())

class FoundryPilotChangeSetTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.repo=self.root/"repo";self.repo.mkdir()
        git(self.repo,"init","-q");git(self.repo,"config","user.email","test@localhost");git(self.repo,"config","user.name","Test")
        (self.repo/"a.txt").write_text("base\n");git(self.repo,"add",".");git(self.repo,"commit","-qm","base");self.inc=git(self.repo,"rev-parse","HEAD")
        (self.repo/"a.txt").write_text("candidate\n");(self.repo/"b.txt").write_text("new\n");git(self.repo,"add",".");git(self.repo,"commit","-qm","candidate");self.cand=git(self.repo,"rev-parse","HEAD")
    def tearDown(self): self.tmp.cleanup()
    def pilot(self,**changes):
        x={"schema":"chacha.dev/platform-component-comparative-pilot-result/v1","status":"PASS","pipeline_status":"PASS_HOLD_INCUMBENT",
           "run_id":"run1","dispatch_id":"d1","component_id":"core:test","incumbent_revision":self.inc,"candidate_revision":self.cand,
           "council_review_technical_pass":True,"comparison":{"candidate_technically_admissible_for_council_review":True},
           "human_explicit_promotion_approval_present":False,"production_change_authorized":False,"promotion_authorized":False,
           "automatic_external_spend_eur":0}
        x.update(changes);p=self.root/"pilot.json";p.write_text(json.dumps(x));return p
    def invoke(self,pilot):
        out=self.root/"out.json";p=cmd(sys.executable,TOOL,"--repository",self.repo,"--pilot-result",pilot,"--policy",POLICY,"--output",out)
        return p,load(out)

    def test_pass_produces_canonical_change_set(self):
        p,x=self.invoke(self.pilot());self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(x["schema"],"chacha.dev/golden-path-artifact-evidence/v1");self.assertEqual(x["artifact_id"],"change-set")
        self.assertEqual(x["details"]["state"],"READY_FOR_RELEASE_TRAIN");self.assertEqual(x["details"]["workspace_commit"],self.cand)
        self.assertEqual(x["details"]["incumbent_revision"],self.inc);self.assertEqual(x["details"]["files"],["a.txt","b.txt"])
        self.assertFalse(x["details"]["production_change_authorized"]);self.assertFalse(x["details"]["promotion_authorized"])

    def test_non_hold_pass_pipeline_blocks(self):
        p,x=self.invoke(self.pilot(pipeline_status="PILOT_BLOCKED_HOLD_INCUMBENT"));self.assertEqual(p.returncode,20);self.assertIn("PILOT_PIPELINE_NOT_HOLD_PASS",x["reason"])

    def test_premature_human_promotion_approval_blocks(self):
        p,x=self.invoke(self.pilot(human_explicit_promotion_approval_present=True));self.assertEqual(p.returncode,20);self.assertIn("HUMAN_PROMOTION_APPROVAL_MUST_BE_ABSENT",x["reason"])
    def test_empty_delta_blocks(self):
        p,x=self.invoke(self.pilot(candidate_revision=self.inc));self.assertEqual(p.returncode,20);self.assertIn("EMPTY_CHANGE_SET",x["reason"])

if __name__=="__main__": unittest.main()
