#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'config' / 'mcp-chrome-devtools-contract.v1.json'
REGISTRY = ROOT / 'config' / 'provider-adapters.v1.json'
CATALOG = ROOT / 'config' / 'mcp-provider-catalog.v1.json'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fail(msg):
    raise SystemExit(f'CHROME_DEVTOOLS_MCP_DESIGN_INVALID: {msg}')


def main():
    c = load(CONTRACT)
    r = load(REGISTRY)
    catalog = load(CATALOG)

    if c.get('schema') != 'chacha.dev/mcp-chrome-devtools-contract/v1':
        fail('schema')
    if c.get('provider_id') != 'chrome-devtools-mcp' or c.get('adapter_id') != 'chrome-devtools-mcp-adapter':
        fail('identity')
    if c.get('decision') != 'ASSESS' or c.get('runtime_status') != 'DESIGNED':
        fail('design status')

    upstream = c.get('upstream', {})
    if upstream.get('package') != 'chrome-devtools-mcp':
        fail('package')
    if upstream.get('design_reference_version') != '1.9.0':
        fail('design reference version')
    if upstream.get('runtime_must_pin_exact_version') is not True:
        fail('version pinning')
    if upstream.get('technology_radar_tracks_releases') is not True:
        fail('technology radar')

    execution = c.get('execution', {})
    if execution.get('pilot_surface') != 'github-actions-ephemeral' or execution.get('execution') != 'external':
        fail('pilot execution surface')
    required_true = ('isolated_session_required', 'headless', 'launch_new_isolated_browser_only')
    for key in required_true:
        if execution.get(key) is not True:
            fail(key)
    required_false = (
        'vps_install_allowed_at_design_stage', 'persistent_profile', 'attach_existing_browser_allowed',
        'auto_connect_allowed', 'browser_url_allowed', 'websocket_endpoint_allowed',
        'authenticated_user_profile_allowed', 'production_target_allowed', 'accept_insecure_certs'
    )
    for key in required_false:
        if execution.get(key) is not False:
            fail(key)

    protocol = c.get('protocol', {})
    if protocol.get('transport') != 'stdio':
        fail('transport')
    if protocol.get('dev_hub_input') != 'chacha.dev/dispatch-envelope/v1' or protocol.get('dev_hub_output') != 'chacha.dev/task-result/v1':
        fail('DEV HUB boundary')
    if protocol.get('provider_result_trust') != 'UNVERIFIED':
        fail('provider trust')
    if protocol.get('verification_broker_required') is not True or protocol.get('producer_must_not_self_verify') is not True:
        fail('verification separation')
    if protocol.get('dev_hub_preferred_protocol_version') != '2026-07-28':
        fail('DEV HUB protocol baseline')
    if protocol.get('generic_legacy_fallback') is not False or protocol.get('runtime_protocol_probe_required_before_pilot') is not True:
        fail('protocol compatibility policy')

    hardening = c.get('runtime_hardening', {})
    flags = set(hardening.get('required_flags', []))
    required_flags = {
        '--headless=true', '--isolated=true', '--no-javascript-evaluation',
        '--no-performance-crux', '--no-usage-statistics', '--redact-network-headers'
    }
    if not required_flags.issubset(flags):
        fail('runtime hardening flags')
    if hardening.get('allow_unrestricted_paths') is not False or hardening.get('filesystem_root_must_be_ephemeral') is not True:
        fail('filesystem hardening')
    if hardening.get('page_id_routing_required') is not True or hardening.get('source_maps') is not False:
        fail('page routing/source maps')
    for key in (
        'extensions_category', 'experimental_third_party_category', 'pwa_category',
        'experimental_devtools', 'experimental_vision', 'memory_debugging', 'experimental_screencast'
    ):
        if hardening.get(key) is not False:
            fail(f'{key} must be false')

    tools = c.get('tool_policy', {})
    allowed = set(tools.get('design_allow', []))
    expected_allowed = {
        'list_pages', 'take_snapshot', 'take_screenshot', 'list_console_messages',
        'get_console_message', 'list_network_requests', 'get_network_request'
    }
    if allowed != expected_allowed:
        fail('design allowlist')
    denied = set(tools.get('explicit_deny', []))
    must_deny = {
        'evaluate_script', 'click', 'fill', 'type_text', 'upload_file', 'navigate_page',
        'new_page', 'performance_start_trace', 'lighthouse_audit'
    }
    if not must_deny.issubset(denied):
        fail('unsafe or mutating tools not denied')
    if tools.get('default') != 'DENY' or tools.get('filename_argument_for_read_tools') != 'DENY':
        fail('default/file argument deny')
    for key in ('javascript_evaluation', 'file_upload', 'form_submission', 'browser_interaction',
                'workspace_write', 'repository_write', 'production_mutation'):
        if tools.get(key) is not False:
            fail(f'{key} must be false')

    network = c.get('network_policy', {})
    if network.get('test_or_preview_origins_only') is not True or network.get('allowed_url_patterns_required_at_runtime') is not True:
        fail('network origin policy')
    if network.get('network_headers_redacted') is not True or network.get('request_or_response_body_capture_default') != 'DENY':
        fail('network redaction/body policy')
    if network.get('authorization_header_in_evidence') != 'REDACT' or network.get('cookie_header_in_evidence') != 'REDACT':
        fail('credential redaction')

    provider = (r.get('providers') or {}).get('chrome-devtools-mcp')
    adapter = (r.get('adapters') or {}).get('chrome-devtools-mcp-adapter')
    if provider != {'adapter': 'chrome-devtools-mcp-adapter', 'kind': 'mcp', 'execution': 'external'}:
        fail('dedicated provider binding')
    if not isinstance(adapter, dict) or adapter.get('status') != 'DESIGNED':
        fail('adapter design status')
    if adapter.get('executable') not in {None, ''} or adapter.get('supports') != ['read']:
        fail('adapter permissions')

    entry = (catalog.get('providers') or {}).get('chrome-devtools-mcp')
    if not isinstance(entry, dict):
        fail('catalog entry')
    if entry.get('decision') != 'ASSESS' or entry.get('runtime_status') != 'CATALOG_ONLY':
        fail('catalog must remain CATALOG_ONLY during design')
    if entry.get('integration_mode') != 'local-mcp' or entry.get('risk_class') != 'MEDIUM':
        fail('catalog classification')

    admission = c.get('admission', {})
    if admission.get('automatic_promotion') is not False:
        fail('automatic promotion')
    if admission.get('runtime_call_allowed_at_design_stage') is not False:
        fail('runtime call at design')
    if admission.get('browser_download_allowed_at_design_stage') is not False:
        fail('browser download at design')
    if admission.get('next_transition') != 'DESIGNED->CONTRACT_OK':
        fail('next transition')

    print('CHROME_DEVTOOLS_MCP_DESIGN_VALID: status=DESIGNED catalog=CATALOG_ONLY runtime=false attach_existing=false js=false write=false')


if __name__ == '__main__':
    main()
