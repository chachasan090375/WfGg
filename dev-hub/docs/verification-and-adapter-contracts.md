# ChaCha DEV HUB V5 — Verification Broker & Adapter Contracts

## Purpose

Execution and verification are separate trust domains.

A successful process exit is only an execution fact. It is not sufficient to satisfy a lifecycle gate. The Run Controller therefore emits an unverified `chacha.dev/task-result/v1`. The Independent Verification Broker checks that result against the Task Graph contract and the evidence before producing a separate verification report and, only when admissible, a verified copy of the task result.

## Trust chain

```text
Execution Plan
  -> Run Controller
  -> Provider Adapter
  -> Task Result (UNVERIFIED)
  -> Independent Verification Broker
  -> Verification Report
  -> Task Result (VERIFIED, if admissible)
  -> Evidence Collector
  -> Evidence Ledger
  -> Lifecycle Engine
```

The producer and verifier must be different identities. Human verification is never synthesized by the broker.

## Verification outcomes

- `VERIFIED`: contract, evidence and required verification mode are satisfied.
- `REJECTED`: one or more mandatory checks failed.
- `NEEDS_INDEPENDENT_CHECK`: evidence or verification mode requires an external agent or real human decision.

The broker never upgrades a failed or blocked execution to success.

## Evidence rules

Evidence entries require a source and SHA-256 digest. For locally readable absolute paths the broker recomputes the digest. A missing local source is a rejection. External/non-local sources are not blindly trusted and remain `NEEDS_INDEPENDENT_CHECK` until independently validated.

The original task result is immutable. A verified result is written as a separate artifact.

## Adapter contracts

Provider adapters are capability transport implementations, not architecture dependencies. Every adapter follows the same protocol:

```text
stdin:  chacha.dev/dispatch-envelope/v1 JSON
stdout: chacha.dev/task-result/v1 JSON
shell:  disabled
```

The adapter lifecycle is:

```text
DESIGNED
  -> CONTRACT_OK
  -> PILOT
  -> ENABLED
  -> DEGRADED / DISABLED
  -> RETIRED
```

No promotion is automatic.

### DESIGNED

The contract is documented but the adapter is not executable. This is the current safe state for the initial adapter registry.

### CONTRACT_OK

Static contract checks passed. This still does not authorize execution.

### PILOT

A sandbox runtime contract test passed. The adapter may be evaluated under restricted policy.

### ENABLED

Requires repeatable runtime evidence, provider-health evidence, rollback definition and any approval required by the permission boundary.

## Adapter Contract Test Harness

`dev-hub/bin/adapter-contract-harness.py` performs static validation for the full registry and optional runtime tests for one adapter using a dispatch-envelope fixture.

Static checks include:

- provider references an existing adapter;
- adapter status is recognized;
- permissions are known;
- execution location is known;
- shell execution remains disabled;
- `DESIGNED` adapters have no executable;
- runtime-capable statuses have an absolute executable path.

Runtime tests are sandbox-only and check that the adapter accepts the dispatch envelope and returns a matching Task Result identity and schema.

## Safety invariant

The pipeline deliberately requires three independent facts before lifecycle evidence can become `OK`:

1. the scheduler selected an eligible healthy provider;
2. the Run Controller recorded what actually executed;
3. an independent verifier validated the result and evidence.

No single agent or tool owns all three decisions.
