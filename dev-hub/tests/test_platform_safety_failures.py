"""Offline behavioral regressions; no runtime services, secrets or network."""
from __future__ import annotations
import ast
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

BIN=Path(__file__).resolve().parents[1]/'bin'
sys.path.insert(0,str(BIN))
from stop_state import inspect_stop, blocks_execution

def functions(name, selected, scope):
    tree=ast.parse((BIN/name).read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in selected]
    assert len(nodes)==len(selected)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),name,'exec'),scope)
    return scope

class StopTests(unittest.TestCase):
    def test_missing_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'missing'
            self.assertTrue(blocks_execution(p))
            self.assertEqual(inspect_stop(p)['state'],'UNKNOWN')

    def test_only_explicit_boolean_false_is_clear(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'stop.json'
            for value in [{'active':True},{'active':'false'},{'active':0},{},[],None]:
                p.write_text(json.dumps(value))
                self.assertTrue(blocks_execution(p),value)
            p.write_text('{"active":false}')
            self.assertFalse(blocks_execution(p))

    def test_corruption_and_unreadable_block(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'stop.json';p.write_text('not-json')
            self.assertTrue(blocks_execution(p))
            with patch.object(Path,'read_text',side_effect=PermissionError):
                self.assertTrue(blocks_execution(p))

    def test_orchestrator_uses_same_fail_closed_reader(self):
        scope={'Path':Path,'blocks_execution':blocks_execution}
        functions('autonomous-project-orchestrator.py',{'emergency_stop_active'},scope)
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(scope['emergency_stop_active'](Path(td)/'missing'))

    def test_run_controller_uses_same_fail_closed_reader(self):
        scope={}
        functions('run-controller.py',{'emergency_stop_active'},scope)
        with patch('stop_state.blocks_execution',return_value=True) as reader:
            self.assertTrue(scope['emergency_stop_active']())
            reader.assert_called_once_with()

class ActionTests(unittest.TestCase):
    def setUp(self):
        self.gate=Mock(return_value={'verdict':'PASS'})
        self.child=Mock(return_value=types.SimpleNamespace(returncode=0,stdout='fixture',stderr=''))
        self.scope={'Path':Path,'uuid':uuid,'sys':sys,'os':os,
          'subprocess':types.SimpleNamespace(run=self.child,PIPE=subprocess.PIPE,TimeoutExpired=subprocess.TimeoutExpired),
          'guardian_stage':self.gate,'_GUARDIAN_CONTEXT':{'run_id':'fixture'},'_STAGE_ROLE':{},
          '_observe_stage':Mock(),'ulr':types.SimpleNamespace(observe_platform=Mock())}
        functions('autonomous-project-orchestrator.py',{'run'},self.scope)

    def invoke(self):return self.scope['run'](Path('fixture.py'),[])

    def assert_pair(self,status):
        calls=self.gate.call_args_list
        self.assertEqual([c.args[2] for c in calls],['PRE_ACTION','POST_ACTION'])
        self.assertEqual(calls[0].args[3],calls[1].args[3])
        self.assertEqual(calls[1].kwargs['execution_result']['execution_status'],status)

    def test_success(self):
        self.assertEqual(self.invoke(),'fixture');self.assert_pair('SUCCESS')

    def test_child_failure_still_posts_and_raises(self):
        self.child.return_value.returncode=7
        with self.assertRaises(RuntimeError):self.invoke()
        self.assert_pair('FAILED')
        self.assertEqual(self.gate.call_args_list[1].kwargs['execution_result']['execution_returncode'],7)

    def test_timeout_still_posts_without_replay(self):
        self.child.side_effect=subprocess.TimeoutExpired('fixture',120)
        with self.assertRaises(subprocess.TimeoutExpired):self.invoke()
        self.assert_pair('TIMEOUT');self.child.assert_called_once()

    def test_spawn_error_still_posts(self):
        self.child.side_effect=FileNotFoundError('fixture')
        with self.assertRaises(FileNotFoundError):self.invoke()
        self.assert_pair('ERROR')

    def test_pre_refusal_does_not_execute_or_post(self):
        self.gate.side_effect=RuntimeError('PRE denied')
        with self.assertRaises(RuntimeError):self.invoke()
        self.child.assert_not_called();self.assertEqual(self.gate.call_count,1)

    def test_post_failure_prevents_success_response(self):
        self.gate.side_effect=[{'verdict':'PASS'},RuntimeError('POST unavailable')]
        with self.assertRaisesRegex(RuntimeError,'GUARDIAN_POST_ACTION_UNCONFIRMED'):self.invoke()
        self.child.assert_called_once()

    def test_post_failure_retains_original_execution_error(self):
        original=subprocess.TimeoutExpired('fixture',120)
        self.child.side_effect=original
        self.gate.side_effect=[{'verdict':'PASS'},RuntimeError('POST unavailable')]
        with self.assertRaises(RuntimeError) as caught:self.invoke()
        self.assertIs(caught.exception.__cause__,original)

    def test_post_precedes_fallible_observation(self):
        self.scope['_observe_stage'].side_effect=RuntimeError('fixture telemetry failure')
        with self.assertRaises(RuntimeError):self.invoke()
        self.assert_pair('SUCCESS')

class GuardianEventTests(unittest.TestCase):
    def test_failed_council_does_not_claim_final_decision(self):
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);client=t/'client.py';policy=t/'policy.json';output=t/'council.json'
            client.write_text('import json\nprint(json.dumps({"verdict":"PASS"}))\n')
            policy.write_text('{}');output.write_text('{"dispatch_allowed":true,"decisions":[]}')
            scope={'Path':Path,'sys':sys,'subprocess':subprocess,'json':json,'uuid':uuid,
                   '_GUARDIAN_CONTEXT':{'enabled':True,'client':client,'policy':policy,'event_dir':t/'events','run_id':'fixture'},
                   '_STAGE_ROLE':{'architecture-decision-council.py':'architecture-decision-council'},
                   'emergency_stop_active':lambda:False,
                   'grr':types.SimpleNamespace(inject_context=lambda context,**kwargs:context)}
            functions('autonomous-project-orchestrator.py',
                      {'load','save','_output_arg','_council_guardian_evidence','guardian_stage'},scope)
            scope['guardian_stage'](Path('architecture-decision-council.py'),['--output',output],
                                    'POST_ACTION','fixture-action',execution_result={
                                     'execution_status':'FAILED','execution_returncode':7,'execution_attempted':True})
            events=[json.loads(p.read_text()) for p in (t/'events').glob('*.json')
                    if not p.name.endswith('.verdict.json')]
            self.assertEqual(len(events),1)
            self.assertEqual(events[0]['action'],'REPORT_DECISION')
            self.assertEqual(events[0]['evidence']['execution_returncode'],7)
            self.assertEqual(events[0]['action_id'],'fixture-action')

if __name__=='__main__':unittest.main()
