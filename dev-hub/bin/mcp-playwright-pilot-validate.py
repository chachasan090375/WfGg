#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / 'config'
EVID = ROOT / 'evidence'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def fail(msg):
    raise SystemExit(f'PLAYWRIGHT_MCP_PILOT_INVALID: {msg}')


def main():
    contract = load(CFG / 'mcp-playwright-contract.v1.json')
    adapters = load(CFG / 'provider-adapters.v1.json')
    catalog = load(CFG / 'mcp-provider-catalog.v1.json')
    runtime = load(EVID / 'playwright-mcp-pilot-runtime-2026-09-16.json')
    promotion = load(EVID / 'playwright-mcp-contract-ok-to-pilot-2026-09-16.json')
    receipt = load(EVID / 'playwright-mcp-pilot-promotion-35082644829-receipt.json')

    if contract.get('runtime_status') != 'PILOT':
        fail('contract status')
    if contract.get('admission', {}).get('next_transition') != 'PILOT->ENABLED':
        fail('next transition')

    adapter = adapters.get('adapters', {}).get('playwright-mcp-adapter', {})
    if adapter.get('status') != 'PILOT':
        fail('adapter status')
    if adapter.get('executable') is not None:
        fail('external adapter must not claim local executable')
    if adapter.get('supports') != ['read']:
        fail('adapter permissions expanded')

    provider_binding = adapters.get('providers', {}).get('playwright-mcp', {})
    if provider_binding.get('adapter') != 'playwright-mcp-adapter':
        fail('provider binding')
    if provider_binding.get('execution') != 'external':
        fail('execution kind')

    cat = catalog.get('providers', {}).get('playwright-mcp', {})
    if cat.get('runtime_status') != 'PILOT':
        fail('catalog status')
    if cat.get('provider_binding') != 'playwright-mcp':
        fail('catalog provider binding')

    if runtime.get('schema') != 'chacha.dev/playwright-mcp-pilot-runtime-evidence/v1':
        fail('runtime evidence schema')
    if runtime.get('package_version') != '0.0.81':
        fail('package version')
    if runtime.get('runtime_surface') != 'github-actions-ephemeral':
        fail('runtime surface')
    if runtime.get('eligible_for_pilot') is not True or runtime.get('blockers') != []:
        fail('runtime eligibility')
    for key in ('runtime_contract_pass','sandbox_only_pass','provisioning_pass','test_origin_navigation_pass','snapshot_pass','no_repository_workspace_write_pass'):
        if runtime.get(key) is not True:
            fail(key)
    if runtime.get('production_target') is not False:
        fail('production target')
    if runtime.get('unsafe_tool_invoked') is not False:
        fail('unsafe tool invocation')
    if runtime.get('result_trust') != 'UNVERIFIED':
        fail('provider result trust')
    if runtime.get('negotiated_era') != 'legacy' or runtime.get('negotiated_protocol_version') != '2025-11-25':
        fail('recorded compatibility')

    if promotion.get('schema') != 'chacha.dev/adapter-promotion-evidence/v1':
        fail('promotion evidence schema')
    for label in ('runtime-contract-pass','sandbox-only','provisioning-pass'):
        if promotion.get('evidence', {}).get(label, {}).get('status') != 'PASS':
            fail(f'promotion evidence {label}')

    if receipt.get('schema') != 'chacha.dev/adapter-promotion-report/v1':
        fail('promotion receipt schema')
    if receipt.get('transition') != 'CONTRACT_OK->PILOT':
        fail('promotion transition')
    if receipt.get('eligible') is not True or receipt.get('applied') is not True or receipt.get('blockers') != []:
        fail('promotion application')
    if receipt.get('production_capable') is not False:
        fail('production capability')
    if receipt.get('requires_local_executable') is not False:
        fail('local executable requirement')
    prev = receipt.get('previous_entry', {})
    new = receipt.get('new_entry', {})
    if prev.get('status') != 'CONTRACT_OK' or new.get('status') != 'PILOT':
        fail('receipt state transition')
    if new.get('executable') is not None or new.get('supports') != ['read']:
        fail('receipt permission drift')

    policy = contract.get('tool_policy', {})
    if policy.get('default') != 'DENY':
        fail('tool default policy')
    if 'browser_run_code_unsafe' not in policy.get('explicit_deny', []):
        fail('unsafe tool not denied')
    for key in ('arbitrary_javascript','file_upload','form_submission','webmcp_page_tools','workspace_write','repository_write','production_mutation'):
        if policy.get(key) is not False:
            fail(f'tool policy {key}')

    proto = contract.get('protocol', {})
    if proto.get('preferred_protocol_version') != '2026-07-28':
        fail('preferred protocol baseline')
    if proto.get('legacy_fallback') != 'EXPLICIT_PROVIDER_COMPATIBILITY':
        fail('legacy compatibility policy')
    if proto.get('legacy_result_requires_technology_radar_followup') is not True:
        fail('technology radar followup')

    print('PLAYWRIGHT_MCP_PILOT_VALID: state=PILOT read_only=true runtime=github-actions-ephemeral production=false unsafe_invoked=false compatibility=legacy-2025-11-25')


if __name__ == '__main__':
    main()
