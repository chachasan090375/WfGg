#!/usr/bin/env python3
import json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as td:
 td=Path(td);o=td/'out.json'
 p=subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-cutover-gate.py'),'--bootstrap',str(td/'missing.json'),'--output',str(o)],stdout=subprocess.PIPE)
 assert p.returncode==20
 x=json.loads(o.read_text());assert x['status']=='HOLD' and 'BOOTSTRAP_MISSING' in x['blockers'] and x['cutover_performed'] is False
 for name in ['bootstrap','local-pilot','nas-snapshot','d1-import','parity','dual-parity']:(td/(name+'.json')).write_text(json.dumps({'status':'PASS'}))
 args=[sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-cutover-gate.py')]
 for name in ['bootstrap','local-pilot','nas-snapshot','d1-import','parity','dual-parity']:args += ['--'+name,str(td/(name+'.json'))]
 args += ['--output',str(o)];p=subprocess.run(args,stdout=subprocess.PIPE);assert p.returncode==0
 x=json.loads(o.read_text());assert x['status']=='READY_FOR_HUMAN_CUTOVER_APPROVAL' and x['human_approval_required'] is True and x['cutover_performed'] is False
print('CHACHA_DEV_SOVEREIGN_STATE_CUTOVER_GATE_TEST=PASS')
