#!/usr/bin/env python3
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'config'
EVID=ROOT/'evidence'

def load(p): return json.loads(p.read_text(encoding='utf-8'))
def fail(msg): raise SystemExit('CHROME_DEVTOOLS_ENABLED_INVALID: '+msg)

contract=load(CFG/'mcp-chrome-devtools-contract.v1.json')
adapters=load(CFG/'provider-adapters.v1.json')
catalog=load(CFG/'mcp-provider-catalog.v1.json')
receipt=load(EVID/'chrome-devtools-mcp-enabled-2026-09-16.json')
readiness=load(EVID/'chrome-devtools-mcp-enable-readiness-2026-09-16.json')

if contract.get('runtime_status')!='ENABLED': fail('contract status')
a=adapters.get('adapters',{}).get('chrome-devtools-mcp-adapter',{})
if a.get('status')!='ENABLED' or a.get('supports')!=['read'] or a.get('executable') is not None: fail('adapter boundary')
p=adapters.get('providers',{}).get('chrome-devtools-mcp',{})
if p.get('adapter')!='chrome-devtools-mcp-adapter' or p.get('execution')!='external': fail('provider binding')
c=catalog.get('providers',{}).get('chrome-devtools-mcp',{})
if c.get('runtime_status')!='ENABLED' or c.get('provider_binding')!='chrome-devtools-mcp': fail('catalog status')
proto=contract.get('protocol',{})
if proto.get('dev_hub_preferred_protocol_version')!='2026-07-28': fail('baseline')
if proto.get('upstream_protocol_version')!='2025-11-25': fail('upstream protocol')
if proto.get('compatibility_mode')!='EXPLICIT_PROVIDER_COMPATIBILITY' or proto.get('generic_legacy_fallback') is not False: fail('compatibility')
if proto.get('provider_result_trust')!='UNVERIFIED' or proto.get('verification_broker_required') is not True: fail('verification boundary')
policy=contract.get('tool_policy',{})
for key in ('javascript_evaluation','browser_interaction','workspace_write','repository_write','production_mutation'):
    if policy.get(key) is not False: fail('unsafe boundary '+key)
if policy.get('adapter_internal_allow')!=['navigate_page'] or policy.get('caller_direct_tool_selection') is not False: fail('controlled navigation boundary')
enable=contract.get('enablement_qualification',{})
if enable.get('transition')!='PILOT->ENABLED': fail('transition')
if enable.get('readiness_workflow_run_id')!=35122620991 or enable.get('sandbox_workflow_run_id')!=35122821172: fail('source runs')
if enable.get('repeatability_runs')!=3 or enable.get('provider_health')!='HEALTHY' or enable.get('rollback_defined') is not True or enable.get('sandbox_promotion_pass') is not True: fail('enablement gates')
if enable.get('supports')!=['read'] or enable.get('local_executable') is not None or enable.get('production_capable') is not False: fail('enablement boundary')
if enable.get('provider_result_verification')!='UNVERIFIED' or enable.get('verification_broker_required') is not True: fail('enablement verification')
if enable.get('automatic_promotion') is not False or enable.get('blockers')!=[]: fail('promotion boundary')
if readiness.get('status')!='READY_FOR_ENABLEMENT' or readiness.get('promotion_eligible') is not True or readiness.get('promotion_applied') is not False or readiness.get('blockers')!=[]: fail('readiness evidence')
if receipt.get('schema')!='chacha.dev/chrome-devtools-mcp-enabled-materialization/v1': fail('receipt schema')
if receipt.get('status_change')!={'previous':'PILOT','new':'ENABLED','applied':True,'automatic':False}: fail('receipt status change')
b=receipt.get('boundaries',{})
if b.get('supports')!=['read'] or b.get('local_executable') is not None or b.get('production_capable') is not False: fail('receipt boundary')
if b.get('provider_result_verification')!='UNVERIFIED' or b.get('verification_broker_required') is not True: fail('receipt verification')
if receipt.get('permissions_expanded') is not False or receipt.get('vps_modified') is not False or receipt.get('production_modified') is not False or receipt.get('blockers')!=[]: fail('receipt mutation')
admission=contract.get('admission',{})
if admission.get('automatic_promotion') is not False or admission.get('enablement_materialized') is not True or admission.get('next_transition')!='ENABLED->DISABLED': fail('admission')
print('CHROME_DEVTOOLS_MCP_ENABLED_VALID enabled=true read_only=true external=true controlled_navigation=true verification=UNVERIFIED production=false')
