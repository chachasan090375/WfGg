#!/usr/bin/env python3
import json,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
P=json.loads((ROOT/'dev-hub/config/sovereign-state-cutover.v1.json').read_text())
assert P['rollback_floor']=='SOVEREIGN_STATE_COMPAT_BRIDGE'
assert P['rollback_below_bridge_after_local_writes_forbidden'] is True
assert P['cutover_requirements']['double_export_digest_convergence_required'] is True
assert P['cutover_requirements']['fresh_authoritative_export_required'] is True
assert P['required_bridge_revision']=='8c984ab17bf7911ea0537b6c755c2ad44337c969'
units=sorted((ROOT/'dev-hub/systemd/sovereign-state').glob('*.service'));assert len(units)==4
for u in units:
 s=u.read_text();assert '127.0.0.1' in s and 'ProtectSystem=strict' in s and 'NoNewPrivileges=true' in s
with tempfile.TemporaryDirectory() as td:
 o=Path(td)/'stage.json'
 proc=subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-stage-runtime.py'),'--repo-root',str(ROOT),'--candidate-root','/opt/chacha-dev/runtime/sovereign-state/candidate','--policy',str(ROOT/'dev-hub/config/sovereign-state-cutover.v1.json'),'--revision',subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'--output',str(o)],stdout=subprocess.PIPE)
 assert proc.returncode==0; x=json.loads(o.read_text());assert x['status']=='DRY_RUN' and x['authority_switched'] is False
print('CHACHA_DEV_SOVEREIGN_STATE_CUTOVER_PLAN=PASS')
print('PRODUCTION_MUTATION=NO')
