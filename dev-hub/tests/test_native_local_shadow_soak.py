#!/usr/bin/env python3
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'bin/native-local-shadow-soak.py'
s=importlib.util.spec_from_file_location('soak',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
POL=json.load(open(ROOT/'config/native-local-shadow-soak.v1.json'))

def fake_adapter(path:Path,good:bool=True)->None:
    content="offline zero rollback A RPC NO evidence" if good else "bad"
    path.write_text("#!/usr/bin/env python3\nimport json,sys\nout=sys.argv[sys.argv.index('--output')+1]\njson.dump({'status':'PASS','content':%r},open(out,'w'))\n"%content)
    path.chmod(0o755)

def test_good_fixture_passes():
    with tempfile.TemporaryDirectory() as td:
        d=Path(td);a=d/'adapter.py';rp=d/'runtime.json';fake_adapter(a,True);rp.write_text('{}')
        x=m.run(POL,a,rp)
        assert x['status']=='PASS' and x['pass_rate']==1.0
        assert 'cold_start_latency_seconds' in x
        assert x['production_activation_authorized'] is False

def test_bad_fixture_blocks():
    with tempfile.TemporaryDirectory() as td:
        d=Path(td);a=d/'adapter.py';rp=d/'runtime.json';fake_adapter(a,False);rp.write_text('{}')
        x=m.run(POL,a,rp)
        assert x['status']=='BLOCK' and x['pass_rate']<1.0

def test_policy_zero_spend_and_bounded_iterations():
    assert POL['automatic_external_spend_eur']==0
    assert POL['production_activation_authorized'] is False
    assert 1 <= POL['iterations'] <= 20
    assert POL['warmup_requests']==1
    assert POL['maximum_cold_start_latency_seconds']>=POL['maximum_p95_latency_seconds']
    assert all(1 <= int(c['max_tokens']) <= 64 for c in POL['cases'])
