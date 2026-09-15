# ChaCha DEV HUB — Adapter Enablement Evidence V1

Adapter Enablement is the evidence layer for `PILOT -> ENABLED`. It does not change adapter state itself.

The promotion engine already requires three evidence items for this transition:

- `repeatable-pass`
- `provider-health-pass`
- `rollback-defined`

`adapter-enablement-evidence.py` now derives those items from concrete runtime artifacts instead of declarations.

## Repeatability

At least three successful task results are required by policy. Each result must:

- use `chacha.dev/task-result/v1`;
- be produced by the adapter being evaluated;
- have status `OK`;
- remain `UNVERIFIED`, because runtime adapters cannot verify their own work;
- carry a valid and distinct observation timestamp.

## Provider health

Enablement consumes a normalized `chacha.dev/provider-health-snapshot/v1`. The selected provider must be `HEALTHY` and fresh within the policy window. Missing, stale, future-dated, degraded or unavailable health evidence fails the enablement evidence.

Health normalization remains the responsibility of Platform Evidence. The enablement layer does not invent provider health.

## Rollback

Rollback plans are stored in `dev-hub/config/adapter-rollbacks.v1.json` and validated against `dev-hub/schemas/adapter-rollbacks-v1.schema.json`.

For `http-smoke-adapter`, rollback is explicit `ENABLED -> DISABLED`, preserves the executable for forensics, retains previous promotion receipts, stops future scheduling to the adapter, and returns capability selection to scheduler failover policy.

## End-to-end certification

Control Plane CI now exercises the first concrete adapter through the entire non-mutating readiness chain:

`real sandbox execution x3 -> normalized provider health -> rollback validation -> enablement evidence -> promotion plan PILOT->ENABLED`

The final promotion command is plan-only. The repository copy of `provider-adapters.v1.json` must remain unchanged.

## Safety boundary

Evidence generation:

- never mutates `provider-adapters.v1.json`;
- never enables an adapter;
- never creates a human approval;
- never authorizes production changes;
- never turns an `UNVERIFIED` runtime result into verified evidence by itself.

A real adapter promotion still requires the dedicated Promotion Engine, explicit apply semantics, a concrete runtime executable on the target host, and any approval required by the adapter's permissions.
