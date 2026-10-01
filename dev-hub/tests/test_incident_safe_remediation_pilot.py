import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/incident-safe-remediation-pilot.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
R=Path('/opt/chacha-dev/runtime/worktrees/incident-safe-remediation-router-v1');P=Path('/opt/chacha-dev/runtime/worktrees/progress-state-recovery-v1')
def test_prepared_components_pass_isolated_pilot():
 o=M.pilot(R/'dev-hub/bin/incident-safe-remediation-router.py',R/'dev-hub/config/incident-safe-remediation-router.v1.json',P/'dev-hub/bin/progress-state-recovery.py',P/'dev-hub/config/progress-state-recovery.v1.json');assert o['status']=='PASS' and o['safe_auto_remediation_proved'] is True
def test_no_production_mutation():
 o=M.pilot(R/'dev-hub/bin/incident-safe-remediation-router.py',R/'dev-hub/config/incident-safe-remediation-router.v1.json',P/'dev-hub/bin/progress-state-recovery.py',P/'dev-hub/config/progress-state-recovery.v1.json');assert o['production_mutation'] is False and o['destructive_operation'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
