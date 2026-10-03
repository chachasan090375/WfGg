import json, importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_v03_is_narrow_extension_not_shell():
 p=json.loads((ROOT/'config/policy.v3.json').read_text())
 assert p['command_execution_enabled'] is False
 assert p['file_write_enabled'] is False and p['git_mutation_enabled'] is False and p['service_mutation_enabled'] is False
 assert p['destructive_operations_enabled'] is False and p['automatic_external_spend_eur']==0
 assert p['governed_operation_allowlist'][-1]=='guardian_check_event'
 assert p['capability_evolution']['authority_expansion'] is False
 assert p['capability_evolution']['resolution_order']==['REUSE','EXTEND','ADAPT','CREATE']

def test_guardian_event_root_is_release_gates_only():
 p=json.loads((ROOT/'config/policy.v3.json').read_text())
 assert p['guardian_event_allowed_root']=='/opt/chacha-dev/runtime/release-gates'

def test_server_exposes_named_guardian_tool_without_generic_command():
 s=(ROOT/'src/chacha_remote_operator/server_v02.py').read_text()
 assert 'def guardian_check_event(event_path: str)' in s
 assert 'run_guardian_check_event(POLICY, event_path)' in s
 assert 'command_run' not in s

def test_adaptive_operation_has_fixed_guardian_argv_and_stop_checks():
 s=(ROOT/'src/chacha_remote_operator/adaptive_operations.py').read_text()
 assert "policy.require_operational()" in s
 assert "[sys.executable,str(client),'--policy',str(gp),'check','--event',str(source)]" in s
 assert 'shell=False' in s
 assert "GUARDIAN_EVENT_OUTSIDE_ALLOWLIST" in s
