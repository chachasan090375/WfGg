#!/usr/bin/env python3
import importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];TOOL=ROOT/"dev-hub/bin/canonical-route-authority.py"
spec=importlib.util.spec_from_file_location("cra",TOOL);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RouteAuthorityTest(unittest.TestCase):
 def test_active_candidate_passes(self):
  x=m.check(ROOT);self.assertEqual(x["status"],"PASS",x);self.assertEqual(x["issue_count"],0)
 def test_policy_denial_cannot_become_fallback(self):
  with tempfile.TemporaryDirectory() as t:
   tmp=Path(t);shutil.copytree(ROOT/"dev-hub/config",tmp/"dev-hub/config")
   p=tmp/"dev-hub/config/canonical-route-authority.v1.json";x=json.loads(p.read_text());
   fb=next(r for r in x["routes"] if r["route_id"]=="third-party-remote-fallback");fb["forbidden"].remove("policy-denied-bypass");p.write_text(json.dumps(x))
   o=m.check(tmp);self.assertEqual(o["status"],"BLOCK");self.assertIn("FALLBACK_POLICY_DENIAL_NOT_BLOCKED",o["issues"])
 def test_direct_operator_cannot_gain_route_authority(self):
  with tempfile.TemporaryDirectory() as t:
   tmp=Path(t);shutil.copytree(ROOT/"dev-hub/config",tmp/"dev-hub/config")
   p=tmp/"dev-hub/config/direct-operator.v1.json";x=json.loads(p.read_text());x["invariants"]["direct_central_orchestrator_bypass_forbidden"]=False;p.write_text(json.dumps(x))
   o=m.check(tmp);self.assertEqual(o["status"],"BLOCK")
if __name__=="__main__":unittest.main()
