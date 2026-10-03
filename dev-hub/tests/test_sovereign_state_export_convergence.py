#!/usr/bin/env python3
import json,subprocess,tempfile,sys,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
services=['chacha-dev-guardian','chacha-dev-sentinel','chacha-dev-assurance-exchange','chacha-dev-learning-relay']
def receipt(suffix='x'):
 return {'status':'PASS','files':[{'database':s,'sha256':s+'-'+suffix} for s in services]}
with tempfile.TemporaryDirectory() as td:
 td=Path(td);a=td/'a.json';b=td/'b.json';o=td/'o.json';a.write_text(json.dumps(receipt()));b.write_text(json.dumps(receipt()))
 p=subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-export-convergence.py'),'--first',str(a),'--second',str(b),'--output',str(o)],stdout=subprocess.PIPE);assert p.returncode==0;assert json.loads(o.read_text())['status']=='PASS'
 b.write_text(json.dumps(receipt('changed')))
 p=subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-export-convergence.py'),'--first',str(a),'--second',str(b),'--output',str(o)],stdout=subprocess.PIPE);assert p.returncode==20;assert 'DOUBLE_EXPORT_DIGEST_NOT_CONVERGED' in json.loads(o.read_text())['blockers']
print('CHACHA_DEV_SOVEREIGN_STATE_EXPORT_CONVERGENCE_TEST=PASS')
