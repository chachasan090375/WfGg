#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))

spec=importlib.util.spec_from_file_location('direct',BIN/'direct-operator-service.py')
direct=importlib.util.module_from_spec(spec);assert spec and spec.loader
spec.loader.exec_module(direct)
odi=direct.odi
policy=json.load(open(ROOT/'dev-hub/config/operator-directives.v1.json'))
text='À partir de maintenant, tous les agents doivent hériter automatiquement des règles globales.'
classified=odi.classify(text,policy)
assert classified['structural'] is True,classified
assert classified['suggested_scope']=='PLATFORM_GLOBAL',classified

with tempfile.TemporaryDirectory(prefix='v820-directive-intake-') as td:
    td=Path(td)
    op=json.load(open(ROOT/'dev-hub/config/direct-operator.v1.json'))
    op['runtime_root']=str(td/'operator')
    state=direct.State(ROOT,td,op)
    state.operator_directive_intake=td/'intake.jsonl'
    state.channel_router=td/'missing-router.py'
    state.process('conversation-intake-job',text,'chacha-dev-platform','pilot@example.test','CONVERSATION')
    cjob=json.load(open(state.job_path('conversation-intake-job')))
    assert cjob['state']=='FAILED',cjob
    creq=cjob['request_id']
    creceipt=json.load(open(state.root/'requests'/creq/'operator-directive-intake.json'))
    assert creceipt['status']=='CAPTURED',creceipt
    assert creceipt['structural_candidate'] is True,creceipt

    state.translator=td/'missing-translator.py'
    state.process('build-intake-job',text,'chacha-dev-platform','pilot@example.test','BUILD')
    bjob=json.load(open(state.job_path('build-intake-job')))
    assert bjob['state']=='FAILED',bjob
    breq=bjob['request_id']
    breceipt=json.load(open(state.root/'requests'/breq/'operator-directive-intake.json'))
    assert breceipt['status']=='CAPTURED',breceipt
    assert breceipt['structural_candidate'] is True,breceipt

    rows=[json.loads(x) for x in state.operator_directive_intake.read_text().splitlines() if x.strip()]
    assert len(rows)==2,rows
    assert all(x['status']=='RECEIVED' for x in rows)
    assert all(x['activation_status']=='NOT_ACTIVE_UNTIL_PROPAGATION_VERIFIED' for x in rows)
    assert all(x['automatic_external_spend_eur']==0 for x in rows)
print('CHACHA_DEV_OPERATOR_DIRECTIVE_INTAKE=PASS')
print('CHACHA_DEV_DIRECTIVE_CAPTURE_BEFORE_CONVERSATION_ROUTER=PASS')
print('CHACHA_DEV_DIRECTIVE_CAPTURE_BEFORE_BUILD_TRANSLATOR=PASS')
print('CHACHA_DEV_PROMPT_SENT_IS_NOT_APPLICATION_PROOF=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
