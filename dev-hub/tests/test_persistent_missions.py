#!/usr/bin/env python3
import datetime,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"dev-hub/bin/persistent-mission-controller.py"
POLICY=ROOT/"dev-hub/config/persistent-missions.v1.json"

def run(*args):
    return subprocess.run([sys.executable,str(TOOL),*[str(x) for x in args]],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)

def load(path): return json.loads(Path(path).read_text())

class PersistentMissionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.plan=self.root/"plan.json";self.state=self.root/"mission/mission.json"
        plan={"schema":"chacha.dev/execution-plan/v1","project":"p","transition":"BUILD->VERIFY","waves":[
            {"index":1,"tasks":[{"task_id":"task-a"}]},{"index":2,"tasks":[{"task_id":"task-b"}]}
        ]}
        self.plan.write_text(json.dumps(plan))
    def tearDown(self): self.tmp.cleanup()
    def create(self,deadline=None):
        args=["create","--mission-id","m1","--goal","finish safely","--plan",self.plan,"--policy",POLICY,"--state",self.state]
        if deadline: args.extend(["--deadline-at",deadline])
        return run(*args)
    def test_create_resume_and_complete(self):
        p=self.create();self.assertEqual(p.returncode,0,p.stdout)
        out=self.root/"resume.json";r=run("resume","--state",self.state,"--plan",self.plan,"--policy",POLICY,"--output",out)
        self.assertEqual(r.returncode,0,r.stdout);x=load(out)
        self.assertEqual(x["status"],"READY");self.assertEqual(x["pending_tasks"],["task-a","task-b"])
        self.assertFalse(x["controller_executes_tasks"]);self.assertEqual(x["automatic_external_spend_eur"],0)
        for event,task in [("e1","task-a"),("e2","task-b")]:
            q=run("checkpoint","--state",self.state,"--policy",POLICY,"--event-id",event,"--task-id",task,"--result","PASS")
            self.assertEqual(q.returncode,0,q.stdout)
        r=run("resume","--state",self.state,"--plan",self.plan,"--policy",POLICY,"--output",out)
        self.assertEqual(r.returncode,0);self.assertEqual(load(out)["status"],"COMPLETE")
        c=run("complete","--state",self.state,"--policy",POLICY);self.assertEqual(c.returncode,0,c.stdout)
        self.assertEqual(load(self.state)["status"],"COMPLETE")

    def test_checkpoint_event_is_idempotent(self):
        self.assertEqual(self.create().returncode,0)
        args=("checkpoint","--state",self.state,"--policy",POLICY,"--event-id","same","--task-id","task-a","--result","FAILED")
        self.assertEqual(run(*args).returncode,0);self.assertEqual(run(*args).returncode,0)
        state=load(self.state);self.assertEqual(state["attempts"]["task-a"],1)
        journal=(self.state.parent/"checkpoints.jsonl").read_text().splitlines();self.assertEqual(len(journal),1)
    def test_plan_drift_is_blocked(self):
        self.assertEqual(self.create().returncode,0)
        x=load(self.plan);x["waves"][0]["tasks"].append({"task_id":"task-c"});self.plan.write_text(json.dumps(x))
        r=run("resume","--state",self.state,"--plan",self.plan,"--policy",POLICY)
        self.assertEqual(r.returncode,20);self.assertIn("EXECUTION_PLAN_DRIFT",r.stdout)

    def test_emergency_stop_blocks_resume(self):
        self.assertEqual(self.create().returncode,0)
        stop=self.root/"stop.json";stop.write_text(json.dumps({"active":True}))
        out=self.root/"resume.json";r=run("resume","--state",self.state,"--plan",self.plan,"--policy",POLICY,"--stop-state",stop,"--output",out)
        self.assertEqual(r.returncode,0,r.stdout);x=load(out)
        self.assertEqual(x["status"],"BLOCKED");self.assertEqual(x["reason"],"EMERGENCY_STOP_ACTIVE")

    def test_attempt_budget_escalates_to_human_boundary(self):
        self.assertEqual(self.create().returncode,0)
        for n in range(3):
            r=run("checkpoint","--state",self.state,"--policy",POLICY,"--event-id",f"f{n}","--task-id","task-a","--result","FAILED")
            self.assertEqual(r.returncode,0,r.stdout)
        out=self.root/"resume.json";run("resume","--state",self.state,"--plan",self.plan,"--policy",POLICY,"--output",out)
        x=load(out);self.assertEqual(x["status"],"AWAIT_HUMAN");self.assertEqual(x["reason"],"HUMAN_BOUNDARY_REQUIRED")

    def test_deadline_escalates_to_human_boundary(self):
        past=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=1)).isoformat()
        self.assertEqual(self.create(past).returncode,0)
        out=self.root/"resume.json";run("resume","--state",self.state,"--plan",self.plan,"--policy",POLICY,"--output",out)
        x=load(out);self.assertEqual(x["status"],"AWAIT_HUMAN");self.assertEqual(x["reason"],"MISSION_DEADLINE_EXCEEDED")

if __name__=="__main__": unittest.main()
