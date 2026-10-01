#!/usr/bin/env python3
import json,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];TOOL=ROOT/"dev-hub/bin/autonomy_constitution.py";CFG=ROOT/"dev-hub/config/autonomy-constitution.v1.json"
def run(*a):return subprocess.run([str(x) for x in a],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
class ConstitutionTest(unittest.TestCase):
 def test_active_repository_passes(self):
  with tempfile.TemporaryDirectory() as t:
   out=Path(t)/"out.json";p=run(TOOL,"--repo-root",ROOT,"--config",CFG,"--output",out);self.assertEqual(p.returncode,0,p.stdout);x=json.loads(out.read_text());self.assertEqual(x["status"],"PASS");self.assertEqual(x["clause_count"],15);self.assertEqual(x["blocked_count"],0)
 def test_authoritative_source_drift_blocks(self):
  with tempfile.TemporaryDirectory() as t:
   tmp=Path(t)/"repo";shutil.copytree(ROOT/"dev-hub/config",tmp/"dev-hub/config")
   p=tmp/"dev-hub/config/platform-promotion-transaction.v1.json";x=json.loads(p.read_text());x["invariants"]["single_active_promotion_writer"]=False;p.write_text(json.dumps(x))
   out=Path(t)/"out.json";r=run(TOOL,"--repo-root",tmp,"--config",tmp/"dev-hub/config/autonomy-constitution.v1.json","--output",out);self.assertEqual(r.returncode,20);o=json.loads(out.read_text());self.assertEqual(o["status"],"BLOCK");self.assertTrue(any(v.get("id")=="single-writer-promotion" and v.get("status")=="BLOCK" for v in o["clauses"]))
 def test_constitution_is_reference_only(self):
  x=json.loads(CFG.read_text());self.assertEqual(x["authority_model"],"REFERENCE_ONLY_NO_DUPLICATE_RUNTIME_AUTHORITY");self.assertEqual(x["automatic_external_spend_eur"],0)
if __name__=="__main__":unittest.main()
