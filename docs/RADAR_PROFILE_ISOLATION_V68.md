# Radar V6.8 — Profile Isolation

V6.8 treats the map scan as primary evidence and profile enrichment as a second, best-effort layer. A failure in `get.user.info.multi` must never discard players already observed on the map.

## Adaptive enrichment

Collector starts with batches of at most 50 UID values. When a batch fails, it is bisected recursively. When a batch succeeds but returns only part of the requested profiles, only the missing subset is retried. The process stops at individual profiles or at a hard budget of 192 profile attempts per Collector cycle.

This lets Collector distinguish a global multi-profile incompatibility from a size-sensitive batch failure, a partial response, or one isolated profile that cannot be enriched.

## Safe telemetry

Only aggregate counters and sanitized error codes are published to the Radar job:

- requested profiles;
- attempts;
- successful/failed batches;
- profiles returned/resolved/unresolved;
- profiles accepted by Collector;
- isolated single failures;
- ingest failures;
- attempt-budget/context state;
- up to 32 failure summaries containing only scope, batch size and sanitized code.

No UID, pseudo, token, session data, device identifier, raw payload or raw stderr is included in the V6.8 telemetry.

## Completion semantics

A profile failure is no longer a fatal Collector-cycle failure. The map rows remain valid and the cycle can complete with profile status `PARTIAL`, `FAILED`, `PARTIAL_BUDGET` or `UNAVAILABLE`. Systemic cycle failures remain fatal independently of enrichment.

## Knowledge value

The resulting batch-size/error observations are protocol evidence for Collector's Knowledge Engine. They allow future rules about `get.user.info.multi` to be marked OBSERVED/INFERRED/CONFIRMED without pretending an unverified protocol assumption is a game rule.
