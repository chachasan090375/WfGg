#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config' / 'claude-agent-adapter.v1.json'
REGISTRY = ROOT / 'config' / 'provider-adapters.v1.json'
CAPABILITIES = ROOT / 'config' / 'capability-registry.v1.json'
EVIDENCE = ROOT / 'evidence' / 'claude-contract-ok-2026-09-16.json'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fail(msg):
    raise SystemExit(f'CLAUDE_CONTRACT_OK_INVALID: {msg}')


def provider_entries(capabilities, provider_id):
    out = []
    for capability, item in capabilities.get('capabilities', {}).items():
        for provider in item.get('providers', []):
            if provider.get('id') == provider_id:
                out.append((capability, provider))
    return out


def main():
    cfg = load(CONFIG)
    reg = load(REGISTRY)
    cap = load(CAPABILITIES)
    ev = load(EVIDENCE)

    if cfg.get('schema') != 'chacha.dev/claude-agent-adapter/v1':
        fail('config schema')
    if cfg.get('provider_id') != 'anthropic-claude' or cfg.get('adapter_id') != 'claude-agent-adapter':
        fail('identity')
    if cfg.get('decision') != 'ASSESS' or cfg.get('runtime_status') != 'CONTRACT_OK':
        fail('qualification status')

    integration = cfg.get('integration', {})
    if integration.get('primary_surface') != 'anthropic-provider-abstraction':
        fail('provider abstraction')
    if integration.get('preferred_runtime') != 'claude-managed-agents':
        fail('preferred runtime')
    if integration.get('compatibility_runtime') != 'claude-agent-sdk':
        fail('compatibility runtime')
    if integration.get('execution') != 'external':
        fail('execution')
    if integration.get('mcp_server_mode') != 'SECONDARY_OPTIONAL' or integration.get('github_action_mode') != 'NOT_PRIMARY':
        fail('secondary transports')

    q = cfg.get('contract_qualification', {})
    if q.get('transition') != 'DESIGNED->CONTRACT_OK':
        fail('transition')
    if q.get('static_contract_pass_required') is not True:
        fail('static contract requirement')
    if q.get('runtime_executed') is not False or q.get('credential_used') is not False:
        fail('runtime or credential claim')
    if q.get('write_surface_expanded') is not False or q.get('automatic_promotion') is not False:
        fail('write expansion or automatic promotion')

    admission = cfg.get('admission', {})
    if admission.get('next_transition') != 'CONTRACT_OK->PILOT':
        fail('next transition')
    if admission.get('automatic_promotion') is not False or admission.get('production_change_allowed') is not False:
        fail('admission policy')

    tools = cfg.get('tool_policy', {})
    if tools.get('default') != 'DENY':
        fail('tool default')
    if set(tools.get('design_stage_allow', [])) != {'Read', 'Glob', 'Grep'}:
        fail('allowlist changed')
    if not {'Bash', 'Edit', 'Write'}.issubset(set(tools.get('design_stage_deny', []))):
        fail('dangerous tools not denied')
    for key in ('arbitrary_shell', 'workspace_write', 'repository_write', 'production_mutation', 'destructive_operations'):
        if tools.get(key) is not False:
            fail(f'{key} must remain false')

    auth = cfg.get('auth', {})
    if auth.get('credential_type') != 'ANTHROPIC_EXTERNAL_CREDENTIAL':
        fail('credential type')
    if set(auth.get('supported_modes', [])) != {'API_KEY', 'WORKLOAD_IDENTITY_FEDERATION'}:
        fail('supported auth modes')
    if auth.get('pilot_initial_mode') != 'API_KEY_REFERENCE':
        fail('pilot auth mode')
    if auth.get('future_ci_preferred_mode') != 'WORKLOAD_IDENTITY_FEDERATION':
        fail('future CI auth mode')
    if auth.get('secret_policy') != 'REFERENCE_ONLY':
        fail('secret policy')
    if auth.get('secret_values_in_git') is not False or auth.get('secret_values_in_evidence') is not False:
        fail('secret material')
    if auth.get('environment_reference') != 'ANTHROPIC_API_KEY':
        fail('credential reference')

    boundary = cfg.get('boundary', {})
    if boundary.get('provider_result_trust') != 'UNVERIFIED':
        fail('result trust')
    if boundary.get('verification_broker_required') is not True or boundary.get('producer_must_not_self_verify') is not True:
        fail('verification separation')

    provider = reg.get('providers', {}).get('anthropic-claude')
    adapter = reg.get('adapters', {}).get('claude-agent-adapter')
    if provider != {'adapter': 'claude-agent-adapter', 'kind': 'ai-agent', 'execution': 'external'}:
        fail('provider binding')
    if not isinstance(adapter, dict) or adapter.get('status') != 'CONTRACT_OK':
        fail('adapter status')
    if adapter.get('executable') not in {None, ''}:
        fail('external adapter must not bind local executable')
    if adapter.get('supports') != ['read', 'plan']:
        fail('permissions expanded')

    entries = provider_entries(cap, 'anthropic-claude')
    if {name for name, _ in entries} != {'code-review', 'documentation'}:
        fail('capability exposure')
    for name, entry in entries:
        if entry.get('status') != 'ASSESS':
            fail(f'{name} status')
        if entry.get('health') != 'runtime-not-qualified':
            fail(f'{name} health')
        if entry.get('scope') != 'read-only-workspace':
            fail(f'{name} scope')
        if entry.get('fallback') != []:
            fail(f'{name} must not be active fallback')

    code_edit = {p.get('id') for p in cap.get('capabilities', {}).get('code-edit', {}).get('providers', [])}
    if 'anthropic-claude' in code_edit:
        fail('Claude entered code-edit before write qualification')

    if ev.get('schema') != 'chacha.dev/ai-agent-contract-qualification-evidence/v1':
        fail('evidence schema')
    if ev.get('provider') != 'anthropic-claude' or ev.get('adapter') != 'claude-agent-adapter':
        fail('evidence identity')
    if ev.get('transition') != 'DESIGNED->CONTRACT_OK':
        fail('evidence transition')
    source = ev.get('source', {})
    if source.get('qualified_head') != '0e33859b0c54d8d8dad4846ae60ea4e36f21d1e7':
        fail('qualified head')
    if source.get('workflow_run_id') != 35078446312 or source.get('workflow_conclusion') != 'success':
        fail('design CI evidence')
    checks = ev.get('checks', {})
    required = {
        'provider-binding', 'adapter-static-contract', 'provider-abstraction',
        'managed-agents-preferred', 'agent-sdk-compatibility-backend', 'read-plan-only',
        'no-code-edit-routing', 'default-deny-tools', 'bash-edit-write-denied',
        'external-auth-boundary', 'verification-broker-required',
        'no-production-mutation', 'no-automatic-promotion'
    }
    if set(checks) != required or any(checks[k] != 'PASS' for k in required):
        fail('static evidence')
    runtime = ev.get('runtime', {})
    if runtime.get('executed') is not False or runtime.get('credential_used') is not False:
        fail('runtime evidence must remain false')
    promotion = ev.get('promotion', {})
    if promotion.get('eligible') is not True or promotion.get('target') != 'CONTRACT_OK':
        fail('promotion eligibility')
    if promotion.get('automatic') is not False or promotion.get('blockers') != []:
        fail('promotion blockers')

    print('CLAUDE_CONTRACT_OK_VALID: provider-abstraction=true preferred=managed-agents compatibility=agent-sdk runtime=false writes=false next=PILOT')


if __name__ == '__main__':
    main()
