#!/usr/bin/env python3
import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CFG=ROOT/'dev-hub/config';PROJ=ROOT/'dev-hub/projects/chacha-remote-operator'
class T(unittest.TestCase):
 def test_two_authority_classes(self):
  x=json.loads((PROJ/'project-agent-registry.v1.json').read_text());a={r['agent_id']:r for r in x['agents']};self.assertEqual(set(a),{'remote-operator-gateway-agent','remote-operator-functional-ingress-agent'});self.assertFalse(a['remote-operator-gateway-agent']['direct_mutation_authority']);self.assertTrue(a['remote-operator-functional-ingress-agent']['direct_operator_m2m_required']);self.assertFalse(a['remote-operator-functional-ingress-agent']['technical_decision_authority'])
 def test_materialization_matches_v03_runtime(self):
  p=json.loads((PROJ/'config/policy.v3.json').read_text());m=json.loads((PROJ/'runtime.materialization.v1.json').read_text());self.assertEqual(p['port'],m['mcp_runtime']['port']);self.assertEqual(m['mcp_runtime']['port'],8767);self.assertEqual(m['scope'],'PLATFORM');self.assertFalse(m['activation']['production_active'])
 def test_m2m_is_bound_to_canonical_route_and_disabled(self):
  x=json.loads((CFG/'direct-operator-machine-ingress.v1.json').read_text());self.assertFalse(x['enabled']);self.assertEqual(x['service_contract']['canonical_route_id'],'remote-mcp-functional-build');self.assertEqual(x['governance']['guardian_role_extension'],'role:remote-operator-functional-ingress-agent');self.assertTrue(x['service_contract']['direct_central_orchestrator_call_forbidden']);self.assertFalse(x['activation']['production_activation_allowed'])
 def test_guardian_roles_are_split(self):
  x=json.loads((CFG/'guardian-role-contracts.v1.json').read_text());c={r['contract_id']:r for r in x['contracts']};self.assertEqual(c['role:remote-operator-gateway-agent']['authority_scope'],'BOUNDED_REMOTE_READ_ONLY');self.assertEqual(c['role:remote-operator-functional-ingress-agent']['authority_scope'],'FUNCTIONAL_BUILD_INTENT_HANDOFF_ONLY');self.assertIn('BYPASS_DIRECT_OPERATOR',c['role:remote-operator-functional-ingress-agent']['forbidden_actions'])
 def test_exposure_has_no_historical_pilot_binding(self):
  x=json.loads((PROJ/'config/chatgpt-exposure.v1.json').read_text());self.assertNotIn('first_pilot',x);self.assertNotIn('revision',x['source_candidate']);self.assertEqual(x['direct_operator_target']['canonical_route_id'],'remote-mcp-functional-build');self.assertFalse(x['direct_operator_target']['bridge_enabled'])
if __name__=='__main__':unittest.main()
