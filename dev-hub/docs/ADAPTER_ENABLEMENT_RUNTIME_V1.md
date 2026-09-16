# ChaCha DEV HUB — Adapter Runtime Enablement V1

This layer prepares the `PILOT -> ENABLED` transition without mutating the canonical adapter registry.

## Required evidence

The enablement contract requires three independent classes of evidence:

- repeatability: at least three successful runtime results for the same task identity, with distinct timestamps and distinct result digests, each containing concrete evidence and remaining `UNVERIFIED` by the producer;
- provider health: a fresh normalized `chacha.dev/provider-health-snapshot/v1` entry in state `HEALTHY`;
- rollback: a machine-readable rollback plan for `ENABLED -> DISABLED` with explicit verification checks.

`adapter-enable-readiness.py` validates these preconditions, invokes `adapter-enablement-evidence.py`, then asks `adapter-promotion.py` for a read-only `PILOT -> ENABLED` plan. A successful result is `READY_FOR_ENABLEMENT`; the tool never writes `provider-adapters.v1.json`.

## HTTP smoke independent health probe

`http-smoke-provider-probe.py` is intentionally independent of `http-smoke-adapter`. It verifies the executable exists and is executable, then performs its own loopback-only HTTP request using a separate Python urllib stack. Query strings are not emitted in the recorded source.

The provider probe is normalized by `platform-evidence.py` before enablement consumes it.

## Safety boundary

`READY_FOR_ENABLEMENT` is evidence, not activation. The canonical `PILOT -> ENABLED` state change still requires a separate explicit `adapter-promotion.py ... apply --apply` operation. Production-capable adapters additionally require explicit human approval; `http-smoke-adapter` is read-only and is not production-capable.

The canonical rollback plan for `http-smoke-adapter` remains `ENABLED -> DISABLED` through the promotion engine. Previous promotion and rollback receipts are retained.
