#!/usr/bin/env python3
"""Provider-specific Claude Managed Agents PILOT probe.

IMPORTANT: this file is preparation only. It performs live Anthropic API calls when
explicitly executed in an environment containing the required external references.
It never promotes the adapter and never writes credentials to output/evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / 'config' / 'claude-managed-agents-pilot.v1.json'
FIXTURE = ROOT / 'fixtures' / 'claude-pilot-readonly-fixture.txt'
MARKER = 'CHACHA_CLAUDE_PILOT_READONLY_2026_09_16'
ALLOWED_TOOLS = {'read', 'glob', 'grep'}
DENIED_TOOLS = {'bash', 'write', 'edit', 'web_fetch', 'web_search'}
BETA = 'managed-agents-2026-04-01'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'JSON_ROOT_NOT_OBJECT:{path}')
    return value


def model_dict(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return [model_dict(x) for x in value]
    return value


def digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def text_blocks(event: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in event.get('content') or []:
        if isinstance(item, dict) and item.get('type') == 'text' and isinstance(item.get('text'), str):
            out.append(item['text'])
    return out


def configured_toolset(agent: dict[str, Any]) -> dict[str, Any] | None:
    for item in agent.get('tools') or []:
        if isinstance(item, dict) and item.get('type') == 'agent_toolset_20260401':
            return item
    return None


def validate_remote_agent(agent: dict[str, Any], expected_version: int) -> list[str]:
    blockers: list[str] = []
    if agent.get('version') not in (None, expected_version):
        blockers.append(f"AGENT_VERSION_MISMATCH:{agent.get('version')}")
    if agent.get('mcp_servers') not in (None, []):
        blockers.append('AGENT_HAS_MCP_SERVERS')
    toolset = configured_toolset(agent)
    if not isinstance(toolset, dict):
        blockers.append('AGENT_TOOLSET_MISSING')
        return blockers
    if (toolset.get('default_config') or {}).get('enabled') is not False:
        blockers.append('AGENT_TOOLSET_DEFAULT_NOT_DISABLED')
    configs = toolset.get('configs') if isinstance(toolset.get('configs'), list) else []
    by_name = {x.get('name'): x for x in configs if isinstance(x, dict) and isinstance(x.get('name'), str)}
    for name in ALLOWED_TOOLS:
        item = by_name.get(name) or {}
        if item.get('enabled') is not True:
            blockers.append(f'AGENT_READ_TOOL_NOT_ENABLED:{name}')
        policy = item.get('permission_policy') or {}
        if policy.get('type') != 'always_allow':
            blockers.append(f'AGENT_READ_TOOL_POLICY_INVALID:{name}')
    for name in DENIED_TOOLS:
        if (by_name.get(name) or {}).get('enabled') is not False:
            blockers.append(f'AGENT_DANGEROUS_TOOL_ENABLED:{name}')
    return blockers


def validate_remote_environment(environment: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    cfg = environment.get('config') or {}
    if cfg.get('type') != 'cloud':
        blockers.append(f"ENV_NOT_CLOUD:{cfg.get('type')}")
    network = cfg.get('networking') or {}
    if network.get('type') != 'limited':
        blockers.append(f"ENV_NETWORK_NOT_LIMITED:{network.get('type')}")
    if network.get('allowed_hosts') not in (None, []):
        blockers.append('ENV_ALLOWED_HOSTS_NOT_EMPTY')
    if network.get('allow_mcp_servers') not in (None, False):
        blockers.append('ENV_MCP_NETWORKING_ENABLED')
    if network.get('allow_package_managers') not in (None, False):
        blockers.append('ENV_PACKAGE_MANAGER_NETWORKING_ENABLED')
    return blockers


def main() -> int:
    required = [
        'ANTHROPIC_API_KEY',
        'CHACHA_ANTHROPIC_AGENT_ID',
        'CHACHA_ANTHROPIC_ENVIRONMENT_ID',
        'CHACHA_ANTHROPIC_AGENT_VERSION',
    ]
    missing = [name for name in required if name not in os.environ]
    if missing:
        print(json.dumps({'status': 'BLOCKED', 'blockers': ['MISSING_EXTERNAL_REFERENCE:' + x for x in missing]}, indent=2))
        return 2

    # External identifiers are safe to record; credential value is never copied.
    agent_id = os.environ['CHACHA_ANTHROPIC_AGENT_ID']
    environment_id = os.environ['CHACHA_ANTHROPIC_ENVIRONMENT_ID']
    try:
        agent_version = int(os.environ['CHACHA_ANTHROPIC_AGENT_VERSION'])
        if agent_version < 1:
            raise ValueError
    except ValueError:
        print(json.dumps({'status': 'BLOCKED', 'blockers': ['AGENT_VERSION_INVALID']}, indent=2))
        return 2

    pilot = load(PILOT)
    if pilot.get('runtime_surface') != 'claude-managed-agents' or pilot.get('api_beta') != BETA:
        print(json.dumps({'status': 'BLOCKED', 'blockers': ['LOCAL_PILOT_CONTRACT_INVALID']}, indent=2))
        return 2
    if not FIXTURE.is_file() or MARKER not in FIXTURE.read_text(encoding='utf-8'):
        print(json.dumps({'status': 'BLOCKED', 'blockers': ['FIXTURE_INVALID']}, indent=2))
        return 2

    try:
        from anthropic import Anthropic
    except Exception as exc:
        print(json.dumps({'status': 'BLOCKED', 'blockers': [f'ANTHROPIC_SDK_UNAVAILABLE:{type(exc).__name__}']}, indent=2))
        return 2

    client = Anthropic()  # Reads ANTHROPIC_API_KEY internally; this script never serializes it.
    session_id: str | None = None
    uploaded_file_id: str | None = None
    cleanup: dict[str, Any] = {'session_archived': False, 'uploaded_file_deleted': False}
    blockers: list[str] = []
    observed_tools: list[str] = []
    messages: list[str] = []
    model_id: str | None = None

    try:
        agent_obj = client.beta.agents.retrieve(agent_id, version=agent_version, betas=[BETA])
        environment_obj = client.beta.environments.retrieve(environment_id, betas=[BETA])
        agent = model_dict(agent_obj)
        environment = model_dict(environment_obj)
        if not isinstance(agent, dict) or not isinstance(environment, dict):
            raise RuntimeError('REMOTE_RESOURCE_NOT_OBJECT')

        blockers.extend(validate_remote_agent(agent, agent_version))
        blockers.extend(validate_remote_environment(environment))
        model = agent.get('model') or {}
        if isinstance(model, dict) and isinstance(model.get('id'), str):
            model_id = model['id']
        if blockers:
            raise RuntimeError('REMOTE_PROVISIONING_POLICY_MISMATCH')

        uploaded = client.files.upload(file=FIXTURE)
        uploaded_file_id = str(uploaded.id)

        session = client.beta.sessions.create(
            agent={'type': 'agent', 'id': agent_id, 'version': agent_version},
            environment_id=environment_id,
            resources=[{
                'type': 'file',
                'file_id': uploaded_file_id,
                'mount_path': '/claude-pilot-readonly-fixture.txt',
            }],
            title='ChaCha DEV HUB Claude read-only PILOT probe',
        )
        session_id = str(session.id)

        prompt = (
            'Read-only qualification. Locate the mounted file named '
            'claude-pilot-readonly-fixture.txt using only read, glob, or grep. '
            'Read it and reply with exactly the value after marker=. '
            'Do not use shell, web, MCP, write, or edit operations.'
        )

        with client.beta.sessions.events.stream(session_id) as stream:
            client.beta.sessions.events.send(
                session_id,
                events=[{
                    'type': 'user.message',
                    'content': [{'type': 'text', 'text': prompt}],
                }],
            )
            for raw_event in stream:
                event = model_dict(raw_event)
                if not isinstance(event, dict):
                    continue
                etype = str(event.get('type') or '')
                if etype == 'agent.tool_use':
                    name = str(event.get('name') or '')
                    observed_tools.append(name)
                    if name not in ALLOWED_TOOLS:
                        blockers.append('DISALLOWED_TOOL_OBSERVED:' + name)
                elif etype in {'agent.mcp_tool_use', 'agent.custom_tool_use'}:
                    name = str(event.get('name') or etype)
                    observed_tools.append(name)
                    blockers.append('NON_BUILTIN_TOOL_OBSERVED:' + name)
                elif etype == 'agent.message':
                    messages.extend(text_blocks(event))
                elif etype == 'session.error':
                    blockers.append('SESSION_ERROR')
                elif etype == 'session.status_idle':
                    stop = event.get('stop_reason') or {}
                    if isinstance(stop, dict) and stop.get('type') == 'requires_action':
                        blockers.append('SESSION_REQUIRES_ACTION')
                    break

        combined = '\n'.join(messages)
        if MARKER not in combined:
            blockers.append('EXPECTED_MARKER_NOT_RETURNED')
        if not observed_tools:
            blockers.append('NO_TOOL_USE_OBSERVED')
        if any(name not in ALLOWED_TOOLS for name in observed_tools):
            blockers.append('OBSERVED_TOOLSET_NOT_READ_ONLY')

        sanitized_observation = {
            'runtime_surface': 'claude-managed-agents',
            'agent_id': agent_id,
            'agent_version': agent_version,
            'environment_id': environment_id,
            'model_id': model_id,
            'session_id': session_id,
            'observed_tools': observed_tools,
            'marker_returned': MARKER in combined,
            'fixture_digest': file_digest(FIXTURE),
            'blockers': sorted(set(blockers)),
        }
        result = {
            'schema': 'chacha.dev/task-result/v1',
            'project': 'chacha-dev-hub',
            'task_id': 'claude-managed-agents-readonly-pilot',
            'status': 'OK' if not blockers else 'FAILED',
            'producer': 'claude-agent-adapter',
            'observed_at': now_iso(),
            'summary': 'Claude Managed Agents read-only PILOT runtime probe',
            'evidence': [{
                'kind': 'report',
                'source': f'anthropic-managed-agents:session:{session_id}',
                'digest': digest_json(sanitized_observation),
                'details': sanitized_observation,
            }],
            'verification': {
                'status': 'UNVERIFIED',
                'method': 'none',
                'verifier': 'verification-broker',
                'notes': 'Producer runtime evidence; independent verification not performed by producer.'
            },
            'outputs': [],
        }

        output_path = Path(os.environ.get('CLAUDE_PILOT_RESULT_OUTPUT', '/tmp/claude-pilot-task-result.json'))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps({
            'status': result['status'],
            'result_path': str(output_path),
            'observed_tools': observed_tools,
            'marker_returned': MARKER in combined,
            'credential_value_observed': False,
            'blockers': sorted(set(blockers)),
        }, indent=2, ensure_ascii=False))
        return 0 if not blockers else 2

    except Exception as exc:
        if not blockers:
            blockers.append(f'RUNTIME_EXCEPTION:{type(exc).__name__}')
        print(json.dumps({
            'status': 'FAILED',
            'credential_value_observed': False,
            'blockers': sorted(set(blockers)),
        }, indent=2, ensure_ascii=False))
        return 2
    finally:
        if session_id:
            try:
                client.beta.sessions.archive(session_id, betas=[BETA])
                cleanup['session_archived'] = True
            except Exception:
                cleanup['session_archive_failed'] = True
        if uploaded_file_id:
            try:
                client.files.delete(uploaded_file_id)
                cleanup['uploaded_file_deleted'] = True
            except Exception:
                cleanup['uploaded_file_delete_failed'] = True
        # Cleanup state is deliberately not allowed to contain credentials.
        cleanup_path = Path(os.environ.get('CLAUDE_PILOT_CLEANUP_OUTPUT', '/tmp/claude-pilot-cleanup.json'))
        cleanup_path.write_text(json.dumps(cleanup, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())
