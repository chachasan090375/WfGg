# ChaCha DEV HUB — Project Planner V1

## Purpose

The Project Planner converts a human project intention into an explicit architecture contract before implementation begins.

Pipeline:

`Project Intent -> Golden Path selection -> Components -> Capabilities -> Provider resolution -> Decisions -> Quality gates -> Draft Manifest V3`

The planner is deterministic and has no authority to deploy, modify production, install providers, or approve its own architecture decisions.

## Inputs

- `schemas/project-intent-v1.schema.json`: project need and constraints.
- `config/golden-paths.v1.json`: machine-readable reusable architecture patterns.
- `config/capability-registry.v1.json`: replaceable capability providers and technology status.

## Outputs

The planner emits `chacha.dev/project-plan/v1` containing:

- selected Golden Path or composite path;
- selection confidence and reasons;
- proposed components and dependencies;
- required capabilities and resolved providers;
- the 18 architecture quality gates;
- unresolved decisions;
- risks;
- readiness state;
- a draft Manifest V3.

## Readiness rule

Code generation is not authorized while a mandatory architectural input remains unresolved or a required capability is unavailable/degraded.

A provider in `WATCH`, `ASSESS`, `PILOT`, or `DISCOVER` is `CONDITIONAL`: it can be surfaced for evaluation but is not silently promoted to `ADOPT`.

`production_change_allowed` is always `false` in a planner result. Production promotion is a separate approval/evidence process.

## Golden Path selection

`config/golden-paths.v1.json` is the executable companion to `GOLDEN_PATHS_V1.md`.

Selection considers, among other signals:

- delivery channels (web/PWA/API/mobile/scheduled/event/AI/3D);
- persistence requirements;
- relational and object-storage needs;
- offline and real-time constraints;
- criticality;
- simplicity preference;
- managed-service preference.

Composite paths are supported. Current automatic composition triggers include:

- scheduled/event-driven -> add GP-05 when appropriate;
- AI agent -> add GP-06;
- 3D pipeline -> add GP-07.

## Capability resolution

The project asks for capabilities, never permanent products. Example:

`e2e-test-web -> Playwright (WATCH)`

The selected provider and its registry status are recorded in the plan. Technology Radar may later recommend alternatives, but replacement still requires evidence and the configured approval boundary.


## Object Factory

Applications that manipulate business data may declare `domain_objects` in the Project Intent.

ChaCha DEV responsibility chain:

`Project Intent -> Project Planner / Dev Architect -> Object Factory -> Component Factory -> Capability Foundry (only on technical gap) -> verification`

Responsibilities:

- **Project Planner / Dev Architect:** identifies the business objects required by the application and blocks code generation when a data-storing application has no explicit object model.
- **Object Factory:** searches for reusable qualified object contracts, otherwise produces a new explicit object contract covering fields, sensitive attributes, relationships, persistence semantics, API exposure, UI exposure, events, validation and tests.
- **Component Factory:** materializes a new object contract into the application's implementation when reuse is not possible.
- **Capability Foundry:** is invoked only if the requested object needs a technical capability that ChaCha DEV does not already possess.
- **Guardian / Sentinel / normal project gates:** verify the result before consequential use.

Object Factory does **not** choose production providers, deploy databases, mutate production storage, promote itself, or bypass architecture approval. Its output is an application-domain contract and downstream handoff.

Reuse-before-build is mandatory. Qualified reusable domain objects belong in `config/object-registry.v1.json`.


## Architecture decisions

The planner deliberately creates `NEEDS_INPUT`, `NEEDS_EVIDENCE`, and `NEEDS_APPROVAL` decisions rather than inventing missing requirements.

Examples:

- authentication/authorization model;
- RPO and RTO;
- conditional provider promotion;
- consequential infrastructure choices.

## Reference invocation

```bash
python3 dev-hub/bin/project-planner.py \
  dev-hub/examples/project-intent.sample.v1.json \
  --registry dev-hub/config/capability-registry.v1.json \
  --golden-paths dev-hub/config/golden-paths.v1.json \
  --pretty \
  --output /tmp/project-plan.json \
  --manifest-output /tmp/project-manifest.v3.json
```

The generated draft Manifest must subsequently pass semantic validation through `manifest-v3-engine.py` after its unresolved architecture fields have been completed.

## Separation of responsibilities

- **Planner:** proposes architecture.
- **Manifest engine:** validates the architecture contract and dependency graph.
- **Capability Registry:** resolves tool/provider choices.
- **Dev Architect:** orchestrates roles, evidence and approvals.
- **Technology Radar:** discovers and compares alternatives.
- **Agents/providers:** execute only within their granted scope.
- **Human approval:** controls production-consequential changes.

This separation prevents one AI agent, IDE, framework or vendor from becoming the architecture itself.
