#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'config' / 'mcp-playwright-contract.v1.json'
REGISTRY = ROOT / 'config' / 'provider-adapters.v1.json'
CATALOG = ROOT / 'config' / 'mcp-provider-catalog.v1.json'
EVIDENCE = ROOT / 'evidence' / 'playwright-mcp-contract-ok-2026-09-16.json'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fail(msg):
    raise SystemExit(f'PLAYWRIGHT_MCP_CONTRACT_OK_INVALID: {msg}')


def main():
    c, r, catalog, ev = map(load, [CONTRACT, REGISTRY, CATALOG, EVIDENCE])
    if c.get('schema') != 'chacha.dev/mcp-playwright-contract/v1': fail('contract schema')
    if c.get('provider_id') != 'playwright-mcp' or c.get('adapter_id') != 'playwright-mcp-adapter': fail('identity')
    if c.get('runtime_status') != 'CONTRACT_OK' or c.get('decision') != 'ASSESS': fail('contract status')

    q = c.get('contract_qualification', {})
    if q.get('transition') != 'DESIGNED->CONTRACT_OK': fail('transition')
    if q.get('qualified_design_head') != 'f6ad4ef4917fa35187506f89a395dcb24d33ab87': fail('design head')
    if q.get('qualified_design_workflow_run_id') != 35081382668 or q.get('qualified_design_workflow_conclusion') != 'success': fail('design CI')
    for key in ('static_contract_pass','dedicated_adapter_binding_pass','unsafe_code_tool_denied','isolated_ephemeral_pilot_plan_pass','network_policy_defined'):
        if q.get(key) is not True: fail(key)
    for key in ('runtime_executed','browser_downloaded','vps_modified','permissions_expanded','automatic_promotion'):
        if q.get(key) is not False: fail(key)

    tools = c.get('tool_policy', {})
    if tools.get('default') != 'DENY': fail('default deny')
    if 'browser_run_code_unsafe' not in set(tools.get('explicit_deny', [])): fail('unsafe code')
    if tools.get('filename_argument_for_read_tools') != 'DENY': fail('filename writes')
    for key in ('arbitrary_javascript','file_upload','form_submission','webmcp_page_tools','workspace_write','repository_write','production_mutation'):
        if tools.get(key) is not False: fail(f'{key} open')

    adapter = (r.get('adapters') or {}).get('playwright-mcp-adapter')
    provider = (r.get('providers') or {}).get('playwright-mcp')
    if provider != {'adapter':'playwright-mcp-adapter','kind':'mcp','execution':'external'}: fail('provider binding')
    if not isinstance(adapter, dict) or adapter.get('status') != 'CONTRACT_OK': fail('adapter status')
    if adapter.get('executable') not in {None,''} or adapter.get('supports') != ['read']: fail('adapter permission/runtime')
    if (r.get('providers') or {}).get('playwright',{}).get('adapter') == 'playwright-mcp-adapter': fail('runner conflation')

    entry = (catalog.get('providers') or {}).get('playwright-mcp')
    if not isinstance(entry, dict): fail('catalog entry')
    if entry.get('runtime_status') != 'CONTRACT_OK' or entry.get('decision') != 'ASSESS': fail('catalog state')
    if entry.get('provider_binding') != 'playwright-mcp': fail('catalog binding')

    if c.get('admission', {}).get('next_transition') != 'CONTRACT_OK->PILOT': fail('next transition')
    if c.get('admission', {}).get('automatic_promotion') is not False: fail('automatic promotion')

    if ev.get('schema') != 'chacha.dev/mcp-contract-qualification-evidence/v1': fail('evidence schema')
    if ev.get('provider') != 'playwright-mcp' or ev.get('adapter') != 'playwright-mcp-adapter': fail('evidence identity')
    if ev.get('transition') != 'DESIGNED->CONTRACT_OK': fail('evidence transition')
    src = ev.get('source', {})
    if src.get('qualified_head') != 'f6ad4ef4917fa35187506f89a395dcb24d33ab87' or src.get('workflow_run_id') != 35081382668 or src.get('workflow_conclusion') != 'success': fail('evidence source')
    if any(v != 'PASS' for v in (ev.get('checks') or {}).values()): fail('evidence checks')
    runtime = ev.get('runtime', {})
    if any(runtime.get(k) is not False for k in ('executed','browser_downloaded','vps_modified','production_modified')): fail('runtime claim')
    promotion = ev.get('promotion', {})
    if promotion.get('eligible') is not True or promotion.get('target') != 'CONTRACT_OK' or promotion.get('automatic') is not False or promotion.get('blockers') != []: fail('promotion evidence')

    print('PLAYWRIGHT_MCP_CONTRACT_OK_VALID: static=true runtime=false browser=false vps=false next=PILOT')


if __name__ == '__main__':
    main()
