# Claude Managed Agents — PILOT preparation V1

## Purpose

Prepare `anthropic-claude` / `claude-agent-adapter` for `CONTRACT_OK -> PILOT` without making a runtime call and without placing credentials or Anthropic resource identifiers in Git.

This preparation phase is intentionally **blocked** until external authentication and provisioned Managed Agent resources exist.

## Runtime target

Preferred runtime: `claude-managed-agents`.

The DEV HUB contract remains provider-neutral. Claude Agent SDK remains a compatibility backend, not the architectural boundary.

## Least-privilege pilot

The pilot toolset defaults to disabled and enables only:

- `read`
- `glob`
- `grep`

Explicitly disabled:

- `bash`
- `write`
- `edit`
- `web_fetch`
- `web_search`

The cloud environment is constrained to limited networking with an empty host allowlist. MCP-server access and package-manager networking are disabled.

No workspace write, repository write, shell execution, web access, MCP access, production mutation or destructive operation is admitted.

## Read-only fixture

The probe fixture is `dev-hub/fixtures/claude-pilot-readonly-fixture.txt` and contains the marker:

`CHACHA_CLAUDE_PILOT_READONLY_2026_09_16`

A future runtime probe must mount a read-only copy, locate it, read it, and report the marker without editing, creating, deleting, renaming or executing files.

## External references

The preparation preflight checks only whether references exist. It never reads, prints or hashes credential values.

Expected runtime references:

- `ANTHROPIC_API_KEY` for the initial sandbox qualification, or a later separately contracted identity-federation binding;
- `CHACHA_ANTHROPIC_AGENT_ID`;
- `CHACHA_ANTHROPIC_ENVIRONMENT_ID`;
- `CHACHA_ANTHROPIC_AGENT_VERSION`.

These are deliberately absent from Git.

## Preflight states

`claude-managed-agents-pilot-preflight.py` can emit:

- `BLOCKED_STATIC_CONTRACT` — an architectural invariant is broken;
- `BLOCKED_AUTH_MISSING` — static contract is valid but external authentication is not configured;
- `BLOCKED_PROVISIONING_MISSING` — authentication reference exists but Agent/Environment bindings are missing;
- `READY_FOR_RUNTIME_PROBE` — all external references are present; this still does not promote the adapter.

The preflight never mutates `provider-adapters.v1.json`, never executes Claude and never marks the adapter PILOT.

## Promotion gate

Actual `CONTRACT_OK -> PILOT` still requires:

1. `runtime-contract-pass`;
2. `sandbox-only`;
3. `provisioning-pass`;
4. a provider-specific live runtime probe;
5. `chacha.dev/task-result/v1` with `status=OK`;
6. producer verification status remains `UNVERIFIED`;
7. no credential leakage;
8. explicit promotion after evidence, never automatic.

A later and separate contract is required before admitting `Edit`, `Write`, shell execution, repository mutation, test orchestration or any production operation.
