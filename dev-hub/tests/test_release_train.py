#!/usr/bin/env python3
import json, subprocess, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"dev-hub/bin/release_train.py"
POLICY=ROOT/"dev-hub/config/release-train.v1.json"

def run(*argv,cwd=None):
    return subprocess.run([str(x) for x in argv],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)

def git(repo,*args):
    p=run("git","-C",repo,*args)
    if p.returncode: raise AssertionError((p.stdout,p.stderr,args))
    return p.stdout.strip()

def load(p): return json.loads(Path(p).read_text())

class ReleaseTrainTest(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.repo=self.root/"repo";self.repo.mkdir()
        git(self.repo,"init","-q");git(self.repo,"config","user.name","Test");git(self.repo,"config","user.email","test@example.invalid")
        (self.repo/"README.md").write_text("base\n");git(self.repo,"add",".");git(self.repo,"commit","-qm","base");self.base=git(self.repo,"rev-parse","HEAD")
        self.a=self.make_candidate("a",{"a.txt":"A\n"});self.b=self.make_candidate("b",{"b.txt":"B\n"});self.c=self.make_candidate("c",{"a.txt":"C\n"})
        git(self.repo,"checkout","-q","master")
    def tearDown(self): self.t.cleanup()
    def make_candidate(self,name,files):
        git(self.repo,"checkout","-q","-B",name,self.base)
        for n,v in files.items():(self.repo/n).write_text(v)
        git(self.repo,"add",".");git(self.repo,"commit","-qm",name);return git(self.repo,"rev-parse","HEAD")
    def manifest(self,cid,candidate,writes=0,deps=None):
        ev=self.root/(cid+"-evidence.json");rb=self.root/(cid+"-rollback.json");ev.write_text(json.dumps({"status":"PASS","id":cid}));rb.write_text(json.dumps({"status":"READY","id":cid}))
        p=self.root/(cid+"-manifest.json");p.write_text(json.dumps({"chantier_id":cid,"repository":str(self.repo),"base_revision":self.base,"candidate_revision":candidate,
          "dependencies":deps or [],"evidence_refs":[str(ev)],"rollback":{"strategy":"git-revert","target_revision":self.base,"refs":[str(rb)]},
          "d1_budget":{"rows_read":writes*10,"rows_written":writes},"automatic_external_spend_eur":0}));return p,ev
    def freeze(self,cid,candidate,writes=0,deps=None):
        m,ev=self.manifest(cid,candidate,writes,deps);out=self.root/(cid+"-freeze.json");p=run(TOOL,"freeze","--manifest",m,"--policy",POLICY,"--output",out)
        return p,out,ev
    def test_independent_chantiers_compose_and_targeted_rollback(self):
        pa,ra,_=self.freeze("A",self.a,1000);pb,rb,_=self.freeze("B",self.b,2000);self.assertEqual(pa.returncode,0,pa.stdout);self.assertEqual(pb.returncode,0,pb.stdout)
        t0=self.root/"train0.json";self.assertEqual(run(TOOL,"train-init","--train-id","train-1","--base-revision",self.base,"--output",t0).returncode,0)
        t1=self.root/"train1.json";self.assertEqual(run(TOOL,"train-add","--train",t0,"--chantier-receipt",ra,"--policy",POLICY,"--output",t1).returncode,0)
        t2=self.root/"train2.json";self.assertEqual(run(TOOL,"train-add","--train",t1,"--chantier-receipt",rb,"--policy",POLICY,"--output",t2).returncode,0)
        plan=self.root/"plan.json";self.assertEqual(run(TOOL,"plan","--train",t2,"--policy",POLICY,"--output",plan).returncode,0)
        pl=load(plan);self.assertEqual(pl["chantier_order"],["A","B"]);self.assertEqual(pl["d1_budget"]["rows_written"],3000);self.assertEqual(pl["file_provenance"],{"a.txt":"A","b.txt":"B"})
        dest=self.root/"composite";receipt=self.root/"composite.json";p=run(TOOL,"compose","--train",t2,"--policy",POLICY,"--repository",self.repo,"--destination",dest,"--output",receipt)
        self.assertEqual(p.returncode,0,p.stdout);r=load(receipt);self.assertEqual(r["state"],"COMPOSITE_CANDIDATE_NOT_PROMOTED");self.assertFalse(r["production_mutation"])
        self.assertEqual(int(git(dest,"rev-list","--count",self.base+"..HEAD")),2);self.assertTrue((dest/"a.txt").is_file());self.assertTrue((dest/"b.txt").is_file())
        commit_a=r["commits"][0]["train_commit"];rv=run("git","-C",dest,"revert","--no-edit",commit_a);self.assertEqual(rv.returncode,0,(rv.stdout,rv.stderr))
        self.assertFalse((dest/"a.txt").exists());self.assertTrue((dest/"b.txt").is_file())
    def test_overlap_is_blocked(self):
        _,ra,_=self.freeze("A",self.a);_,rc,_=self.freeze("C",self.c)
        t0=self.root/"t0.json";run(TOOL,"train-init","--train-id","t","--base-revision",self.base,"--output",t0)
        t1=self.root/"t1.json";self.assertEqual(run(TOOL,"train-add","--train",t0,"--chantier-receipt",ra,"--policy",POLICY,"--output",t1).returncode,0)
        out=self.root/"t2.json";p=run(TOOL,"train-add","--train",t1,"--chantier-receipt",rc,"--policy",POLICY,"--output",out);self.assertEqual(p.returncode,20);self.assertIn("FILE_OVERLAP:a.txt",p.stdout)
    def test_dependency_is_blocked_in_v1(self):
        p,_,_=self.freeze("B",self.b,deps=["A"]);self.assertEqual(p.returncode,20);self.assertIn("DEPENDENCIES_FORBIDDEN_IN_V1",p.stdout)
    def test_frozen_evidence_drift_blocks_plan(self):
        _,ra,ev=self.freeze("A",self.a);t0=self.root/"t0.json";run(TOOL,"train-init","--train-id","t","--base-revision",self.base,"--output",t0)
        t1=self.root/"t1.json";run(TOOL,"train-add","--train",t0,"--chantier-receipt",ra,"--policy",POLICY,"--output",t1);ev.write_text("changed")
        p=run(TOOL,"plan","--train",t1,"--policy",POLICY,"--output",self.root/"plan.json");self.assertEqual(p.returncode,20);self.assertIn("FROZEN_EVIDENCE_DRIFT",p.stdout)

if __name__=="__main__":unittest.main()
