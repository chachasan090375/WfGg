"""Real child processes and persisted events against a local Guardian fixture."""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

BIN=Path(__file__).resolve().parents[1]/'bin'
sys.path.insert(0,str(BIN))
from stop_state import blocks_execution

CLIENT='''import json,sys
from pathlib import Path
args=sys.argv
policy=json.loads(Path(args[args.index('--policy')+1]).read_text())
event=json.loads(Path(args[args.index('--event')+1]).read_text())
assert event['schema']=='chacha.dev/governance-action/v1'
assert event['action_id'] and event['phase'] in ['PRE_ACTION','POST_ACTION']
mode=policy['test_mode'];phase=event['phase']
if mode=='invalid': print('not-json');raise SystemExit(0)
if mode=='non_object': print('[]');raise SystemExit(0)
if mode in ['remediation_required','stop_recommended']:
    print(json.dumps({'verdict':'PASS',mode:True}));raise SystemExit(0)
blocked=event['evidence'].get('emergency_stop_active') is True or (mode=='pre_denied' and phase=='PRE_ACTION') or (mode=='post_denied' and phase=='POST_ACTION')
print(json.dumps({'verdict':'CRITICAL' if blocked else 'PASS','fixture':True,'event_id':event['event_id']}))
raise SystemExit(21 if blocked or mode=='inconsistent_exit' else 0)
'''

class ProcessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.events=self.root/'events'
        self.client=self.root/'client.py';self.client.write_text(CLIENT)
        self.policy=self.root/'policy.json';self.policy.write_text('{"test_mode":"pass"}')
        self.stop=self.root/'stop.json';self.stop.write_text('{"active":false}')
        self.marker=self.root/'child-ran'
        self.child=self.root/'child.py'
        self.child.write_text('from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text("executed")\n')
        spec=importlib.util.spec_from_file_location('process_fixture_orchestrator',BIN/'autonomous-project-orchestrator.py')
        self.orch=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.orch)
        self.orch._GUARDIAN_CONTEXT.clear()
        self.orch._GUARDIAN_CONTEXT.update({'enabled':True,'client':self.client,'policy':self.policy,
                                           'event_dir':self.events,'run_id':'fixture-run'})
        # Only observation adapters are isolated; run(), Guardian events and child execution are real.
        self.orch._observe_stage=lambda *args:None
        self.orch.ulr=types.SimpleNamespace(observe_platform=lambda **kwargs:None)
        self.orch.emergency_stop_active=lambda:blocks_execution(self.stop)
        self.orch.grr=types.SimpleNamespace(inject_context=lambda value,**kwargs:value)

    def mode(self,value):self.policy.write_text(json.dumps({'test_mode':value}))
    def run_child(self):return self.orch.run(self.child,[self.marker])
    def records(self):
        return sorted([json.loads(p.read_text()) for p in self.events.glob('*.json')
                       if not p.name.endswith('.verdict.json')],key=lambda x:x['phase']=='POST_ACTION')
    def assert_pair(self,outcome):
        events=self.records()
        self.assertEqual([x['phase'] for x in events],['PRE_ACTION','POST_ACTION'])
        self.assertEqual(events[0]['action_id'],events[1]['action_id'])
        self.assertEqual(events[1]['evidence']['execution_status'],outcome)
        verdicts=list(self.events.glob('*.verdict.json'))
        self.assertEqual(len(verdicts),2)

    def test_success_writes_real_pair(self):
        self.run_child();self.assertTrue(self.marker.is_file());self.assert_pair('SUCCESS')

    def test_child_failure_writes_real_post(self):
        self.child.write_text('import sys\nraise SystemExit(7)\n')
        with self.assertRaises(RuntimeError):self.run_child()
        self.assert_pair('FAILED')
        self.assertEqual(self.records()[1]['evidence']['execution_returncode'],7)

    def test_real_timeout_writes_post_and_does_not_replay(self):
        self.child.write_text('import time\ntime.sleep(5)\n')
        real_run=subprocess.run
        def bounded(argv,**kwargs):
            if str(self.child) in argv:kwargs['timeout']=0.1
            return real_run(argv,**kwargs)
        with patch.object(self.orch.subprocess,'run',side_effect=bounded):
            with self.assertRaises(subprocess.TimeoutExpired):self.run_child()
        self.assert_pair('TIMEOUT')
        self.assertFalse(self.marker.exists())

    def test_pre_refusal_never_launches(self):
        self.mode('pre_denied')
        with self.assertRaisesRegex(RuntimeError,'GUARDIAN_STAGE_BLOCK'):self.run_child()
        self.assertFalse(self.marker.exists());self.assertEqual(len(self.records()),1)

    def test_post_refusal_never_returns_success(self):
        self.mode('post_denied')
        with self.assertRaisesRegex(RuntimeError,'GUARDIAN_POST_ACTION_UNCONFIRMED'):self.run_child()
        self.assertTrue(self.marker.exists());self.assert_pair('SUCCESS')

    def test_invalid_guardian_json_never_launches(self):
        self.mode('invalid')
        with self.assertRaisesRegex(RuntimeError,'GUARDIAN_STAGE_UNAVAILABLE'):self.run_child()
        self.assertFalse(self.marker.exists())

    def test_pass_with_nonzero_client_exit_never_launches(self):
        self.mode('inconsistent_exit')
        with self.assertRaises(RuntimeError):self.run_child()
        self.assertFalse(self.marker.exists())

    def test_non_object_guardian_response_is_recorded_as_unavailable(self):
        self.mode('non_object')
        with self.assertRaisesRegex(RuntimeError,'GUARDIAN_STAGE_UNAVAILABLE'):self.run_child()
        self.assertFalse(self.marker.exists())
        verdict=json.loads(next(self.events.glob('*.verdict.json')).read_text())
        self.assertEqual(verdict['reason'],'INVALID_GUARDIAN_RESPONSE')

    def test_remediation_required_prevents_execution_even_with_pass(self):
        self.mode('remediation_required')
        with self.assertRaisesRegex(RuntimeError,'GUARDIAN_REMEDIATION_OR_STOP_REQUIRED'):self.run_child()
        self.assertFalse(self.marker.exists())

    def test_stop_recommended_prevents_execution_even_with_pass(self):
        self.mode('stop_recommended')
        with self.assertRaisesRegex(RuntimeError,'GUARDIAN_REMEDIATION_OR_STOP_REQUIRED'):self.run_child()
        self.assertFalse(self.marker.exists())

    def test_stop_active_unknown_or_invalid_never_launches(self):
        for content in ['{"active":true}','not-json',None]:
            if content is None:self.stop.unlink()
            else:self.stop.write_text(content)
            with self.assertRaisesRegex(RuntimeError,'GUARDIAN_STAGE_BLOCK'):self.run_child()
            self.assertFalse(self.marker.exists())

if __name__=='__main__':unittest.main()
