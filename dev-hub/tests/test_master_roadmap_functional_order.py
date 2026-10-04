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
assert f['current_focus']=='F13_NATIVE_LOCAL_HA_CURRENT_LINE_RECONCILIATION'
assert rows[7]['depends_on']==['F02','F03','F04','F05','F06']
assert rows[9]['reuse_asset']['sha']=='ae002f634a5b15794dbd1433c9cb056b90049e23'
print('CHACHA_DEV_MASTER_ROADMAP_FUNCTIONAL_ORDER_V2=PASS')
print('PRODUCTION_BASELINE=7160ef74c760d5d4b4e3d0f81af1a8c1d6d06ecb')
assert rows[10]['state']=='EXACT_SHA_QUALIFIED_SHADOW'
assert rows[10]['qualified_sha']=='80ebb885a54c78f7ef07358289b8bb02bb3f72e9'
assert rows[11]['depends_on']==['F10']
assert rows[11]['clean_host_reconstruction']=='PASS'
assert rows[11]['state']=='EXACT_SHA_QUALIFIED_SHADOW'
assert rows[11]['qualified_sha']=='71e6f1168ec64816684b0a91e8def3dc4ff01bbe'
assert rows[12]['depends_on']==['F11']
assert rows[12]['runtime_materialized'] is False
assert rows[12]['m2m_ingress_enabled'] is False
assert rows[12]['state']=='EXACT_SHA_TRIPLE_QUALIFIED_SHADOW'
assert rows[12]['qualified_sha']=='aebc7acc3d86c25bc2c2567a855f6bd2a76ff697'
assert rows[13]['depends_on']==['F12']
assert rows[13]['native_local_runtime_active'] is False
assert rows[13]['ha_rehearsal']=='BLOCK'
assert rows[13]['ha_failover_performed'] is False
print('CURRENT_FOCUS=F13_NATIVE_LOCAL_HA_CURRENT_LINE_RECONCILIATION')
