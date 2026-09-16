#!/usr/bin/env python3
"""Provision the least-privilege Anthropic resources required by the Claude PILOT.

Default mode is PLAN ONLY. Live resource creation requires explicit --apply plus
external environment references. Credential values are never written to output.
A provision request ID makes re-runs idempotent: the same request reuses its
existing Agent+Environment pair instead of creating duplicates.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / 'config' / 'claude-managed-agents-pilot.v1.json'
BETA = 'managed-agents-2026-04-01'
ALLOWED = {'read', 'glob', 'grep'}
DENIED = {'bash', 'write', 'edit', 'web_fetch', 'web_search'}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise SystemExit(f'JSON_ROOT_NOT_OBJECT={path}')
    return value


def as_dict(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return value


def page_items(page: Any) -> list[Any]:
    data = getattr(page, 'data', None)
    if data is None and isinstance(page, dict):
        data = page.get('data')
    return list(data or [])


def api_toolset_from_contract(toolset: dict[str, Any]) -> dict[str, Any]:
    """Strip DEV HUB-only expectation fields before sending to Anthropic."""
    return {
        'type': toolset.get('type'),
        'default_config': toolset.get('default_config'),
        'configs': toolset.get('configs'),
    }


def validate_toolset(toolset: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if toolset.get('type') != 'agent_toolset_20260401':
        blockers.append('TOOLSET_TYPE_INVALID')
    if (toolset.get('default_config') or {}).get('enabled') is not False:
        blockers.append('TOOLSET_DEFAULT_NOT_DISABLED')
    configs = toolset.get('configs') if isinstance(toolset.get('configs'), list) else []
    by_name = {x.get('name'): x for x in configs if isinstance(x, dict) and isinstance(x.get('name'), str)}
    for name in ALLOWED:
        item = by_name.get(name) or {}
        if item.get('enabled') is not True or (item.get('permission_policy') or {}).get('type') != 'always_allow':
            blockers.append(f'READ_TOOL_INVALID:{name}')
    for name in DENIED:
        if (by_name.get(name) or {}).get('enabled') is not False:
            blockers.append(f'DANGEROUS_TOOL_NOT_DISABLED:{name}')
    if set(by_name) != ALLOWED | DENIED:
        blockers.append('UNEXPECTED_TOOL_CONFIG_PRESENT')
    return blockers


def validate_environment_config(config: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    network = (config.get('networking') or {}) if isinstance(config, dict) else {}
    if config.get('type') != 'cloud':
        blockers.append('ENVIRONMENT_NOT_CLOUD')
    if network.get('type') != 'limited' or network.get('allowed_hosts') not in (None, []):
        blockers.append('ENVIRONMENT_NETWORK_NOT_LOCKED')
    if network.get('allow_mcp_servers') not in (None, False):
        blockers.append('ENVIRONMENT_MCP_NETWORK_ENABLED')
    if network.get('allow_package_managers') not in (None, False):
        blockers.append('ENVIRONMENT_PACKAGE_MANAGER_NETWORK_ENABLED')
    return blockers


def configured_remote_toolset(agent: dict[str, Any]) -> dict[str, Any] | None:
    for item in agent.get('tools') or []:
        if isinstance(item, dict) and item.get('type') == 'agent_toolset_20260401':
            return item
    return None


def existing_resource_blockers(agent: dict[str, Any], environment: dict[str, Any], model_id: str) -> list[str]:
    blockers: list[str] = []
    remote_model = agent.get('model') or {}
    remote_model_id = remote_model.get('id') if isinstance(remote_model, dict) else None
    if remote_model_id != model_id:
        blockers.append(f'IDEMPOTENT_AGENT_MODEL_MISMATCH:{remote_model_id}')
    if agent.get('mcp_servers') not in (None, []):
        blockers.append('IDEMPOTENT_AGENT_HAS_MCP_SERVERS')
    toolset = configured_remote_toolset(agent)
    if not isinstance(toolset, dict):
        blockers.append('IDEMPOTENT_AGENT_TOOLSET_MISSING')
    else:
        blockers.extend('IDEMPOTENT_' + x for x in validate_toolset(toolset))
    env_cfg = environment.get('config') or {}
    blockers.extend('IDEMPOTENT_' + x for x in validate_environment_config(env_cfg))
    return blockers


def metadata_matches(value: Any, request_id: str) -> bool:
    item = as_dict(value)
    if not isinstance(item, dict):
        return False
    metadata = item.get('metadata') or {}
    return (
        isinstance(metadata, dict)
        and metadata.get('owner') == 'chacha-dev-hub'
        and metadata.get('purpose') == 'readonly-pilot'
        and metadata.get('provision_request_id') == request_id
    )


def write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Provision Claude Managed Agents PILOT resources')
    parser.add_argument('--apply', action='store_true', help='Explicitly create remote Anthropic resources')
    parser.add_argument('--output', type=Path, default=Path('/tmp/claude-managed-agents-provisioning.json'))
    args = parser.parse_args()

    pilot = load(PILOT)
    contract_toolset = pilot.get('toolset') or {}
    api_toolset = api_toolset_from_contract(contract_toolset)
    environment_cfg = pilot.get('environment') or {}
    model_ref_present = 'CHACHA_ANTHROPIC_MODEL_ID' in os.environ
    credential_ref_present = 'ANTHROPIC_API_KEY' in os.environ
    request_ref_present = 'CHACHA_ANTHROPIC_PROVISION_REQUEST_ID' in os.environ

    plan = {
        'schema': 'chacha.dev/claude-managed-agents-provisioning/v1',
        'provider': 'anthropic-claude',
        'adapter': 'claude-agent-adapter',
        'runtime_surface': 'claude-managed-agents',
        'api_beta': BETA,
        'mode': 'APPLY' if args.apply else 'PLAN_ONLY',
        'credential_value_observed': False,
        'credential_reference_present': credential_ref_present,
        'model_reference_present': model_ref_present,
        'provision_request_reference_present': request_ref_present,
        'provision_request_id': os.environ.get('CHACHA_ANTHROPIC_PROVISION_REQUEST_ID') if request_ref_present else None,
        'agent': {
            'name': 'ChaCha DEV HUB read-only PILOT',
            'model_source': 'CHACHA_ANTHROPIC_MODEL_ID',
            'api_toolset': api_toolset,
            'expected_enabled_tools': contract_toolset.get('expected_enabled_tools') or [],
            'expected_disabled_tools': contract_toolset.get('expected_disabled_tools') or [],
            'mcp_servers': [],
        },
        'environment': {
            'name': 'ChaCha DEV HUB read-only PILOT environment',
            'config': environment_cfg,
        },
        'created': False,
        'reused': False,
        'agent_id': None,
        'agent_version': None,
        'environment_id': None,
        'rollback_on_partial_failure': True,
        'observed_at': now_iso(),
    }

    # No API import, no credential access and no network in default plan mode.
    if not args.apply:
        plan['status'] = 'PLAN_ONLY'
        plan['blockers'] = []
        write_receipt(args.output, plan)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    blockers: list[str] = []
    if not credential_ref_present:
        blockers.append('MISSING_EXTERNAL_REFERENCE:ANTHROPIC_API_KEY')
    if not model_ref_present:
        blockers.append('MISSING_EXTERNAL_REFERENCE:CHACHA_ANTHROPIC_MODEL_ID')
    if not request_ref_present:
        blockers.append('MISSING_EXTERNAL_REFERENCE:CHACHA_ANTHROPIC_PROVISION_REQUEST_ID')
    if pilot.get('api_beta') != BETA:
        blockers.append('API_BETA_MISMATCH')
    blockers.extend(validate_toolset(api_toolset))
    blockers.extend(validate_environment_config(environment_cfg))

    if blockers:
        plan['status'] = 'BLOCKED'
        plan['blockers'] = sorted(set(blockers))
        write_receipt(args.output, plan)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 2

    try:
        from anthropic import Anthropic
    except Exception as exc:
        plan['status'] = 'BLOCKED'
        plan['blockers'] = [f'ANTHROPIC_SDK_UNAVAILABLE:{type(exc).__name__}']
        write_receipt(args.output, plan)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 2

    model_id = os.environ['CHACHA_ANTHROPIC_MODEL_ID']
    request_id = os.environ['CHACHA_ANTHROPIC_PROVISION_REQUEST_ID']
    client = Anthropic()
    environment_id: str | None = None
    agent_id: str | None = None

    try:
        # Idempotence: same request ID must map to zero or exactly one Agent+Environment pair.
        agent_page = client.beta.agents.list(limit=100, betas=[BETA])
        env_page = client.beta.environments.list(limit=1000, betas=[BETA])
        existing_agents = [as_dict(x) for x in page_items(agent_page) if metadata_matches(x, request_id)]
        existing_envs = [as_dict(x) for x in page_items(env_page) if metadata_matches(x, request_id)]

        if len(existing_agents) > 1 or len(existing_envs) > 1:
            plan.update({
                'status': 'BLOCKED',
                'blockers': ['DUPLICATE_EXISTING_RESOURCES_FOR_REQUEST'],
                'existing_agent_count': len(existing_agents),
                'existing_environment_count': len(existing_envs),
            })
            write_receipt(args.output, plan)
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 2

        if bool(existing_agents) != bool(existing_envs):
            plan.update({
                'status': 'BLOCKED',
                'blockers': ['PARTIAL_EXISTING_RESOURCES_FOR_REQUEST'],
                'existing_agent_id': existing_agents[0].get('id') if existing_agents else None,
                'existing_environment_id': existing_envs[0].get('id') if existing_envs else None,
            })
            write_receipt(args.output, plan)
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 2

        if existing_agents and existing_envs:
            existing_agent = existing_agents[0]
            existing_env = existing_envs[0]
            agent_id = str(existing_agent.get('id'))
            environment_id = str(existing_env.get('id'))
            agent_version = int(existing_agent.get('version'))
            verified_agent = as_dict(client.beta.agents.retrieve(agent_id, version=agent_version, betas=[BETA]))
            verified_env = as_dict(client.beta.environments.retrieve(environment_id, betas=[BETA]))
            if not isinstance(verified_agent, dict) or not isinstance(verified_env, dict):
                raise RuntimeError('IDEMPOTENT_RESOURCE_RETRIEVAL_INVALID')
            policy_blockers = existing_resource_blockers(verified_agent, verified_env, model_id)
            if policy_blockers:
                plan.update({'status': 'BLOCKED', 'blockers': policy_blockers})
                write_receipt(args.output, plan)
                print(json.dumps(plan, indent=2, ensure_ascii=False))
                return 2
            remote_model = verified_agent.get('model') or {}
            plan.update({
                'status': 'PROVISIONED_REUSED',
                'created': False,
                'reused': True,
                'agent_id': agent_id,
                'agent_version': agent_version,
                'environment_id': environment_id,
                'model_id': remote_model.get('id') if isinstance(remote_model, dict) else None,
                'blockers': [],
                'next_action': 'run-pilot-preflight-and-runtime-probe',
            })
            write_receipt(args.output, plan)
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0

        metadata = {
            'owner': 'chacha-dev-hub',
            'purpose': 'readonly-pilot',
            'provision_request_id': request_id,
        }
        env = client.beta.environments.create(
            name='ChaCha DEV HUB read-only PILOT environment',
            description='Sandbox-only Claude qualification environment; no outbound hosts, MCP, packages or production access.',
            config={
                'type': 'cloud',
                'networking': {
                    'type': 'limited',
                    'allowed_hosts': [],
                    'allow_mcp_servers': False,
                    'allow_package_managers': False,
                },
            },
            metadata=metadata,
            betas=[BETA],
        )
        environment_id = str(env.id)

        agent = client.beta.agents.create(
            name='ChaCha DEV HUB read-only PILOT',
            description='Read-only Claude qualification agent controlled by ChaCha DEV HUB.',
            model=model_id,
            system=(
                'You are a read-only qualification agent. Use only read, glob, and grep. '
                'Never execute shell commands, write or edit files, access the web, use MCP, '
                'or attempt any production or repository mutation.'
            ),
            tools=[api_toolset],
            mcp_servers=[],
            metadata=metadata,
            betas=[BETA],
        )
        agent_id = str(agent.id)
        agent_version = int(agent.version)

        verified_agent = as_dict(client.beta.agents.retrieve(agent_id, version=agent_version, betas=[BETA]))
        verified_env = as_dict(client.beta.environments.retrieve(environment_id, betas=[BETA]))
        if not isinstance(verified_agent, dict) or not isinstance(verified_env, dict):
            raise RuntimeError('PROVISIONED_RESOURCE_RETRIEVAL_INVALID')
        policy_blockers = existing_resource_blockers(verified_agent, verified_env, model_id)
        if policy_blockers:
            raise RuntimeError('PROVISIONED_RESOURCE_POLICY_MISMATCH:' + ','.join(policy_blockers))

        remote_model = verified_agent.get('model') or {}
        plan.update({
            'status': 'PROVISIONED',
            'created': True,
            'reused': False,
            'agent_id': agent_id,
            'agent_version': agent_version,
            'environment_id': environment_id,
            'model_id': remote_model.get('id') if isinstance(remote_model, dict) else None,
            'blockers': [],
            'next_action': 'run-pilot-preflight-and-runtime-probe',
        })
        write_receipt(args.output, plan)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    except Exception as exc:
        cleanup: list[str] = []
        # Only roll back resources created during this invocation. Reused resources are never deleted here.
        if agent_id and not plan.get('reused'):
            try:
                client.beta.agents.archive(agent_id, betas=[BETA])
                cleanup.append('agent_archived')
            except Exception:
                cleanup.append('agent_archive_failed')
        if environment_id and not plan.get('reused'):
            try:
                client.beta.environments.delete(environment_id, betas=[BETA])
                cleanup.append('environment_deleted')
            except Exception:
                cleanup.append('environment_delete_failed')
        plan.update({
            'status': 'FAILED',
            'created': False,
            'blockers': [f'PROVISIONING_EXCEPTION:{type(exc).__name__}'],
            'partial_failure_cleanup': cleanup,
        })
        write_receipt(args.output, plan)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
