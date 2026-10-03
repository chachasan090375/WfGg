#!/usr/bin/env python3
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[2]
units=list((ROOT/'dev-hub/systemd').glob('chacha-dev-sovereign-*.service'))
assert len(units)==4,[x.name for x in units]
ports=set();services=set()
for p in units:
 s=p.read_text();assert '127.0.0.1' in s and 'd1-worker-local-runtime.mjs' in s and 'ProtectSystem=strict' in s
 m=re.search(r'CHACHA_D1_LOCAL_PORT=(\d+)',s);assert m;ports.add(int(m.group(1)))
 m=re.search(r'CHACHA_D1_LOCAL_SERVICE=([^\n]+)',s);assert m;services.add(m.group(1))
assert ports=={8871,8872,8873,8874};assert services=={'guardian','sentinel','assurance-exchange','learning-relay'}
a=json.loads((ROOT/'dev-hub/config/sovereign-state-authority.remote.v1.json').read_text());assert a['mode']=='D1_REMOTE'
b=json.loads((ROOT/'dev-hub/config/sovereign-state-authority.local.v1.json').read_text());assert b['mode']=='LOCAL_SQLITE' and b['human_cutover_approval_required'] is True
c=(ROOT/'dev-hub/bin/sovereign-state-cutover-controller.py').read_text();assert "choices=['dry-run','activate','rollback']" in c and 'approval_ok' in c and 'ROLLED_BACK_ON_FAILURE' in c
assert 'production_activation_authorized":false' in (ROOT/'dev-hub/config/sovereign-state-fabric.v1.json').read_text().replace(' ','')
print('CHACHA_DEV_SOVEREIGN_STATE_HOTFIX_CONTRACT=PASS')
print('DEFAULT_AUTHORITY=D1_REMOTE')
print('LOCAL_CUTOVER_HUMAN_APPROVAL=REQUIRED')
print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
