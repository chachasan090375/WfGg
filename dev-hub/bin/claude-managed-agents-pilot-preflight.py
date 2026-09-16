#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / 'config' / 'claude-managed-agents-pilot.v1.json'
CLAUDE = ROOT / 'config' / 'claude-agent-adapter.v1.json'
REGISTRY = ROOT / 'config' / 'provider-adapters.v1.json'
CAPABILITIES = ROOT / 'config' / 'capability-registry.v1.json'

OUTPUT_SCHEMA = 'chacha.dev/claude-managed-agents-pilot-preflight/v1'
REQUIRED_EXTERNAL = [
    'ANTHROPIC_API_KEY',
    'CHACHA_ANTHROPIC_AGENT_ID',
    'CHACHA_ANTHROPIC_ENVIRONMENT_ID',
    'CHACHA_ANTHROPIC_AGENT_VERSION',
]


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise SystemExit(f'JSON_ROOT_NOT_OBJECT={path}')
    return value


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def provider_capabilities(cap: dict[str, Any], provider_id: str) -> set[str]:
    found: set[str] = set()
    for name, item in (cap.get('capabilities') or {}).items():
        if not isinstance(item, dict):
            continue
        for provider in item.get('providers') or []:
            if isinstance(provider, dict) and provider.get('id') == provider_id:
                found.add(name)
    return found


def env_present(name: str) -> bool:
    # Presence only: never read, print, hash, serialize or compare the value.
    return name in os.environ


def main() -> int:
    pilot = load(PILOT)
    claude = load(CLAUDE)
    registry = load(REGISTRY)
    capabilities = load(CAPABILITIES)

    blockers: list[str] = []

    if pilot.get('schema') != 'chacha.dev/claude-managed-agents-pilot/v1':
        blockers.append('PILOT_SCHEMA_INVALID')
    if pilot.get('provider') != 'anthropic-claude' or pilot.get('adapter') != 'claude-agent-adapter':
        blockers.append('PILOT_IDENTITY_INVALID')
    if pilot.get('source_status') != 'CONTRACT_OK' or pilot.get('target_status') != 'PILOT':
        blockers.append('PILOT_TRANSITION_INVALID')
    if pilot.get('runtime_surface') != 'claude-managed-agents':
        blockers.append('RUNTIME_SURFACE_INVALID')
    if pilot.get('api_beta') != 'managed-agents-2026-04-01':
        blockers.append('API_BETA_INVALID')

    adapter = (registry.get('adapters') or {}).get('claude-agent-adapter')
    provider = (registry.get('providers') or {}).get('anthropic-claude')
    if provider != {'adapter': 'claude-agent-adapter', 'kind': 'ai-agent', 'execution': 'external'}:
        blockers.append('PROVIDER_BINDING_INVALID')
    if not isinstance(adapter, dict) or adapter.get('status') != 'CONTRACT_OK':
        blockers.append(f"ADAPTER_NOT_CONTRACT_OK:{None if not isinstance(adapter, dict) else adapter.get('status')}")
    else:
        if adapter.get('supports') != ['read', 'plan']:
            blockers.append('ADAPTER_PERMISSIONS_EXPANDED')
        if adapter.get('executable') not in {None, ''}:
            blockers.append('EXTERNAL_ADAPTER_BOUND_LOCAL_EXECUTABLE')

    if claude.get('runtime_status') != 'CONTRACT_OK':
        blockers.append('CLAUDE_CONFIG_NOT_CONTRACT_OK')
    if claude.get('decision') != 'ASSESS':
        blockers.append('CLAUDE_DECISION_NOT_ASSESS')

    toolset = pilot.get('toolset') or {}
    default_cfg = toolset.get('default_config') or {}
    configs = toolset.get('configs') if isinstance(toolset.get('configs'), list) else []
    config_by_name = {
        item.get('name'): item
        for item in configs
        if isinstance(item, dict) and isinstance(item.get('name'), str)
    }
    allowed = {'read', 'glob', 'grep'}
    denied = {'bash', 'write', 'edit', 'web_fetch', 'web_search'}
    if toolset.get('type') != 'agent_toolset_20260401':
        blockers.append('TOOLSET_TYPE_INVALID')
    if default_cfg.get('enabled') is not False:
        blockers.append('TOOLSET_DEFAULT_NOT_DENY')
    if set(toolset.get('expected_enabled_tools') or []) != allowed:
        blockers.append('TOOL_ALLOWLIST_DECLARATION_INVALID')
    if set(toolset.get('expected_disabled_tools') or []) != denied:
        blockers.append('TOOL_DENYLIST_DECLARATION_INVALID')
    for name in allowed:
        item = config_by_name.get(name) or {}
        if item.get('enabled') is not True:
            blockers.append(f'READ_TOOL_NOT_ENABLED:{name}')
        policy = item.get('permission_policy') or {}
        if policy.get('type') != 'always_allow':
            blockers.append(f'READ_TOOL_PERMISSION_POLICY_INVALID:{name}')
    for name in denied:
        item = config_by_name.get(name) or {}
        if item.get('enabled') is not False:
            blockers.append(f'DANGEROUS_TOOL_NOT_DISABLED:{name}')
    if set(config_by_name) != allowed | denied:
        blockers.append('UNEXPECTED_TOOL_CONFIG_PRESENT')

    environment = pilot.get('environment') or {}
    networking = environment.get('networking') or {}
    if environment.get('type') != 'cloud':
        blockers.append('ENVIRONMENT_TYPE_INVALID')
    if networking.get('type') != 'limited':
        blockers.append('NETWORK_NOT_LIMITED')
    if networking.get('allowed_hosts') != []:
        blockers.append('NETWORK_HOST_ALLOWLIST_NOT_EMPTY')
    if networking.get('allow_mcp_servers') is not False:
        blockers.append('MCP_NETWORKING_ENABLED')
    if networking.get('allow_package_managers') is not False:
        blockers.append('PACKAGE_MANAGER_NETWORKING_ENABLED')

    fixture = pilot.get('fixture') or {}
    fixture_path = ROOT.parent / str(fixture.get('source') or '')
    if not fixture_path.is_file():
        blockers.append('READONLY_FIXTURE_MISSING')
    elif 'CHACHA_CLAUDE_PILOT_READONLY_2026_09_16' not in fixture_path.read_text(encoding='utf-8'):
        blockers.append('READONLY_FIXTURE_MARKER_MISSING')
    if fixture.get('mounted_copy_expected_read_only') is not True:
        blockers.append('FIXTURE_READONLY_EXPECTATION_MISSING')

    runtime = pilot.get('runtime_probe') or {}
    for key in ('repository_write', 'workspace_write', 'production_mutation', 'mcp_allowed', 'web_allowed', 'shell_allowed'):
        if runtime.get(key) is not False:
            blockers.append(f'RUNTIME_BOUNDARY_OPEN:{key}')
    if runtime.get('sandbox_only') is not True:
        blockers.append('SANDBOX_NOT_REQUIRED')
    if runtime.get('expected_result_schema') != 'chacha.dev/task-result/v1':
        blockers.append('RESULT_SCHEMA_INVALID')
    if runtime.get('expected_task_status') != 'OK':
        blockers.append('TASK_STATUS_INVALID')
    if runtime.get('expected_verification_status') != 'UNVERIFIED':
        blockers.append('VERIFICATION_STATUS_INVALID')

    promotion = pilot.get('promotion') or {}
    if promotion.get('automatic') is not False:
        blockers.append('AUTOMATIC_PROMOTION_ENABLED')
    if set(promotion.get('required_evidence') or []) != {'runtime-contract-pass', 'sandbox-only', 'provisioning-pass'}:
        blockers.append('PROMOTION_EVIDENCE_INVALID')
    if promotion.get('registry_mutation_in_preparation_phase') is not False:
        blockers.append('PREP_REGISTRY_MUTATION_ALLOWED')

    exposed = provider_capabilities(capabilities, 'anthropic-claude')
    if exposed != {'code-review', 'documentation'}:
        blockers.append('CAPABILITY_EXPOSURE_INVALID:' + ','.join(sorted(exposed)))
    if 'code-edit' in exposed:
        blockers.append('CODE_EDIT_EXPOSED')

    missing_external = [name for name in REQUIRED_EXTERNAL if not env_present(name)]
    credential_reference_present = env_present('ANTHROPIC_API_KEY')
    provisioning_missing = [name for name in REQUIRED_EXTERNAL[1:] if not env_present(name)]

    static_blockers = sorted(set(blockers))
    if static_blockers:
        status = 'BLOCKED_STATIC_CONTRACT'
    elif not credential_reference_present:
        status = 'BLOCKED_AUTH_MISSING'
    elif provisioning_missing:
        status = 'BLOCKED_PROVISIONING_MISSING'
    else:
        status = 'READY_FOR_RUNTIME_PROBE'

    output = {
        'schema': OUTPUT_SCHEMA,
        'provider': 'anthropic-claude',
        'adapter': 'claude-agent-adapter',
        'source_status': None if not isinstance(adapter, dict) else adapter.get('status'),
        'target_status': 'PILOT',
        'status': status,
        'runtime_surface': pilot.get('runtime_surface'),
        'registry_mutated': False,
        'runtime_executed': False,
        'credential_value_observed': False,
        'credential_reference_present': credential_reference_present,
        'external_binding_presence': {
            name: env_present(name)
            for name in REQUIRED_EXTERNAL[1:]
        },
        'missing_external_references': missing_external,
        'static_blockers': static_blockers,
        'promotion_eligible': False,
        'automatic_promotion': False,
        'next_action': (
            'fix-static-contract' if static_blockers else
            'configure-external-auth-reference' if not credential_reference_present else
            'provision-managed-agent-and-environment' if provisioning_missing else
            'run-provider-specific-runtime-probe'
        ),
        'observed_at': now_iso(),
    }

    out_path = Path(os.environ.get('CLAUDE_PILOT_PREFLIGHT_OUTPUT', '/tmp/claude-pilot-preflight.json'))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(output, indent=2, ensure_ascii=False))

    # Preparation CI succeeds only when static policy is valid. Runtime readiness is separate.
    return 0 if not static_blockers else 2


if __name__ == '__main__':
    raise SystemExit(main())
