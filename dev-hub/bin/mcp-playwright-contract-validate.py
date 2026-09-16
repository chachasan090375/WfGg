#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'config' / 'mcp-playwright-contract.v1.json'
REGISTRY = ROOT / 'config' / 'provider-adapters.v1.json'
CATALOG = ROOT / 'config' / 'mcp-provider-catalog.v1.json'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fail(msg):
    raise SystemExit(f'PLAYWRIGHT_MCP_DESIGN_INVALID: {msg}')


def main():
    c = load(CONTRACT)
    r = load(REGISTRY)
    catalog = load(CATALOG)

    if c.get('schema') != 'chacha.dev/mcp-playwright-contract/v1':
        fail('schema')
    if c.get('provider_id') != 'playwright-mcp' or c.get('adapter_id') != 'playwright-mcp-adapter':
        fail('identity')
    if c.get('decision') != 'ASSESS' or c.get('runtime_status') != 'DESIGNED':
        fail('design status')

    upstream = c.get('upstream', {})
    if upstream.get('package') != '@playwright/mcp':
        fail('package')
    if int(upstream.get('minimum_node_major') or 0) < 20:
        fail('node requirement')
    if upstream.get('runtime_must_pin_exact_version') is not True:
        fail('runtime version pinning')
    if upstream.get('technology_radar_tracks_releases') is not True:
        fail('technology radar')

    execution = c.get('execution', {})
    if execution.get('pilot_surface') != 'github-actions-ephemeral':
        fail('pilot surface')
    if execution.get('vps_install_allowed_at_design_stage') is not False:
        fail('VPS design install')
    if execution.get('isolated_session_required') is not True:
        fail('isolated session')
    if execution.get('persistent_profile') is not False:
        fail('persistent profile')
    if execution.get('headless') is not True or execution.get('browser') != 'chromium':
        fail('browser config')
    if execution.get('production_target_allowed') is not False:
        fail('production target')
    if execution.get('authenticated_user_profile_allowed') is not False:
        fail('authenticated profile')

    protocol = c.get('protocol', {})
    if protocol.get('transport') != 'stdio':
        fail('transport')
    if protocol.get('dev_hub_input') != 'chacha.dev/dispatch-envelope/v1':
        fail('input boundary')
    if protocol.get('dev_hub_output') != 'chacha.dev/task-result/v1':
        fail('output boundary')
    if protocol.get('provider_result_trust') != 'UNVERIFIED':
        fail('trust')
    if protocol.get('verification_broker_required') is not True or protocol.get('producer_must_not_self_verify') is not True:
        fail('verification separation')

    tools = c.get('tool_policy', {})
    allowed = set(tools.get('pilot_allow', []))
    required_allowed = {
        'browser_navigate', 'browser_snapshot', 'browser_find', 'browser_console_messages',
        'browser_network_requests', 'browser_network_request', 'browser_take_screenshot', 'browser_close'
    }
    if allowed != required_allowed:
        fail('pilot allowlist')
    denied = set(tools.get('explicit_deny', []))
    must_deny = {
        'browser_run_code_unsafe', 'browser_evaluate', 'browser_click', 'browser_type',
        'browser_fill_form', 'browser_file_upload', 'browser_drop', 'browser_webmcp_call'
    }
    if not must_deny.issubset(denied):
        fail('unsafe tools not denied')
    if tools.get('default') != 'DENY':
        fail('default deny')
    if tools.get('filename_argument_for_read_tools') != 'DENY':
        fail('read-tool filename writes')
    for key in ('arbitrary_javascript', 'file_upload', 'form_submission', 'webmcp_page_tools',
                'workspace_write', 'repository_write', 'production_mutation'):
        if tools.get(key) is not False:
            fail(f'{key} must be false')

    network = c.get('network_policy', {})
    required_true = ('test_or_preview_origins_only', 'allowed_origins_required_at_runtime',
                     'allowed_origins_is_not_treated_as_security_boundary', 'redirect_target_must_be_revalidated_by_adapter',
                     'service_workers_blocked_in_pilot')
    for key in required_true:
        if network.get(key) is not True:
            fail(key)
    if network.get('file_url_navigation') is not False or network.get('unrestricted_file_access') is not False:
        fail('file access')

    provider = (r.get('providers') or {}).get('playwright-mcp')
    adapter = (r.get('adapters') or {}).get('playwright-mcp-adapter')
    if provider != {'adapter':'playwright-mcp-adapter','kind':'mcp','execution':'external'}:
        fail('dedicated provider binding')
    if not isinstance(adapter, dict) or adapter.get('status') != 'DESIGNED':
        fail('adapter design status')
    if adapter.get('executable') not in {None, ''} or adapter.get('supports') != ['read']:
        fail('adapter permissions')
    if (r.get('providers') or {}).get('playwright', {}).get('adapter') == 'playwright-mcp-adapter':
        fail('project Playwright runner must remain isolated')

    entry = (catalog.get('providers') or {}).get('playwright-mcp')
    if not isinstance(entry, dict):
        fail('catalog entry')
    if entry.get('decision') != 'ASSESS' or entry.get('runtime_status') != 'CATALOG_ONLY':
        fail('catalog must remain catalog-only during design')
    if entry.get('integration_mode') != 'local-mcp' or entry.get('risk_class') != 'MEDIUM':
        fail('catalog classification')

    admission = c.get('admission', {})
    if admission.get('automatic_promotion') is not False:
        fail('automatic promotion')
    if admission.get('runtime_call_allowed_at_design_stage') is not False:
        fail('runtime call')
    if admission.get('browser_download_allowed_at_design_stage') is not False:
        fail('browser download')
    if admission.get('next_transition') != 'DESIGNED->CONTRACT_OK':
        fail('next transition')

    print('PLAYWRIGHT_MCP_DESIGN_VALID: status=DESIGNED catalog=CATALOG_ONLY runtime=false vps_install=false pilot=github-actions-ephemeral')


if __name__ == '__main__':
    main()
