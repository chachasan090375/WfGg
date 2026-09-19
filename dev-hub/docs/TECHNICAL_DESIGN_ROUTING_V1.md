# ChaCha DEV HUB — Product Requirement to Technical Design V1

Status: QUALIFICATION

## Purpose

This layer is the formal boundary between a human product requirement and implementation work.

The product owner defines **what must be achieved**, the product constraints and acceptance criteria. The product owner is not expected to choose API shape, database schema, indexes, service boundaries, deployment topology or other implementation details.

ChaCha Dev Architect owns the orchestration from product intent into technical-design work. Domain specialists own the technical decisions inside their area.

## Canonical flow

```text
Human Product Owner
        |
        v
Product Requirement
        |
        v
Project Control: technical-design
        |
        v
ChaCha Dev Architect
        |
        +--> Product/Domain Architect
        +--> Frontend Architect (when applicable)
        +--> Backend/API Architect (when backend/integration is involved)
        +--> Data Architect (when persisted/queryable data is involved)
        +--> Security Reviewer
        +--> Test Engineer
        +--> Platform / SRE / Performance / Recovery specialists as required
        |
        v
Technical Design Plan
        |
        v
Specialist design fragments + cross-reviews
        |
        v
ADR set + requirement/design traceability
        |
        v
Implementation gate opens
        |
        v
Task Graph -> Scheduler -> Run Controller -> implementation adapters
```

## Separation of responsibilities

### Product owner

Owns:
- objective;
- functional requirements;
- acceptance criteria;
- business constraints;
- explicit must-preserve behavior;
- product decisions that cannot be inferred technically.

Does not need to own:
- endpoint shape;
- table/index design;
- service decomposition;
- cache/retry strategy;
- migration mechanics;
- observability implementation;
- deployment topology.

### ChaCha Dev Architect

Owns:
- normalization of the product requirement;
- affected-domain/component detection;
- specialist routing;
- design task graph;
- cross-review requirements;
- design completeness gate;
- traceability from requirement to technical decisions.

It does not implement code during this stage and cannot self-certify specialist outputs.

### Backend/API Architect

Owns:
- backend/service boundaries;
- API contracts;
- validation and error model;
- pagination/rate limits where applicable;
- idempotency/concurrency behavior;
- integration behavior, retries/timeouts and failure model;
- compatibility with existing backend components.

### Data Architect

Owns:
- canonical entities and identifiers;
- relationships and integrity constraints;
- query patterns and indexes;
- migrations;
- retention/lifecycle;
- provenance/data-quality contract.

### Security Reviewer

Owns cross-review of:
- trust boundaries;
- sensitive data;
- secrets/logging;
- authorization;
- abuse/input-output protections.

### Test Engineer

Converts each acceptance criterion into independently falsifiable test obligations.

### Documentation/ADR Agent

Records consequential design choices and keeps requirement -> design -> implementation traceability.

## Implementation gate

Code generation is forbidden immediately after a product requirement is captured.

The gate remains closed until at least:

1. product/domain contract is complete;
2. every required primary specialist produced its design contract;
3. mandatory cross-reviews completed;
4. architecture decisions are resolved or explicitly deferred;
5. ADRs are recorded;
6. acceptance-test matrix is defined.

The router therefore emits `code_generation_allowed=false` by design.

## Project Control interface

The canonical operator entrypoint is:

```bash
project-control technical-design \
  --project <project> \
  --requirement <product-requirement.json> \
  --manifest <manifest.v3.json>
```

The operation is planning-only. It writes:
- a `chacha.dev/technical-design-plan/v1`;
- a design-only `chacha.dev/task-graph/v1`.

It does not dispatch implementation work.

## Radar reference

For `RADAR-V619-PLAYER-DATA-SHIELD`, the normalized requirement explicitly routes:
- Product/Domain Architect;
- Backend/API Architect;
- Data Architect;
- Security Reviewer;
- Test Engineer;
- SRE/Observability Engineer;
- Performance Engineer;
- Documentation/ADR Agent.

Primary implementation targets are:
- `radar-worker`;
- `radar-d1`;
- `radar-connector`.

The UI is not made an implementation target for the shield-inventory requirement until a product requirement explicitly asks to expose proven fields in the UI.

## Runtime boundary

The Technical Design Router itself is deterministic orchestration and never pretends to replace specialist reasoning.

The generated specialist task graph is the contract for the specialist-agent runtime. If the architecture-agent execution adapter is not ENABLED, the graph remains planned and fail-closed. No implementation is allowed to bypass this gate.
