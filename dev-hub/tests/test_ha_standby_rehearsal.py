import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/ha-standby-rehearsal.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/ha-standby-rehearsal.v1.json').read_text());REV='a'*40
def ready(**k):
 x={'status':'PASS','state':'READY_FOR_GOVERNED_FAILOVER_PILOT','platform_revision':REV,'primary_node_id':'vps','standby_node_id':'nas','single_writer_enforced':True,'fencing_ready':True,'rollback_ready':True,'bastion_failover_state':'RESERVED_INACTIVE','failover_authorized':False};x.update(k);return x
def test_ready_state_passes(): assert M.rehearse(POL,ready(),REV)['status']=='PASS'
def test_revision_mismatch_blocks(): assert M.rehearse(POL,ready(),'b'*40)['status']=='BLOCK'
def test_no_fencing_blocks(): assert M.rehearse(POL,ready(fencing_ready=False),REV)['status']=='BLOCK'
def test_failover_must_remain_unauthorized(): assert M.rehearse(POL,ready(failover_authorized=True),REV)['status']=='BLOCK'
def test_rehearsal_never_switches_writer():
 o=M.rehearse(POL,ready(),REV);assert o['writer_switch_performed'] is False and o['failover_performed'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
