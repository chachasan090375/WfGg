import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/autonomy-constitution-drift-watch.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/autonomy-constitution-drift-watch.v1.json').read_text())
def v(status='PASS',digest='sha256:a'):return {'schema':'chacha.dev/autonomy-constitution-verification/v1','status':status,'constitution_digest':digest,'blocked_count':0 if status=='PASS' else 1}
def test_first_pass_stable(): assert M.watch(POL,v(),None)['status']=='STABLE'
def test_same_digest_stable(): assert M.watch(POL,v(),{'last_good_digest':'sha256:a'})['status']=='STABLE'
def test_digest_change_requires_review(): assert M.watch(POL,v(digest='sha256:b'),{'last_good_digest':'sha256:a'})['status']=='REVIEW_REQUIRED'
def test_block_is_critical(): assert M.watch(POL,v('BLOCK'),{'last_good_digest':'sha256:a'})['status']=='CRITICAL'
def test_watch_never_mutates(): assert M.watch(POL,v(),None)['constitution_mutation_authorized'] is False
if __name__=='__main__':
 for n,x in sorted(globals().items()):
  if n.startswith('test_'):x();print(n+'=PASS')
