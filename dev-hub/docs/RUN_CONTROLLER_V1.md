# ChaCha DEV HUB — Run Controller / Execution Dispatcher V1

The Run Controller is the safety boundary between a planned execution and an actual provider invocation.

## Position in the architecture

`Task Graph -> Provider Health -> Execution Scheduler -> Run Controller -> Provider Adapter -> Task Result -> Independent Verification -> Evidence Collector`

The scheduler decides *what could run* and in which wave. The Run Controller decides *whether a scheduled task may be dispatched now*. A successful process exit is not evidence that a lifecycle requirement is satisfied.

## Default mode

The repository policy is intentionally `dispatch-only`.

In this mode the controller:
- validates the Execution Plan against the source Task Graph;
- re-checks project, transition and Evidence Ledger identity;
- resolves every scheduled provider to a registered adapter;
- re-checks human approval for consequential permissions;
- re-checks the Storage Governor evidence for heavy and very-heavy work;
- creates immutable JSON dispatch envelopes;
- creates an auditable Run Record;
- invokes no provider and changes no production system.

Execution must never be enabled merely because a task is scheduled.

## Adapter contract

Providers and adapters are separate concepts. The Capability Registry selects a provider. The Provider Adapter Registry maps that provider to an execution adapter.

Adapters use a common contract:
- input: `chacha.dev/dispatch-envelope/v1`;
- output: `chacha.dev/task-result/v1`;
- transport: structured JSON;
- local process invocation: argv with `shell=False`;
- inline secrets are forbidden.

Connector, MCP, provider API and VPS-local adapters can therefore use different implementations without changing the project or capability contract.

All adapters are currently `DESIGNED`, not `ENABLED`. That is deliberate: architecture modelling can continue while VPS capacity work is paused, and no partially implemented adapter can execute accidentally.

## Write locking

Any permission that can mutate a workspace, repository, preview, production data, secrets or technology state requires a project lock. Only one writer per project is allowed. Read/plan work can remain parallel according to the scheduler policy.

A forced unlock is a consequential operation and requires explicit human approval.

## Production boundary

The Run Controller re-checks approvals at dispatch time. A prior plan, scheduler decision or stale approval is insufficient.

Consequential permissions include:
- production deploy;
- production data write;
- secret change;
- destructive operation;
- technology replacement.

No provider failover may silently cross this boundary.

## Storage boundary

Tasks classified as `heavy` or `very-heavy` require an `OK` `storage-preflight` artifact in the Evidence Ledger before dispatch. This keeps Playwright, Lighthouse, Blender and similar workloads from bypassing the Storage Governor.

## Logs and evidence

When execution is eventually enabled, stdout and stderr are captured separately, bounded in size and represented by SHA-256 digests in the Run Record. Full logs live outside Git.

The Run Controller may create a Task Result, but it cannot mark that result independently verified. This prevents the execution component from certifying its own work. Verification remains a separate role and the Evidence Collector remains the only path into lifecycle evidence.

## Fail-closed rules

Dispatch is blocked when any of the following is true:
- task is missing from the source Task Graph;
- provider has no registered adapter;
- adapter does not support the requested permission;
- execution is requested while policy is not `execute-enabled`;
- adapter is not `ENABLED`;
- adapter has no executable/runtime implementation;
- required human approval is absent;
- required storage preflight is absent;
- project lock cannot be acquired;
- plan, graph and ledger identities disagree.

## Future activation sequence

Before enabling real execution:
1. implement provider-specific adapters;
2. run adapter contract tests;
3. add secret-redaction tests;
4. test project locking and crash recovery;
5. test timeout/retry classification;
6. test failover without production mutation;
7. validate independent verification flow;
8. only then change selected adapters from `DESIGNED` to `ENABLED` and the controller policy from `dispatch-only` to `execute-enabled`.

This activation is a separate, explicit engineering decision and not a side effect of installing V5.
