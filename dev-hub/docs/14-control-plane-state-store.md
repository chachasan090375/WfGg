# ChaCha DEV HUB V5 — Control Plane State Store & Immutable Audit Journal

## Purpose

The Control Plane needs one durable answer to four questions for every project:

1. Where is the project now?
2. Why is it in that state?
3. Which evidence, decisions and approvals produced that state?
4. Can the state be reconstructed after interruption or corruption?

The V1 design separates **current state** from **historical truth**.

- `state.json` is the current materialized projection.
- `audit.jsonl` is the append-only historical journal.
- every event is SHA-256 hash chained to the previous event.
- the projection can be rebuilt from the journal.

## Runtime layout

```text
/opt/chacha-dev/runtime/state/<project>/
├── state.json
├── audit.jsonl
├── snapshots/
└── checkpoints/
```

The path is a runtime default only; the architecture is storage-provider agnostic.

## State projection

The projection groups control-plane state into stable sections:

```text
identity
lifecycle
architecture
capabilities
providers
execution
evidence
approvals
risks
decisions
recovery
operations
```

The projection is mutable, but only by creating an audit event first. A mutation without an event is invalid by policy.

## Audit journal

The journal uses JSON Lines. Each event contains:

- project
- monotonic sequence number
- unique event id
- event type
- actor
- UTC timestamp
- previous event digest
- payload
- external references
- SHA-256 digest of the complete unsigned event

The first event has `previous_event_digest = null`. Every later event must reference the digest of the preceding event.

This gives us tamper evidence without pretending to provide cryptographic non-repudiation. If stronger guarantees are needed later, signatures or external timestamping can be added without changing the event model.

## Event model

Initial event types are:

```text
PROJECT_INITIALIZED
STATE_PATCHED
LIFECYCLE_TRANSITION
DECISION_RECORDED
APPROVAL_RECORDED
RISK_ACCEPTANCE_RECORDED
PROVIDER_BINDING_RECORDED
RUN_RECORDED
EVIDENCE_RECORDED
SNAPSHOT_CREATED
CHECKPOINT_CREATED
PROJECT_RETIRED
```

State-changing events may carry a `state_patch`. The engine uses merge-patch semantics so replay is deterministic.

## Snapshots vs checkpoints

A **snapshot** is an operational copy of the current projection.

A **checkpoint** is a deliberately retained state boundary. Release and retirement boundaries require checkpoints by orchestration policy.

Snapshots and checkpoints are themselves recorded in the journal with their file digest.

## Recovery model

If `state.json` is lost or corrupt:

1. verify the journal sequence and hash chain;
2. replay the initial state plus every recorded state patch;
3. regenerate `state.json`;
4. compare the reconstructed head digest with the journal head.

A broken journal chain blocks automatic reconstruction and must be treated as a control-plane integrity incident.

## Backup model

The state projection, journal, snapshots and checkpoints are all eligible for NAS backup. The audit journal is retained for the full project lifetime.

Secrets must never be written into this state store. References to secret identifiers are acceptable; secret values are not.

## Control-plane integration

```text
Planner / Manifest / Lifecycle / Scheduler / Run Controller
                         │
                         ▼
                Control Plane Store
                 ┌───────────────┐
                 │ current state │
                 │   state.json  │
                 └───────┬───────┘
                         │
                         ▼
                 append-only journal
                    audit.jsonl
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
        snapshots                checkpoints
```

The store does not decide whether an action is allowed. Policy, Lifecycle and Orchestration make that decision. The store records the resulting authoritative control-plane state and history.

## Safety boundary

The Git branch contains the architecture and engine only. No runtime state has been initialized on the VPS in this design phase.
