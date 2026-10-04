#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
x=json.loads((ROOT/'dev-hub/config/master-roadmap.v1.json').read_text())
assert x['authority']['current_execution_order']=='functional_execution_order_v2'
assert x['baseline']['production_sha']=='7160ef74c760d5d4b4e3d0f81af1a8c1d6d06ecb'
assert x['current_runtime_state']['transaction_status']=='FINALIZED'
f=x['functional_execution_order_v2'];rows=f['phases'];ids=[r['id'] for r in rows]
assert ids==['FOUNDATION_AND_SOVEREIGN_BASELINE','PROMOTION_TRANSACTION_CONTINUITY','ARTIFACT_FABRIC_AND_PROJECT_BINDING','SPECIALIST_CELL_AND_CAPABILITY_RESOLUTION','EXECUTION_PLANNER','RESOURCE_AWARE_SCHEDULER','VIRTUAL_OS_DEVICE_LAB','END_TO_END_CREATION_RUNTIME','IMPROVEMENT_INTELLIGENCE_AND_AUTONOMOUS_FACTORY','PLUGIN_AND_UPDATE_LIFECYCLE','CONSULTANT_PROJECT_TENANCY','RESILIENCE_AND_RECONSTRUCTIBILITY','REMOTE_MCP_PRIVATE_OPERATOR_ROUTE','NATIVE_LOCAL_AND_HA_DEEPENING']
assert f['current_focus']=='F09_PLUGIN_UPDATE_LIFECYCLE_CURRENT_LINE_RECONCILIATION'
assert rows[7]['depends_on']==['F02','F03','F04','F05','F06']
assert rows[9]['reuse_asset']['sha']=='ae002f634a5b15794dbd1433c9cb056b90049e23'
print('CHACHA_DEV_MASTER_ROADMAP_FUNCTIONAL_ORDER_V2=PASS')
print('PRODUCTION_BASELINE=7160ef74c760d5d4b4e3d0f81af1a8c1d6d06ecb')
print('CURRENT_FOCUS=F09_PLUGIN_UPDATE_LIFECYCLE_CURRENT_LINE_RECONCILIATION')
