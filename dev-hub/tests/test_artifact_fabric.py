#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,io,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def mod():
 p=ROOT/'dev-hub/bin/artifact_fabric.py';s=importlib.util.spec_from_file_location('artifact_fabric',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=mod()

def store(td,maxb=1024*1024):return M.ArtifactStore(Path(td)/'artifacts',maxb)

def test_ingest_hashes_and_reads_content():
 with tempfile.TemporaryDirectory() as td:
  s=store(td);m=s.ingest_bytes(b'hello',filename='hello.txt',mime_type='text/plain',owner_key='op1',project_id='p1',origin='user-upload')
  assert m['sha256']=='sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
  assert s.content_path(m['artifact_id'],'op1','p1').read_bytes()==b'hello'
  assert m['execution_allowed'] is False and m['security_state']=='STORED_UNTRUSTED_NONEXECUTABLE'

def test_same_content_deduplicates_object_but_not_metadata_identity():
 with tempfile.TemporaryDirectory() as td:
  s=store(td);a=s.ingest_bytes(b'same',filename='a.bin',mime_type='application/octet-stream',owner_key='op1',project_id='p1');b=s.ingest_bytes(b'same',filename='b.bin',mime_type='application/octet-stream',owner_key='op1',project_id='p1')
  assert a['artifact_id']!=b['artifact_id'];assert a['object_relpath']==b['object_relpath'];assert len(list((Path(td)/'artifacts/objects').rglob('*')))==2  # prefix dir + object

def test_owner_and_project_binding_fail_closed():
 with tempfile.TemporaryDirectory() as td:
  s=store(td);m=s.ingest_bytes(b'x',filename='x',mime_type='text/plain',owner_key='op1',project_id='p1')
  for owner,project in [('op2','p1'),('op1','p2')]:
   try:s.authorize(m['artifact_id'],owner,project);raise AssertionError('expected block')
   except M.ArtifactError:pass

def test_unsafe_filename_is_sanitized_and_path_never_controls_storage():
 with tempfile.TemporaryDirectory() as td:
  s=store(td);m=s.ingest_bytes(b'x',filename='../../evil<script>.txt',mime_type='text/plain',owner_key='op1',project_id='p1')
  assert '..' not in m['filename'] and '/' not in m['filename'] and '<' not in m['filename']
  assert s.content_path(m['artifact_id'],'op1').is_relative_to((Path(td)/'artifacts/objects').resolve())

def test_size_and_length_mismatch_are_blocked():
 with tempfile.TemporaryDirectory() as td:
  s=store(td,4)
  try:s.ingest_bytes(b'12345',filename='x',mime_type='x',owner_key='op1',project_id='p1');raise AssertionError('expected too large')
  except M.ArtifactError as e:assert str(e)=='ARTIFACT_TOO_LARGE'
  try:s.ingest_stream(io.BytesIO(b'12'),3,'x','x','op1','p1');raise AssertionError('expected mismatch')
  except M.ArtifactError as e:assert str(e)=='ARTIFACT_LENGTH_MISMATCH'

def test_generated_output_is_persistent_but_still_nonexecuting():
 with tempfile.TemporaryDirectory() as td:
  src=Path(td)/'report.pdf';src.write_bytes(b'%PDF-fixture')
  s=store(td);m=s.ingest_path(src,'report.pdf','op1','p1',origin='generated',mime_type='application/pdf')
  assert m['security_state']=='GENERATED_NONEXECUTABLE_UNLESS_SEPARATELY_AUTHORIZED';assert m['execution_allowed'] is False
  assert s.list('op1','p1')[0]['artifact_id']==m['artifact_id']

def test_ref_validation_deduplicates_and_preserves_order():
 with tempfile.TemporaryDirectory() as td:
  s=store(td);a=s.ingest_bytes(b'a',filename='a',mime_type='x',owner_key='op1',project_id='p1');b=s.ingest_bytes(b'b',filename='b',mime_type='x',owner_key='op1',project_id='p1')
  r=s.validate_refs([a['artifact_id'],a['artifact_id'],b['artifact_id']],'op1','p1');assert [x['artifact_id'] for x in r]==[a['artifact_id'],b['artifact_id']]

def test_direct_operator_api_and_ui_contract_are_bidirectional():
 src=(ROOT/'dev-hub/bin/direct-operator-service.py').read_text();ui=(ROOT/'dev-hub/direct-operator-ui/index.html').read_text();policy=json.loads((ROOT/'dev-hub/config/direct-operator.v1.json').read_text());unit=(ROOT/'dev-hub/systemd/chacha-dev-direct-operator.service').read_text()
 for marker in ['path=="/api/v1/artifacts"','path.startswith("/api/v1/artifacts/")','artifact_ids=body.get("artifact_ids")','intent["artifact_refs"]','attached_artifact_ids']:
  assert marker in src,marker
 for marker in ['id="artifactFiles"','id="attach"','uploadArtifact(file)','artifact_ids:attachedSnapshot.map','/api/v1/artifacts/']:
  assert marker in ui,marker
 assert policy['artifact_fabric']['enabled'] is True and policy['invariants']['artifact_upload_never_implies_execution'] is True
 assert '/opt/chacha-dev/runtime/artifacts' in unit

def test_artifact_birth_contract_is_shadow_and_umg_required():
 b=json.loads((ROOT/'dev-hub/config/artifact-fabric.birth.v1.json').read_text());assert b['materialization_gate_required'] is True;assert b['governance_class']=='CORE_PLATFORM_COMPONENT';assert b['production_activation_authorized'] is False;assert b['automatic_external_spend_eur']==0

if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_ARTIFACT_FABRIC=PASS');print('TEST_COUNT='+str(len(tests)));print('PRODUCTION_ACTIVATION=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
