# Claude Agent Adapter V1 — design-only integration

## Decision

Claude is useful to ChaCha DEV HUB as a second independent AI development engine, but it is **not** modeled as another MCP catalog entry. It is modeled as an external AI-agent provider behind the same DEV HUB dispatch/result boundary as other execution providers.

Provider: `anthropic-claude`  
Adapter: `claude-agent-adapter`  
Current status: `DESIGNED` / `ASSESS`

No Anthropic credential is required or accepted during this design stage and no runtime call is performed.

## Why this fits the architecture

The DEV HUB already routes by capability rather than by vendor and supports best-fit selection with fallback. Claude adds provider/model diversity for code review, documentation, architecture analysis, debugging and later — after a separate write contract — code editing. This allows cross-provider review rather than having one engine produce and validate its own work.

## Provider abstraction and runtime surfaces

The DEV HUB binds to an `anthropic-provider-abstraction`, not directly to one Anthropic SDK generation.

Preferred runtime candidate: `claude-managed-agents` after separate runtime qualification.  
Compatibility runtime: `claude-agent-sdk`.

This reflects Anthropic's current migration path while keeping the DEV HUB contract stable if Anthropic changes its agent runtime again.

Claude Code as an MCP server remains a secondary optional transport. Claude Code GitHub Actions is also not the primary path because direct repository automation could bypass DEV HUB scheduling and evidence boundaries unless wrapped by a later dedicated contract.

Official references:
- https://platform.claude.com/docs/en/managed-agents/migration
- https://platform.claude.com/docs/en/managed-agents/permission-policies
- https://platform.claude.com/docs/en/manage-claude/authentication
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner

## Design-stage permissions

Allowed read-only tool names in the contract:
- `Read`
- `Glob`
- `Grep`

Explicitly denied:
- `Bash`
- `Edit`
- `Write`
- arbitrary network tools
- MCP tools unless separately allowlisted
- repository writes
- production mutation
- destructive operations

The initial capability registry exposes Claude only as an `ASSESS` candidate for `code-review` and `documentation`. It is deliberately absent from `code-edit`.

## Authentication

The provider abstraction supports two future authentication modes:

- API key reference for initial sandbox qualification;
- Workload Identity Federation as the preferred future CI/CD direction when the execution environment supports it.

A future API-key runtime binding may reference `ANTHROPIC_API_KEY`, but the secret value must remain outside Git and outside evidence. Headers and credential values must be redacted. Runtime credentials are not needed for the `DESIGNED` stage.

## Model policy

No fixed Claude model ID is stored in the architectural contract. Runtime selection must use an approved active model. Technology Radar must track Anthropic model availability, runtime/SDK tool-surface changes and deprecations; breaking changes may require requalification.

## Verification separation

Claude may review outputs produced by other providers such as `antigravity` and `skywork`. Claude-produced outputs remain `UNVERIFIED` and require an independent verifier via `verification-broker`. Claude must never self-declare its own result verified.

## Future admission path

`DESIGNED → CONTRACT_OK → PILOT → ENABLED`

The next stage may qualify read-only live execution. A **separate** contract is required before adding `Edit`, `Write`, workspace mutation, test orchestration or any repository write. Production permissions remain out of scope.
