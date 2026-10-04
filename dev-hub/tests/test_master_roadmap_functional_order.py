#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
x=json.loads((ROOT/'dev-hub/config/master-roadmap.v1.json').read_text())
assert x['authority']['current_execution_order']=='functional_execution_order_v2'
f=x['functional_execution_order_v2']; assert f['authority']=='PRIMARY_CURRENT_EXECUTION_VIEW'
rows=f['phases']; ids=[r['id'] for r in rows]
assert ids==['FOUNDATION_AND_SOVEREIGN_BASELINE','PROMOTION_TRANSACTION_CONTINUITY','FEASIBILITY_AND_SOLUTION_COMPOSER_FINALIZATION','ARTIFACT_FABRIC_AND_PROJECT_BINDING','SPECIALIST_CELL_AND_CAPABILITY_RESOLUTION','RESOURCE_AWARE_EXECUTION_PLANNER','VIRTUAL_OS_DEVICE_LAB','END_TO_END_CREATION_RUNTIME','IMPROVEMENT_INTELLIGENCE_AND_AUTONOMOUS_FACTORY','PLUGIN_AND_UPDATE_LIFECYCLE','CONSULTANT_PROJECT_TENANCY_AND_PRODUCT_SURFACES','RESILIENCE_AND_RECONSTRUCTIBILITY','REMOTE_MCP_PRIVATE_OPERATOR_ROUTE','NATIVE_LOCAL_AND_HA_DEEPENING']
assert f['current_focus']=='F01_PROMOTION_TRANSACTION_CONTINUITY'
assert rows[7]['depends_on']==['F03','F04','F05','F06']
assert 'CORE_LOCKED structural promotion boundary' in rows[9]['includes']
assert x['authority']['production_convergence_order_role'].startswith('LEGACY_EVIDENCE_VIEW')
print('CHACHA_DEV_MASTER_ROADMAP_FUNCTIONAL_ORDER_V2=PASS')
print('CURRENT_FOCUS=F01_PROMOTION_TRANSACTION_CONTINUITY')
