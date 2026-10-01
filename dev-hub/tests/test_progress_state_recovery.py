import importlib.util,json,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/progress-state-recovery.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/progress-state-recovery.v1.json').read_text())

def state(status='ERROR',age=300):
    t=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=age)).isoformat().replace('+00:00','Z')
    return {'schema':M.STATE_SCHEMA,'status':status,'platform_maturity_percent':86,'active_work_percent':28,'headline':'x','active_operation':'op1','modules':{},'updated_at':t}

def test_stale_terminal_recovers(): assert M.plan(POL,state())['action']=='ARCHIVE_AND_RESET'
def test_fresh_terminal_waits(): assert M.plan(POL,state(age=30))['action']=='NOOP'
def test_running_needs_inactive_evidence(): assert M.plan(POL,state('RUNNING'))['action']=='NOOP'
def test_running_can_recover_with_exact_inactive_evidence():
    p=M.plan(POL,state('RUNNING'),{'operation_id':'op1','operation_active':False});assert p['action']=='ARCHIVE_AND_RESET'
def test_recovery_preserves_maturity():
    x=M.recovered(state(),'x');assert x['platform_maturity_percent']==86 and x['status']=='IDLE' and x['last_operation']['id']=='op1'

if __name__=='__main__':
    for n,v in sorted(globals().items()):
        if n.startswith('test_'):v();print(n+'=PASS')
