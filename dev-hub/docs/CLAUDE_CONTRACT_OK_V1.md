# Claude Agent — CONTRACT_OK V1

## Status

`anthropic-claude` / `claude-agent-adapter` is statically qualified from `DESIGNED` to `CONTRACT_OK`.

This status means the DEV HUB contract is internally coherent. It does **not** mean an Anthropic runtime has been called, authenticated, provisioned, or admitted to execute project tasks.

## Runtime abstraction

The DEV HUB binds to `anthropic-provider-abstraction` rather than to one Anthropic SDK generation.

- preferred runtime candidate: `claude-managed-agents` after runtime qualification;
- compatibility backend: `claude-agent-sdk`;
- Claude Code MCP: secondary optional transport only;
- Claude GitHub automation: not a primary DEV HUB execution path.

This keeps the dispatch/evidence contract stable if Anthropic changes its runtime surface again.

## Current permissions

- adapter permissions: `read`, `plan`
- provider decision: `ASSESS`
- capability exposure: `code-review`, `documentation`
- workspace scope: read-only
- allowed tools in the contract: `Read`, `Glob`, `Grep`
- denied tools: `Bash`, `Edit`, `Write`
- no `code-edit` routing
- no fallback routing
- no workspace write
- no repository write
- no production mutation
- no destructive operation

## Authentication boundary

The abstraction accepts future external authentication through either an API-key reference or Workload Identity Federation. Initial sandbox qualification may use an API-key reference; WIF is the preferred future CI/CD direction when the execution environment supports it.

No credential value may appear in Git or evidence. Authorization material must be redacted. No credential was used for `DESIGNED -> CONTRACT_OK`.

## Verification boundary

Claude-produced results remain `UNVERIFIED`. `verification-broker` remains the independent verification authority. Claude cannot self-verify its own task result.

## Next transition

`CONTRACT_OK -> PILOT` requires all generic DEV HUB gates plus a provider-specific runtime harness:

1. runtime-contract-pass;
2. sandbox-only;
3. provisioning-pass;
4. explicit external authentication binding without secret leakage;
5. recorded runtime surface and active model identity;
6. read-only task execution using only the allowlisted tool surface;
7. structured `chacha.dev/task-result/v1` output;
8. provider result stays `UNVERIFIED`;
9. no registry auto-promotion.

The PILOT qualification must remain separate from any future contract that admits `Edit`, `Write`, shell execution, test orchestration, repository mutation, or production operations.
