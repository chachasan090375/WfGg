#!/usr/bin/env python3
import json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class T(unittest.TestCase):
 def test_remote_runtime_is_discovered_but_not_falsely_active(self):
  with tempfile.TemporaryDirectory() as t:
   out=Path(t)/'ccr.json'
   r=subprocess.run(['python3',str(ROOT/'dev-hub/bin/canonical_component_registry.py'),'--repo-root',str(ROOT),'--policy',str(ROOT/'dev-hub/config/canonical-component-registry.v1.json'),'--output',str(out)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);x=json.loads(out.read_text());row=next(v for v in x['components'] if v['name']=='chacha-remote-operator-python-runtime')
   self.assertEqual(row['canonical_status'],'REGISTERED_PENDING_ACTIVATION');self.assertEqual(row['birth_contract']['controls']['lifecycle']['value'],'MATERIALIZING');self.assertEqual(row['birth_contract']['controls']['health_contract']['value']['mcp_endpoint'],'http://127.0.0.1:8767/mcp')
if __name__=='__main__':unittest.main()
