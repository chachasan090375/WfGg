#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
wf=(ROOT/'.github/workflows/dev-hub-guardian-production-deploy.yml').read_text()
local=json.loads((ROOT/'dev-hub/config/sovereign-state-authority.local.v1.json').read_text())
assert '"triggers": {"crons": []}' in wf, 'Cloud Guardian fallback cron must stay quiesced after LOCAL_SQLITE cutover'
assert '"triggers": {"crons": ["* * * * *"]}' not in wf
assert local['mode']=='LOCAL_SQLITE'
assert local['fallback_services']['guardian'].startswith('https://chacha-dev-guardian.')
assert local['automatic_external_spend_eur']==0
print('CHACHA_DEV_SOVEREIGN_CLOUD_GUARDIAN_FALLBACK_QUIESCENCE=PASS')
print('D1_FALLBACK_RETAINED=YES')
print('CLOUD_GUARDIAN_CRON_RESTORE=NO')
