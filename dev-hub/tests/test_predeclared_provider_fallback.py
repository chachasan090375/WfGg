#!/usr/bin/env python3
import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def mod(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
sched=mod('sched',Path('dev-hub/bin/execution-scheduler.py'));resolver=mod('resolver',Path('dev-hub/bin/provider-resolver.py'))
REG={'capabilities':{'x':{'providers':[{'id':'owned','status':'ADOPT','fallback':['declared']},{'id':'undeclared','status':'ADOPT','fallback':[]},{'id':'declared','status':'PILOT','fallback':[]}]}}}
POL={'provider_selection':{'allow_unknown':False,'allow_degraded_for_non_production':False,'allow_degraded_for_production':False}}
def health(owned='UNAVAILABLE',**over):
 p={'owned':{'state':owned},'undeclared':{'state':'HEALTHY'},'declared':{'state':'HEALTHY'}};p['owned'].update(over);return {'providers':p}
class T(unittest.TestCase):
 def test_scheduler_uses_only_declared_fallback(self): self.assertEqual(sched.bind('x','read',REG,health(),POL)['provider'],'declared')
 def test_resolver_uses_only_declared_fallback(self): self.assertEqual(resolver.resolve('x',REG,health(),POL,'read')['provider'],'declared')
 def test_primary_policy_denial_blocks_scheduler(self): self.assertEqual(sched.bind('x','read',REG,health('HEALTHY',policy_allowed=False),POL)['reason'],'primary-policy-denied')
 def test_primary_policy_denial_blocks_resolver(self): self.assertEqual(resolver.resolve('x',REG,health('HEALTHY',policy_allowed=False),POL,'read')['reason'],'primary-policy-denied')
 def test_primary_security_gate_unavailable_blocks(self): self.assertEqual(sched.bind('x','read',REG,health('HEALTHY',security_gates_available=False),POL)['reason'],'primary-security-gate-unavailable')
if __name__=='__main__':unittest.main()
