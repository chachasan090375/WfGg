#!/usr/bin/env python3
import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('resolver',ROOT/'dev-hub/bin/canonical_route_resolver.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
POL=json.loads((ROOT/'dev-hub/config/canonical-route-authority.v1.json').read_text())
def state(**kw):
 x={'schema':'chacha.dev/route-health-snapshot/v1','canonical_stop_clear':True,'security_gates_available':True,'routes':{'remote-mcp-functional-build':{'capability_supported':True,'runtime_health':'HEALTHY','policy_allowed':True}}};x.update(kw);return x
class T(unittest.TestCase):
 def test_owned_route_wins_when_healthy(self): self.assertEqual(m.resolve(POL,state(),'remote-mcp-functional-build')['selected_route'],'remote-mcp-functional-build')
 def test_unavailable_owned_route_requires_human_fallback(self):
  x=state();x['routes']['remote-mcp-functional-build']['runtime_health']='UNAVAILABLE';o=m.resolve(POL,x,'remote-mcp-functional-build');self.assertEqual(o['status'],'HUMAN_FALLBACK_REQUIRED');self.assertEqual(o['selected_route'],'third-party-remote-fallback')
 def test_unsupported_capability_can_fallback(self):
  x=state();x['routes']['remote-mcp-functional-build']['capability_supported']=False;o=m.resolve(POL,x,'remote-mcp-functional-build');self.assertEqual(o['status'],'HUMAN_FALLBACK_REQUIRED')
 def test_policy_denied_never_falls_back(self):
  x=state();x['routes']['remote-mcp-functional-build']['policy_allowed']=False;o=m.resolve(POL,x,'remote-mcp-functional-build');self.assertEqual(o['status'],'BLOCK');self.assertEqual(o['reason'],'POLICY_DENIED')
 def test_stop_never_falls_back(self):
  o=m.resolve(POL,state(canonical_stop_clear=False),'remote-mcp-functional-build');self.assertEqual(o['status'],'BLOCK')
 def test_security_gate_unavailable_never_falls_back(self):
  o=m.resolve(POL,state(security_gates_available=False),'remote-mcp-functional-build');self.assertEqual(o['status'],'BLOCK')
if __name__=='__main__':unittest.main()
