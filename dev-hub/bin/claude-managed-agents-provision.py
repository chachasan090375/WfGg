#!/usr/bin/env python3
"""Provision the least-privilege Anthropic resources required by the Claude PILOT.

Default mode is PLAN ONLY. Live resource creation requires explicit --apply plus
external environment references. Credential values are never written to output.
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


def main() -> int:
    parser = argparse.ArgumentParser(description='Provision Claude Managed Agents PILOT resources')
    parser.add_argument('--apply', action='store_true', help='Explicitly create remote Anthropic resources')
    parser.add_argument('--output', type=Path, default=Path('/tmp/claude-managed-agents-provisioning.json'))
    args = parser.parse_args()

    pilot = load(PILOT)
    toolset = pilot.get('toolset') or {}
    environment_cfg = pilot.get('environment') or {}
    model_ref_present = 'CHACHA_ANTHROPIC_MODEL_ID' in os.environ
    credential_ref_present = 'ANTHROPIC_API_KEY' in os.environ

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
        'agent': {
            'name': 'ChaCha DEV HUB read-only PILOT',
            'model_source': 'CHACHA_ANTHROPIC_MODEL_ID',
            'toolset': toolset,
            'mcp_servers': [],
            'skills': [],
            'multiagent': None,
        },
        'environment': {
            'name': 'ChaCha DEV HUB read-only PILOT environment',
            'config': environment_cfg,
        },
        'created': False,
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
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    blockers: list[str] = []
    if not credential_ref_present:
        blockers.append('MISSING_EXTERNAL_REFERENCE:ANTHROPIC_API_KEY')
    if not model_ref_present:
        blockers.append('MISSING_EXTERNAL_REFERENCE:CHACHA_ANTHROPIC_MODEL_ID')
    if pilot.get('api_beta') != BETA:
        blockers.append('API_BETA_MISMATCH')
    if (toolset.get('default_config') or {}).get('enabled') is not False:
        blockers.append('TOOLSET_DEFAULT_NOT_DISABLED')
    network = (environment_cfg.get('networking') or {}) if isinstance(environment_cfg, dict) else {}
    if environment_cfg.get('type') != 'cloud':
        blockers.append('ENVIRONMENT_NOT_CLOUD')
    if network.get('type') != 'limited' or network.get('allowed_hosts') != []:
        blockers.append('ENVIRONMENT_NETWORK_NOT_LOCKED')
    if network.get('allow_mcp_servers') is not False or network.get('allow_package_managers') is not False:
        blockers.append('ENVIRONMENT_NETWORK_EXCEPTIONS_ENABLED')

    if blockers:
        plan['status'] = 'BLOCKED'
        plan['blockers'] = blockers
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 2

    try:
        from anthropic import Anthropic
    except Exception as exc:
        plan['status'] = 'BLOCKED'
        plan['blockers'] = [f'ANTHROPIC_SDK_UNAVAILABLE:{type(exc).__name__}']
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 2

    # Value is required by the remote API but is never copied into the receipt.
    model_id = os.environ['CHACHA_ANTHROPIC_MODEL_ID']
    client = Anthropic()
    environment_id: str | None = None
    agent_id: str | None = None

    try:
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
            metadata={'owner': 'chacha-dev-hub', 'purpose': 'readonly-pilot'},
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
            tools=[toolset],
            mcp_servers=[],
            metadata={'owner': 'chacha-dev-hub', 'purpose': 'readonly-pilot'},
            betas=[BETA],
        )
        agent_id = str(agent.id)
        agent_version = int(agent.version)

        # Retrieve both resources before declaring provisioning success.
        verified_agent = as_dict(client.beta.agents.retrieve(agent_id, version=agent_version, betas=[BETA]))
        verified_env = as_dict(client.beta.environments.retrieve(environment_id, betas=[BETA]))
        if not isinstance(verified_agent, dict) or not isinstance(verified_env, dict):
            raise RuntimeError('PROVISIONED_RESOURCE_RETRIEVAL_INVALID')

        plan.update({
            'status': 'PROVISIONED',
            'created': True,
            'agent_id': agent_id,
            'agent_version': agent_version,
            'environment_id': environment_id,
            'model_id': (verified_agent.get('model') or {}).get('id') if isinstance(verified_agent.get('model'), dict) else None,
            'blockers': [],
            'next_action': 'store-safe-resource-identifiers-and-run-pilot-preflight',
        })
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    except Exception as exc:
        cleanup: list[str] = []
        if agent_id:
            try:
                client.beta.agents.archive(agent_id, betas=[BETA])
                cleanup.append('agent_archived')
            except Exception:
                cleanup.append('agent_archive_failed')
        if environment_id:
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
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
