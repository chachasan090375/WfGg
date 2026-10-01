import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/autonomy-evidence-publisher.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/autonomy-evidence-publisher.v1.json').read_text())
def spec(status='PASS'):
 td=Path(tempfile.mkdtemp());p=td/'src.json';p.write_text(json.dumps({'schema':'x/v1','status':status,'platform_revision':'a'*40}));return {'evidence_id':'demo-proof','source_path':str(p),'expected_schema':'x/v1','expected_status':'PASS','revision_field':'platform_revision'}
def test_valid_source_builds_receipt():
 o=M.build(POL,spec());assert o['status']=='PASS' and o['source_digest'].startswith('sha256:')
def test_wrong_status_blocks():
 try:M.build(POL,spec('BLOCK'));assert False
 except ValueError as e:assert 'STATUS' in str(e)
def test_invalid_id_blocks():
 x=spec();x['evidence_id']='../../bad'
 try:M.build(POL,x);assert False
 except ValueError:pass
def test_publisher_has_no_authority():
 o=M.build(POL,spec());assert o['execution_authority'] is False and o['production_mutation'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
