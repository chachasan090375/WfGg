# Claude Agent — CONTRACT_OK V1

## Status

`anthropic-claude` / `claude-agent-adapter` is statically qualified from `DESIGNED` to `CONTRACT_OK`.

This status means the DEV HUB contract is internally coherent. It does **not** mean the Anthropic runtime has been called, authenticated, provisioned, or admitted to execute project tasks.

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

Future runtime qualification may reference `ANTHROPIC_API_KEY`, but the value must remain outside Git and outside evidence. The contract is `REFERENCE_ONLY` and requires redaction of authorization/API-key headers.

No credential was used for `DESIGNED -> CONTRACT_OK`.

## Verification boundary

Claude-produced results remain `UNVERIFIED`. `verification-broker` remains the independent verification authority. Claude cannot self-verify its own task result.

## Next transition

`CONTRACT_OK -> PILOT` requires all generic DEV HUB gates plus a provider-specific runtime harness:

1. runtime-contract-pass;
2. sandbox-only;
3. provisioning-pass;
4. explicit external credential binding without secret leakage;
5. read-only task execution using only the allowlisted tool surface;
6. structured `chacha.dev/task-result/v1` output;
7. provider result stays `UNVERIFIED`;
8. no registry auto-promotion.

The PILOT qualification must remain separate from any future contract that admits `Edit`, `Write`, shell execution, test orchestration, repository mutation, or production operations.
