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
    if toolset.get('type') != 'agent_toolset_20260401':
        blockers.append('TOOLSET_TYPE_INVALID')
    if default_cfg.get('enabled') is not False:
        blockers.append('TOOLSET_DEFAULT_NOT_DENY')
    if set(toolset.get('enabled_tools') or []) != {'read', 'glob', 'grep'}:
        blockers.append('TOOL_ALLOWLIST_INVALID')
    if not {'bash', 'write', 'edit', 'web_fetch', 'web_search'}.issubset(set(toolset.get('disabled_tools') or [])):
        blockers.append('DANGEROUS_TOOLS_NOT_DISABLED')

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

    runtime = pilot.get('runtime_probe') or {}
    for key in ('repository_write', 'workspace_write', 'production_mutation', 'mcp_allowed', 'web_allowed', 'shell_allowed'):
        if runtime.get(key) is not False:
            blockers.append(f'RUNTIME_BOUNDARY_OPEN:{key}')
    if runtime.get('sandbox_only') is not True:
        blockers.append('SANDBOX_NOT_REQUIRED')
    if runtime.get('expected_result_schema') != 'chacha.dev/task-result/v1':
        blockers.append('RESULT_SCHEMA_INVALID')
    if runtime.get('expected_verification_status') != 'UNVERIFIED':
        blockers.append('VERIFICATION_STATUS_INVALID')

    exposed = provider_capabilities(capabilities, 'anthropic-claude')
    if exposed != {'code-review', 'documentation'}:
        blockers.append('CAPABILITY_EXPOSURE_INVALID:' + ','.join(sorted(exposed)))
    if 'code-edit' in exposed:
        blockers.append('CODE_EDIT_EXPOSED')

    missing_external = [name for name in REQUIRED_EXTERNAL if not os.environ.get(name)]
    credential_name_present = bool(os.environ.get('ANTHROPIC_API_KEY'))
    provisioning_missing = [name for name in REQUIRED_EXTERNAL[1:] if not os.environ.get(name)]

    static_blockers = [b for b in blockers if not b.startswith('EXTERNAL_')]
    if static_blockers:
        status = 'BLOCKED_STATIC_CONTRACT'
    elif not credential_name_present:
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
        'credential_reference_present': credential_name_present,
        'external_binding_presence': {
            name: bool(os.environ.get(name))
            for name in REQUIRED_EXTERNAL[1:]
        },
        'missing_external_references': missing_external,
        'static_blockers': sorted(static_blockers),
        'promotion_eligible': False,
        'automatic_promotion': False,
        'next_action': (
            'fix-static-contract' if static_blockers else
            'configure-external-auth-reference' if not credential_name_present else
            'provision-managed-agent-and-environment' if provisioning_missing else
            'run-provider-specific-runtime-probe'
        ),
        'observed_at': now_iso(),
    }

    out_path = Path(os.environ.get('CLAUDE_PILOT_PREFLIGHT_OUTPUT', '/tmp/claude-pilot-preflight.json'))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(output, indent=2, ensure_ascii=False))

    # Static contract validity is the only CI success criterion for preparation.
    return 0 if not static_blockers else 2


if __name__ == '__main__':
    raise SystemExit(main())
