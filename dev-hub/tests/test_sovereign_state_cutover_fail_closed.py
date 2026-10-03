#!/usr/bin/env python3
import json,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as td:
 td=Path(td)
 docs={
  'stage':{'status':'STAGED','revision':'f'*40},
  'services':{'status':'DRY_RUN_READY'},
  'conv':{'status':'PASS'},
  'gate':{'status':'READY_FOR_HUMAN_CUTOVER_APPROVAL'}
 }
 for n,x in docs.items():(td/(n+'.json')).write_text(json.dumps(x))
 out=td/'out.json'
 p=subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-cutover.py'),'--policy',str(ROOT/'dev-hub/config/sovereign-state-cutover.v1.json'),'--stage-receipt',str(td/'stage.json'),'--services-receipt',str(td/'services.json'),'--export-convergence',str(td/'conv.json'),'--cutover-gate',str(td/'gate.json'),'--authority-local',str(ROOT/'dev-hub/config/sovereign-state-authority.local.v1.json'),'--output',str(out)],stdout=subprocess.PIPE)
 assert p.returncode==20
 x=json.loads(out.read_text());assert x['status']=='HOLD';assert x['authority_switched'] is False
 assert 'COMPAT_BRIDGE_NOT_ACTIVE' in x['blockers']
 assert 'LOCAL_SERVICES_NOT_READY' in x['blockers']
print('CHACHA_DEV_SOVEREIGN_STATE_CUTOVER_FAIL_CLOSED=PASS')
