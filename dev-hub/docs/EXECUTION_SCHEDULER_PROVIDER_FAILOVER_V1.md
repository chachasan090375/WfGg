# ChaCha DEV HUB — Execution Scheduler & Provider Failover V1

Status: DESIGN BASELINE

## Purpose

The scheduler sits between a verified Task Graph and actual dispatch. It decides **when** tasks may run and **which healthy provider** may satisfy each abstract capability. It never treats planning as execution and never turns a provider fallback into an implicit production change.

## Pipeline

`Task Graph -> Provider Health Snapshot -> Capability Binding -> Safety Checks -> Execution Waves -> Explicit Dispatch -> Task Results -> Evidence Collector`

## Provider health

Every provider is observed as one of:

- `HEALTHY`
- `DEGRADED`
- `UNAVAILABLE`
- `UNKNOWN`

`UNKNOWN` is intentionally not equivalent to healthy. A provider without sufficiently fresh health evidence cannot be dispatched when health is required.

Health is separate from technology maturity. For example, a provider may be `ADOPT` in the technology registry but `UNAVAILABLE` right now, or `WATCH` but technically healthy for an approved pilot.

## Provider selection

Selection combines:

1. capability compatibility;
2. technology status (`ADOPT`, `PILOT`, `WATCH`, etc.);
3. current health;
4. task permission/risk class;
5. configured provider order/fallbacks.

The first provider listed for a capability is its architectural primary. If it cannot be used and another eligible provider is selected, the binding is recorded as a failover.

A failover is never silent. The execution plan records the original capability, selected provider, health state and `fallback_used=true`.

## Production boundary

Automatic failover is allowed only for low-risk permissions defined by policy. Repository changes, preview deployment and every production/destructive permission require the configured approval boundary before a fallback can be dispatched.

Provider substitution never changes the permanent architecture or Technology Radar status. Permanent replacement remains a separate human-approved architecture decision.

## Concurrency model

Read/analysis tasks may run in parallel up to the configured limit. Write/deployment/destructive permissions use a per-project writer mutex.

Default V1 behavior is deliberately conservative:

- multiple read-only tasks may share a wave;
- only one serialized/write task may run in a wave;
- read tasks do not overlap a write task;
- dependencies must be complete before downstream work is scheduled.

This avoids an agent reading project state while another agent is mutating it.

## Resource classes

Tasks are classified `light`, `medium`, `heavy`, or `very-heavy`. Heavy classes require Storage Governor preflight before dispatch. Typical browser/E2E/performance tasks are heavy; 3D processing is very-heavy.

The scheduler only marks this requirement. The future dispatcher must obtain the real preflight result and feed it into the execution/evidence flow.

## Failure and retry

Only explicitly transient failure classes may be retried. Policy or security denials, invalid input and missing approvals are non-retryable.

After the retry budget is exhausted, the orchestrator may evaluate an eligible fallback provider. The reason for failover must be persisted.

## Separation of responsibility

The Task Graph Engine decides **what must be done**.

The Execution Scheduler decides **what can safely run together and which provider can be used now**.

The Dispatcher will later perform **actual execution**.

The Evidence Collector decides **what results are admissible as evidence**.

The Lifecycle Engine decides **whether evidence is sufficient to promote the project**.

No one layer may bypass the next.

## V1 outputs

An execution plan contains:

- ordered waves;
- provider binding per capability;
- resource class;
- storage-preflight requirement;
- blocked tasks and precise reasons;
- count of provider failovers.

Typical blockers:

- `CAPABILITY_BLOCKED:e2e-test-web:no-healthy-eligible-provider`
- `FAILOVER_APPROVAL_REQUIRED`
- `DEPENDENCY_BLOCKED:artifact:test-result`
- `UNRESOLVED_DEPENDENCY_OR_CYCLE`

## Next layer

The next architectural layer is the **Execution Dispatcher / Run Controller**. It will consume an approved execution plan, obtain required preflights/approvals, lease the project writer lock, launch the selected provider adapter, capture stdout/stderr/exit state, create a signed/hashed Task Result envelope, and return that envelope to the Evidence Collector.
