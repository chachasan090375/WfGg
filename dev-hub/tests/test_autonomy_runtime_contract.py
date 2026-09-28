#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import canonical_component_registry as ccr

def load(p):return json.loads(Path(p).read_text())
reg=ccr.build_registry(ROOT,load(ROOT/'dev-hub/config/canonical-component-registry.v1.json'))
row=next((x for x in reg['components'] if x.get('name')=='autonomy-core-supervisor'),None)
assert row,row
assert row['governance_class']=='CORE_PLATFORM_COMPONENT',row
assert row['evolution_owner']=='branch-foundry',row
assert row['fleet_required'] is False,row
assert (row.get('birth_contract') or {}).get('complete') is True,row
assert 'technology-core-watch' in row.get('sources',[]),row
policy=load(ROOT/'dev-hub/config/autonomy-supervision.v1.json')
assert policy['invariants']['no_direct_mutation'] is True
assert policy['invariants']['supervisor_writes_owner_state'] is False
assert set(policy['runtime']['allowed_systemd_units'])=={'chacha-dev-agent-fleet-observatory.service','chacha-dev-intendant-hygiene.service','chacha-dev-autonomous-recovery-agent.service','chacha-dev-branch-foundry-lifecycle.service'}
service=(ROOT/'dev-hub/systemd/chacha-dev-autonomy-core.service').read_text()
timer=(ROOT/'dev-hub/systemd/chacha-dev-autonomy-core.timer').read_text()
assert 'autonomy-loop-runner.py' in service
assert 'ReadWritePaths=/opt/chacha-dev/runtime/autonomy-core' in service
assert '/opt/chacha-dev/platform/releases' not in next(x for x in service.splitlines() if x.startswith('ReadWritePaths='))
assert '/opt/chacha-dev/runtime/agent-evolution' not in next(x for x in service.splitlines() if x.startswith('ReadWritePaths='))
assert 'RestrictAddressFamilies=AF_UNIX' in service
assert 'NoNewPrivileges=true' in service
assert 'OnUnitActiveSec=10min' in timer and 'Persistent=true' in timer
lifecycle_row=next((x for x in reg['components'] if x.get('name')=='branch-foundry-lifecycle'),None)
assert lifecycle_row,lifecycle_row
assert lifecycle_row['governance_class']=='CORE_PLATFORM_COMPONENT',lifecycle_row
assert lifecycle_row['evolution_owner']=='branch-foundry',lifecycle_row
assert lifecycle_row['fleet_required'] is False,lifecycle_row
assert (lifecycle_row.get('birth_contract') or {}).get('complete') is True,lifecycle_row

branch_lifecycle=(ROOT/'dev-hub/systemd/chacha-dev-branch-foundry-lifecycle.service').read_text()
assert 'ephemeral_branch_lifecycle.py --mode reconcile' in branch_lifecycle
assert 'ReadWritePaths=/opt/chacha-dev/runtime/capsules /opt/chacha-dev/runtime/canonical-registry /opt/chacha-dev/runtime/branch-foundry-lifecycle' in branch_lifecycle
assert '/opt/chacha-dev/platform/releases' not in branch_lifecycle
assert 'NoNewPrivileges=true' in branch_lifecycle
print('CHACHA_DEV_AUTONOMY_CANONICAL_BIRTH=PASS')
print('CHACHA_DEV_AUTONOMY_LEAST_PRIVILEGE_RUNTIME=PASS')
print('CHACHA_DEV_AUTONOMY_OWNER_UNIT_ALLOWLIST=PASS')
print('CHACHA_DEV_AUTONOMY_TIMER_CONTRACT=PASS')
