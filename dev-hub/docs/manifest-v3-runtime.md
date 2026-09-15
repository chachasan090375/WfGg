# ChaCha DEV HUB V5 — Manifest V3 Runtime

## Purpose

The Manifest V3 runtime turns the V5 reference architecture into an enforceable project contract. It does not deploy or modify production. Its first responsibility is to prove that a project description is structurally coherent before any agent writes code or executes a consequential action.

## Inputs

- Project Manifest V3 (`chacha.dev/project-manifest/v3`)
- Capability Registry V1 (`chacha.dev/capability-registry/v1`)
- Quality Gates V1 (`chacha.dev/quality-gates/v1`)

## Reference engine

`dev-hub/bin/manifest-v3-engine.py`

Commands:

```bash
python3 dev-hub/bin/manifest-v3-engine.py validate <manifest.json> \
  --registry dev-hub/config/capability-registry.v1.json

python3 dev-hub/bin/manifest-v3-engine.py graph <manifest.json> \
  --registry dev-hub/config/capability-registry.v1.json

python3 dev-hub/bin/manifest-v3-engine.py resolve <manifest.json> \
  --registry dev-hub/config/capability-registry.v1.json

python3 dev-hub/bin/manifest-v3-engine.py inspect <manifest.json> \
  --registry dev-hub/config/capability-registry.v1.json
```

`inspect` returns the full machine-readable report. `validate` exits with code 2 if semantic errors exist.

## Validation layers

### 1. Contract validation

The runtime verifies mandatory V3 sections, identity, components, environments, storage and technology-policy invariants. The JSON Schema remains the canonical shape contract; the runtime adds cross-field semantic checks that JSON Schema alone cannot conveniently express.

### 2. Component graph

Every component has a stable ID. `depends_on` and explicit dependency edges are converted into one dependency graph.

The runtime checks:

- unknown dependency endpoints;
- self dependencies;
- duplicate component IDs;
- dependency cycles;
- topological order for orchestration.

A cyclic required component graph is an architecture error.

### 3. Environment promotion graph

Promotion paths such as `development -> preview -> production` form a second graph.

The runtime checks:

- unknown promotion sources;
- promotion cycles;
- duplicate environment names;
- mandatory explicit approval for production environments.

### 4. Capability resolution

Projects ask for capabilities, never hard-code infrastructure implementations into the architecture.

Resolution states:

- `READY`: provider is at `ADOPT`;
- `CONDITIONAL`: provider is `PILOT`, `WATCH`, `ASSESS` or `DISCOVER`;
- `DEGRADED`: selected provider is deprecated;
- `UNAVAILABLE`: no eligible provider exists.

A required `UNAVAILABLE` or `DEGRADED` capability invalidates execution readiness. A required `CONDITIONAL` capability is allowed for design/test work but prevents the runtime from claiming full production-provider readiness.

This distinction is intentional. A technology appearing in the radar is not automatically production-approved.

### 5. Quality-control completeness

Every V3 project is checked against the canonical 18 control domains defined in `quality-gates.v1.json`:

1. product-domain
2. ux-frontend
3. api-backend
4. data
5. integrations
6. identity-security
7. testing
8. build-dependencies
9. ci-cd-release
10. environments-infra
11. observability
12. performance
13. reliability-resilience
14. backup-recovery
15. documentation
16. operations-sre
17. finops-capacity
18. governance-compliance

The runtime validates that the controls exist. The evidence-audit layer evaluates whether they are actually satisfied.

## Separation of concerns

The V5 control flow is deliberately split:

```text
Manifest V3
    |
    +--> contract / graph validation
    |
Capability Registry
    |
    +--> provider resolution
    |
Agent Routing
    |
    +--> execution planning
    |
Evidence Audit
    |
    +--> 18 quality gates
    |
Approval Policy
    |
    +--> consequential action or production release
```

No single AI agent is the source of truth for all five layers.

## Safety invariants

The runtime must preserve these rules:

- production technology is never replaced automatically;
- a production environment requires explicit approval;
- a claim without evidence is not `OK`;
- required capabilities must have an eligible provider;
- dependency cycles are rejected;
- high/critical projects require explicit RPO and RTO targets;
- storage pressure is governed before heavy execution;
- provider selection for consequential decisions is recorded;
- rollback remains possible for production changes.

## WfGg reference project

`dev-hub/examples/wfgg.manifest.v3.json` is the first reference project for Manifest V3. It is a model and does not replace the production manifest until the migration is explicitly approved.

The expected use of WfGg is to continuously exercise the framework against a real multi-component project: frontend, edge API, D1, R2, GitHub, Cloudflare, NAS storage, documentation sources, agents and quality gates.

## Next runtime layer

The next V5 component is the **Project Planner**. It will accept a project intent plus constraints, select a Golden Path, generate a draft Manifest V3, resolve capabilities, identify unresolved decisions, and only then hand tasks to specialist agents.

The planner must not generate code before the architecture contract reaches a valid design state.
