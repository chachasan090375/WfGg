#!/usr/bin/env python3
import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PLANNER=ROOT/"dev-hub/bin/human-remediation-plan.py"
RUNNER=ROOT/"dev-hub/bin/autonomy-loop-runner.py"
POLICY=ROOT/"dev-hub/config/human-remediation-planning.v1.json"

def run(*args): return subprocess.run([str(x) for x in args],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
def load(path): return json.loads(Path(path).read_text())

class HumanRemediationPlanTest(unittest.TestCase):
    def test_planner_prepares_dossier_without_mutation(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);plan=root/"plan.json";model=root/"model.json";out=root/"out.json"
            plan.write_text(json.dumps({"schema":"chacha.dev/autonomy-supervision-plan/v1","status":"AWAITING_HUMAN","next_state":"AWAIT_HUMAN","human_boundaries":[{"issue_code":"BIRTH_CONTRACT_INCOMPLETE","subject":"c1","owner":"universal-materialization-gate","reason":"BACKFILL_OR_RETIRE_COMPONENT"}]}))
            model.write_text(json.dumps({"reconciliation":{"issues":[{"code":"BIRTH_CONTRACT_INCOMPLETE","subject":"c1","class":"HUMAN_BOUNDARY","details":{"why":"test"}}]}}))
            p=run(sys.executable,PLANNER,"--plan",plan,"--self-model",model,"--policy",POLICY,"--output",out)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);x=load(out)
            self.assertEqual(x["state"],"PREPARED_AWAITING_HUMAN");self.assertEqual(x["dossier_count"],1)
            self.assertTrue(x["dossiers"][0]["approval_required"]);self.assertFalse(x["dossiers"][0]["auto_apply"])
            self.assertFalse(x["production_mutation"]);self.assertFalse(x["direct_mutation_authority"])
    def test_runner_materializes_human_dossier_before_stop(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);repo=root/"repo";binp=repo/"dev-hub/bin";cfg=repo/"dev-hub/config";runtime=root/"runtime";platform=root/"platform"
            binp.mkdir(parents=True);cfg.mkdir(parents=True);runtime.mkdir();platform.mkdir()
            shutil.copy2(RUNNER,binp/"autonomy-loop-runner.py");shutil.copy2(PLANNER,binp/"human-remediation-plan.py");shutil.copy2(POLICY,cfg/"human-remediation-planning.v1.json")
            (cfg/"autonomy-supervision.v1.json").write_text(json.dumps({"runtime":{"state_file":str(runtime/"unused.json"),"work_root":str(runtime/"unused"),"emergency_stop":str(runtime/"control/emergency-stop.json"),"max_cycles_per_run":1,"owner_timeout_seconds":30,"allowed_systemd_units":[],"max_attempts_per_issue":3,"retry_cooldown_seconds":0},"owner_actions":{}}))
            (cfg/"autonomy-self-model.v1.json").write_text("{}")
            (binp/"autonomy-self-model.py").write_text('''#!/usr/bin/env python3\nimport argparse,json\nfrom pathlib import Path\na=argparse.ArgumentParser();a.add_argument("--output",type=Path,required=True);a.add_argument("--repo-root");a.add_argument("--runtime-root");a.add_argument("--platform-root");a.add_argument("--policy");x=a.parse_args();x.output.parent.mkdir(parents=True,exist_ok=True);x.output.write_text(json.dumps({"reconciliation":{"issues":[{"code":"BIRTH_CONTRACT_INCOMPLETE","subject":"c1","class":"HUMAN_BOUNDARY","owner":"universal-materialization-gate","recommended_action":"BACKFILL_OR_RETIRE_COMPONENT","details":{"why":"fixture"}}]}}))\n''')
            (binp/"autonomy-supervision-controller.py").write_text('''#!/usr/bin/env python3\nimport argparse,json\nfrom pathlib import Path\na=argparse.ArgumentParser();a.add_argument("--mode");a.add_argument("--policy");a.add_argument("--self-model");a.add_argument("--output",type=Path,required=True);x=a.parse_args();x.output.write_text(json.dumps({"schema":"chacha.dev/autonomy-supervision-plan/v1","status":"AWAITING_HUMAN","next_state":"AWAIT_HUMAN","human_boundaries":[{"issue_code":"BIRTH_CONTRACT_INCOMPLETE","subject":"c1","owner":"universal-materialization-gate","reason":"BACKFILL_OR_RETIRE_COMPONENT"}],"automatic_external_spend_eur":0}))\n''')
            (binp/"autonomy-loop-state.py").write_text('#!/usr/bin/env python3\nraise SystemExit(0)\n')
            p=run(sys.executable,binp/"autonomy-loop-runner.py","--repo-root",repo,"--runtime-root",runtime,"--platform-root",platform,"--policy",cfg/"autonomy-supervision.v1.json","--self-policy",cfg/"autonomy-self-model.v1.json","--test-mode")
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            runs=list((runtime/"autonomy-core/work").glob("*/run.json"));self.assertEqual(len(runs),1)
            result=load(runs[0]);self.assertEqual(result["next_state"],"AWAIT_HUMAN");self.assertEqual(result["human_remediation_dossier_count"],1)
            dossier=Path(result["human_remediation_plan"]);self.assertTrue(dossier.is_file());d=load(dossier)
            self.assertEqual(d["state"],"PREPARED_AWAITING_HUMAN");self.assertFalse(d["production_mutation"])
            self.assertEqual(d["dossiers"][0]["required_action"],"BACKFILL_OR_RETIRE_COMPONENT")

    def test_planner_rejects_non_human_plan(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);plan=root/"plan.json";model=root/"model.json";out=root/"out.json"
            plan.write_text(json.dumps({"schema":"chacha.dev/autonomy-supervision-plan/v1","status":"CONVERGED","next_state":"RESUME","human_boundaries":[]}));model.write_text(json.dumps({"reconciliation":{"issues":[]}}))
            p=run(sys.executable,PLANNER,"--plan",plan,"--self-model",model,"--policy",POLICY,"--output",out)
            self.assertEqual(p.returncode,20);self.assertEqual(load(out)["status"],"BLOCK")

if __name__=="__main__": unittest.main()
