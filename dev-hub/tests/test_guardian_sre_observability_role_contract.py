#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
x=json.load(open(ROOT/'dev-hub/config/guardian-role-contracts.v1.json'))
c=next(c for c in x['contracts'] if c.get('contract_id')=='role:sre-observability-engineer')
assert c['authority_scope']=='PLANNING_ONLY'
assert set(c['allowed_permissions'])=={'read','plan'}
assert set(c['allowed_actions'])=={'DISPATCH_TASK','REPORT_PLAN'}
for forbidden in ['PRODUCTION_DEPLOY','PROMOTE_COMPONENT','MUTATE_RUNTIME','MUTATE_APPLICATION','FINAL_ARCHITECTURE_DECISION','MODIFY_GUARDIAN_CONTRACTS','EXPAND_PERMISSIONS','MODIFY_ROUTE_AUTHORITY_POLICY','BYPASS_CANONICAL_ROUTE','EXPAND_ROUTE_AUTHORITY']:
    assert forbidden in c['forbidden_actions']
print('CHACHA_DEV_GUARDIAN_SRE_ROLE_CONTRACT=PASS')
