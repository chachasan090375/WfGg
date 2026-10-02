import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/persistent-mission-scheduler-bridge.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/persistent-mission-scheduler-bridge.v1.json').read_text())
MISSION={'schema':'chacha.dev/persistent-mission/v1','mission_id':'m1','task_order':['a','b','c'],'completed_tasks':['a']}
GRAPH={'schema':'chacha.dev/task-graph/v1','project':'p','transition':'X','tasks':[{'id':'a','depends_on':[]},{'id':'b','depends_on':['a']},{'id':'c','depends_on':['b']}]}
PLAN={'schema':'chacha.dev/execution-plan/v1','project':'p','transition':'X','waves':[{'index':1,'tasks':[{'task_id':'a'}]},{'index':2,'tasks':[{'task_id':'b'}]},{'index':3,'tasks':[{'task_id':'c'}]}]}

def test_filters_completed_task():
    o=M.build(POL,MISSION,PLAN,GRAPH,{'active':False});assert o['status']=='READY';assert o['pending_tasks']==['b','c'];assert [x['id'] for x in o['graph']['tasks']]==['b','c'];assert o['graph']['tasks'][0]['depends_on']==[]
def test_stop_blocks(): assert M.build(POL,MISSION,PLAN,GRAPH,{'active':True})['status']=='BLOCK'
def test_complete_when_no_pending():
    m={**MISSION,'completed_tasks':['a','b','c']};o=M.build(POL,m,PLAN,GRAPH,{'active':False});assert o['status']=='COMPLETE' and not o['scheduler_required']
def test_bridge_has_no_execution_authority():
    o=M.build(POL,MISSION,PLAN,GRAPH,{'active':False});assert o['bridge_executes_tasks'] is False and o['bridge_mutates_mission_state'] is False

if __name__=='__main__':
    for n,v in sorted(globals().items()):
        if n.startswith('test_'):v();print(n+'=PASS')
