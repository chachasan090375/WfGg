#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'config' / 'mcp-chrome-devtools-contract.v1.json'
REGISTRY = ROOT / 'config' / 'provider-adapters.v1.json'
CATALOG = ROOT / 'config' / 'mcp-provider-catalog.v1.json'
EVIDENCE = ROOT / 'evidence' / 'chrome-devtools-mcp-contract-ok-2026-09-16.json'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fail(msg):
    raise SystemExit(f'CHROME_DEVTOOLS_MCP_CONTRACT_OK_INVALID: {msg}')


def main():
    c, r, catalog, ev = map(load, [CONTRACT, REGISTRY, CATALOG, EVIDENCE])
    if c.get('schema') != 'chacha.dev/mcp-chrome-devtools-contract/v1': fail('contract schema')
    if c.get('provider_id') != 'chrome-devtools-mcp' or c.get('adapter_id') != 'chrome-devtools-mcp-adapter': fail('identity')
    if c.get('runtime_status') != 'CONTRACT_OK' or c.get('decision') != 'ASSESS': fail('contract status')

    q = c.get('contract_qualification', {})
    if q.get('transition') != 'DESIGNED->CONTRACT_OK': fail('transition')
    if q.get('qualified_design_head') != 'cbfceef9f74e24e8d0e3494693866cbbd298811e': fail('design head')
    if q.get('qualified_design_workflow_run_id') != 35109820616 or q.get('qualified_design_workflow_conclusion') != 'success': fail('design CI')
    for key in ('static_contract_pass','dedicated_adapter_binding_pass','javascript_evaluation_denied','browser_interaction_denied','isolated_ephemeral_pilot_plan_pass','network_redaction_policy_defined','existing_browser_attach_denied'):
        if q.get(key) is not True: fail(key)
    for key in ('runtime_executed','browser_downloaded','vps_modified','permissions_expanded','automatic_promotion'):
        if q.get(key) is not False: fail(key)

    execution = c.get('execution', {})
    if execution.get('launch_new_isolated_browser_only') is not True: fail('isolated launch')
    for key in ('attach_existing_browser_allowed','auto_connect_allowed','browser_url_allowed','websocket_endpoint_allowed','authenticated_user_profile_allowed','production_target_allowed'):
        if execution.get(key) is not False: fail(key)

    hardening = c.get('runtime_hardening', {})
    flags = set(hardening.get('required_flags') or [])
    for flag in ('--headless=true','--isolated=true','--no-javascript-evaluation','--no-performance-crux','--no-usage-statistics','--redact-network-headers'):
        if flag not in flags: fail(f'missing hardening flag {flag}')
    if hardening.get('allow_unrestricted_paths') is not False: fail('unrestricted paths')

    tools = c.get('tool_policy', {})
    if tools.get('default') != 'DENY': fail('default deny')
    denied = set(tools.get('explicit_deny') or [])
    for tool in ('evaluate_script','click','fill','type_text','upload_file','navigate_page','new_page','performance_start_trace'):
        if tool not in denied: fail(f'unsafe tool {tool}')
    for key in ('javascript_evaluation','file_upload','form_submission','browser_interaction','workspace_write','repository_write','production_mutation'):
        if tools.get(key) is not False: fail(f'{key} open')
    if tools.get('filename_argument_for_read_tools') != 'DENY': fail('filename writes')

    network = c.get('network_policy', {})
    for key in ('test_or_preview_origins_only','allowed_url_patterns_required_at_runtime','redirect_target_must_be_revalidated_by_adapter','network_headers_redacted'):
        if network.get(key) is not True: fail(key)
    if network.get('request_or_response_body_capture_default') != 'DENY': fail('body capture')

    provider = (r.get('providers') or {}).get('chrome-devtools-mcp')
    adapter = (r.get('adapters') or {}).get('chrome-devtools-mcp-adapter')
    if provider != {'adapter':'chrome-devtools-mcp-adapter','kind':'mcp','execution':'external'}: fail('provider binding')
    if not isinstance(adapter, dict) or adapter.get('status') != 'CONTRACT_OK': fail('adapter status')
    if adapter.get('executable') not in {None,''} or adapter.get('supports') != ['read']: fail('adapter permission/runtime')

    entry = (catalog.get('providers') or {}).get('chrome-devtools-mcp')
    if not isinstance(entry, dict): fail('catalog entry')
    if entry.get('runtime_status') != 'CONTRACT_OK' or entry.get('decision') != 'ASSESS': fail('catalog state')
    if entry.get('provider_binding') != 'chrome-devtools-mcp': fail('catalog binding')
    if entry.get('health_probe') != 'chrome-devtools-provider-protocol-tools-list-and-isolated-browser-launch': fail('health probe')

    if c.get('protocol', {}).get('provider_result_trust') != 'UNVERIFIED': fail('trust')
    if c.get('protocol', {}).get('verification_broker_required') is not True: fail('verification broker')
    if c.get('protocol', {}).get('generic_legacy_fallback') is not False: fail('legacy fallback')
    if c.get('admission', {}).get('next_transition') != 'CONTRACT_OK->PILOT': fail('next transition')
    if c.get('admission', {}).get('automatic_promotion') is not False: fail('automatic promotion')

    if ev.get('schema') != 'chacha.dev/mcp-contract-qualification-evidence/v1': fail('evidence schema')
    if ev.get('provider') != 'chrome-devtools-mcp' or ev.get('adapter') != 'chrome-devtools-mcp-adapter': fail('evidence identity')
    if ev.get('transition') != 'DESIGNED->CONTRACT_OK': fail('evidence transition')
    src = ev.get('source', {})
    if src.get('qualified_head') != 'cbfceef9f74e24e8d0e3494693866cbbd298811e' or src.get('workflow_run_id') != 35109820616 or src.get('workflow_conclusion') != 'success': fail('evidence source')
    if any(v != 'PASS' for v in (ev.get('checks') or {}).values()): fail('evidence checks')
    runtime = ev.get('runtime', {})
    if any(runtime.get(k) is not False for k in ('executed','browser_downloaded','vps_modified','production_modified')): fail('runtime claim')
    promotion = ev.get('promotion', {})
    if promotion.get('eligible') is not True or promotion.get('target') != 'CONTRACT_OK' or promotion.get('automatic') is not False or promotion.get('blockers') != []: fail('promotion evidence')

    print('CHROME_DEVTOOLS_MCP_CONTRACT_OK_VALID: static=true runtime=false browser=false vps=false next=PILOT')


if __name__ == '__main__':
    main()
