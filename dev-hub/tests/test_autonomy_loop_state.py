#!/usr/bin/env python3
import importlib.util,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'dev-hub/bin/autonomy-loop-state.py';s=importlib.util.spec_from_file_location('als',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
model={'reconciliation':{'issues':[{'code':'A','subject':'x'},{'code':'B','subject':'y'}]}};plan={'next_state':'DELEGATE','status':'READY'}
a=m.advance({},model,plan);assert a['cycle']==1 and len(a['issues'])==2,a
b=m.advance(a,model,plan);assert b['cycle']==2 and b['issues']['A|x']['first_seen_at']==a['issues']['A|x']['first_seen_at'],b
model2={'reconciliation':{'issues':[{'code':'B','subject':'y'}]}};plan2={'next_state':'CLASSIFY','status':'PARTIAL'}
c=m.advance(b,model2,plan2);assert c['issues']['A|x']['verified_resolved'] is True,c
assert c['issues']['B|y']['verified_resolved'] is False,c
assert len(c['history'])==3,c
print('CHACHA_DEV_AUTONOMY_LOOP_RESUME=PASS')
print('CHACHA_DEV_AUTONOMY_NO_REPLAY_VERIFIED_RESOLUTION=PASS')
