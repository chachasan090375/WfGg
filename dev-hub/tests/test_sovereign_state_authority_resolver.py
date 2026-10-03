#!/usr/bin/env python3
import importlib.util,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import sovereign_state_authority as ssa
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'authority.json'
 x=ssa.load(p);assert x['mode']=='D1_REMOTE';assert ssa.endpoint('guardian',p).startswith('https://');assert ssa.d1_quota_applies(ssa.endpoint('guardian',p)) is True
 local=json.loads((ROOT/'dev-hub/config/sovereign-state-authority.local.v1.json').read_text());p.write_text(json.dumps(local))
 x=ssa.load(p);assert x['mode']=='LOCAL_SQLITE'
 assert ssa.endpoint('guardian',p)=='http://127.0.0.1:8871'
 assert ssa.endpoint('sentinel',p)=='http://127.0.0.1:8872'
 assert ssa.endpoint('assurance-exchange',p)=='http://127.0.0.1:8873'
 assert ssa.endpoint('learning-relay',p)=='http://127.0.0.1:8874'
 assert all(ssa.d1_quota_applies(ssa.endpoint(k,p)) is False for k in local['services'])
 bad=dict(local);bad['services']=dict(local['services']);bad['services']['guardian']='https://evil.invalid';p.write_text(json.dumps(bad))
 try:ssa.load(p);raise AssertionError('INVALID_ENDPOINT_ACCEPTED')
 except RuntimeError as e:assert 'ENDPOINT_INVALID' in str(e)
print('CHACHA_DEV_SOVEREIGN_STATE_AUTHORITY_RESOLVER=PASS')
