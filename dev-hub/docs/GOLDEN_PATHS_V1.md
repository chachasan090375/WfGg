# ChaCha DEV HUB — Golden Paths V1

Golden Paths are reusable reference architectures, not mandatory stacks. Each path specifies required capabilities and evidence while providers remain replaceable through the Capability Registry.

## GP-01 — Static/PWA + Edge API + Managed Data

Best for lightweight web applications, portals and mobile-first PWAs.

Components:
- frontend-web
- worker-edge/backend-api
- database
- object-storage (optional)

Required capability domains:
- UX/frontend
- API/backend
- data
- identity/security
- testing
- CI/CD
- observability
- performance
- recovery
- operations

Recommended current providers:
- source-control: GitHub
- edge tooling/deploy: Wrangler
- database: D1-compatible provider adapter
- object storage: R2-compatible provider adapter
- unit/integration tests: Vitest candidate
- E2E: Playwright candidate

Reference adopter: WfGg.

## GP-02 — SPA/SSR + API Service + SQL

Best for conventional full-stack products requiring a richer server application.

Components:
- frontend-web
- backend-api/service
- database
- cache optional
- queue/event-bus optional

Mandatory extras:
- API contract/version policy
- migration policy
- connection pooling/capacity policy where relevant
- server-side health/readiness checks
- staged environment strategy

## GP-03 — Worker / Serverless API

Best for event-driven, HTTP edge or small stateless APIs.

Components:
- worker-edge
- optional database/object-storage/queue

Mandatory extras:
- execution limits/quotas
- timeout/retry policy
- idempotency where relevant
- cold-start/runtime constraints
- provider portability assessment

## GP-04 — Python Service / API

Components:
- service or backend-api
- optional database/cache/queue

Required engineering baseline:
- isolated environment
- deterministic dependencies
- formatter/linter/type-check policy
- unit/integration tests
- application health endpoint
- structured logs

Provider choices remain registry-driven.

## GP-05 — Data Pipeline / Batch Job

Components:
- data-pipeline or scheduled-job
- database/object-storage
- optional queue/event-bus

Mandatory extras:
- input/output data contracts
- lineage/provenance
- restartability/idempotency
- checkpointing when relevant
- retention policy
- data-quality tests
- cost/capacity controls

## GP-06 — AI-enabled Service

Components:
- backend-api/service
- ai-agent or model-provider adapter
- optional retrieval/data components

Mandatory extras:
- model/provider abstraction
- prompt/config versioning
- eval suite
- fallback behavior
- rate/cost budgets
- privacy/data-boundary controls
- hallucination/error handling appropriate to use case
- human approval boundaries for consequential actions

No model/provider is hard-coded as permanent architecture.

## GP-07 — 3D / Asset Processing Pipeline

Components:
- 3d-pipeline
- static-assets/object-storage
- optional scheduled-job/service

Current candidate providers:
- Blender
- UnityPy

Mandatory extras:
- source asset provenance
- reproducible transforms
- large-file storage policy
- artifact checksums
- workspace disk preflight
- offload to NAS/cloud artifact store

## Golden Path Selection

The Dev Architect chooses or proposes a path from project intent, then tailors it. Selection is evidence-driven and may combine paths.

Example:

`PWA + AI feature + scheduled imports` may combine GP-01 + GP-05 + GP-06.

## Anti-patterns

A Golden Path must never:
- force one vendor where an equivalent capability adapter can be used;
- mark a gate OK without evidence;
- install a production dependency solely because it is popular;
- hide missing recovery/security/testing behind a global numeric score;
- assume every project needs every component.

## Template lifecycle

`DRAFT -> VALIDATED -> RECOMMENDED -> DEPRECATED -> RETIRED`

Validation requires at least one successful reference implementation and documented rollback/migration implications.
