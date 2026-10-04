#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
x=json.loads((ROOT/'dev-hub/config/master-roadmap.v1.json').read_text())
assert x['authority']['current_execution_order']=='functional_execution_order_v2'
assert x['baseline']['production_sha']=='7e7decc758217bb20c142a1bef6799fd70f796a4'
assert x['current_runtime_state']['transaction_status']=='FINALIZED'
f=x['functional_execution_order_v2'];rows=f['phases'];ids=[r['id'] for r in rows]
assert ids==['FOUNDATION_AND_SOVEREIGN_BASELINE','PROMOTION_TRANSACTION_CONTINUITY','ARTIFACT_FABRIC_AND_PROJECT_BINDING','SPECIALIST_CELL_AND_CAPABILITY_RESOLUTION','RESOURCE_AWARE_EXECUTION_PLANNER','VIRTUAL_OS_DEVICE_LAB','END_TO_END_CREATION_RUNTIME','IMPROVEMENT_INTELLIGENCE_AND_AUTONOMOUS_FACTORY','PLUGIN_AND_UPDATE_LIFECYCLE','CONSULTANT_PROJECT_TENANCY','RESILIENCE_AND_RECONSTRUCTIBILITY','REMOTE_MCP_PRIVATE_OPERATOR_ROUTE','NATIVE_LOCAL_AND_HA_DEEPENING']
assert f['current_focus'].startswith('F01_PROMOTION_TRANSACTION_CONTINUITY')
assert rows[6]['depends_on']==['F02','F03','F04','F05']
assert rows[8]['reuse_asset']['sha']=='ae002f634a5b15794dbd1433c9cb056b90049e23'
print('CHACHA_DEV_MASTER_ROADMAP_FUNCTIONAL_ORDER_V2=PASS')
print('PRODUCTION_BASELINE=7e7decc758217bb20c142a1bef6799fd70f796a4')
print('CURRENT_FOCUS=F01_PROMOTION_TRANSACTION_CONTINUITY')
