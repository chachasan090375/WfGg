import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/persistent-mission-e2e-pilot.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
BASE=Path('/opt/chacha-dev/platform/current');BR=Path('/opt/chacha-dev/runtime/worktrees/persistent-mission-scheduler-bridge-v1')
def test_real_prepared_components_resume_without_execution():
 o=M.pilot(BASE/'dev-hub/bin/persistent-mission-controller.py',BASE/'dev-hub/config/persistent-missions.v1.json',BR/'dev-hub/bin/persistent-mission-scheduler-bridge.py',BR/'dev-hub/config/persistent-mission-scheduler-bridge.v1.json');assert o['status']=='PASS' and o['pending_tasks']==['b']
def test_pilot_never_executes_tasks():
 o=M.pilot(BASE/'dev-hub/bin/persistent-mission-controller.py',BASE/'dev-hub/config/persistent-missions.v1.json',BR/'dev-hub/bin/persistent-mission-scheduler-bridge.py',BR/'dev-hub/config/persistent-mission-scheduler-bridge.v1.json');assert o['task_execution_performed'] is False and o['production_mutation'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
