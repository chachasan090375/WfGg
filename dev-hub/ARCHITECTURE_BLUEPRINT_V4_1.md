# ChaCha DEV HUB — Architecture Blueprint v4.1

## Goal

Provide one reusable conception framework for every future project so no major layer is forgotten, from product definition to frontend, backend, data, security, delivery and operations.

The framework is technology-neutral. A project may be static web, SPA, API, worker, Python service, mobile app, data pipeline, Blender/Unity tooling, AI workflow, or a combination of several components.

## Core principle: project = composition of components

A project is not assumed to be monolithic.

Each project manifest may contain one or more components, for example:

- frontend-static
- frontend-spa
- backend-api
- backend-worker
- backend-job
- database
- cache
- queue
- object-storage
- ai-agent
- data-pipeline
- mobile
- desktop
- asset-pipeline
- docs

Each component declares its own path, runtime, dependencies, tests, build, deploy, health checks, artifacts and ownership.

## Reference architecture checklist

### 1. Product and domain

- problem / objective
- users and roles
- use cases
- functional requirements
- non-functional requirements
- acceptance criteria
- domain model
- glossary
- constraints and assumptions

### 2. Frontend

- rendering model: static / SPA / SSR / hybrid
- routes and navigation
- state management
- API client layer
- forms and validation
- error states
- loading states
- responsive/mobile behavior
- accessibility
- internationalization
- design system / components
- asset strategy
- caching
- offline/PWA where useful
- analytics and consent
- frontend tests
- browser compatibility
- performance budgets

### 3. Backend

- API contract
- service boundaries
- authentication
- authorization / RBAC / ABAC
- validation
- business logic
- persistence layer
- background jobs
- queues/events
- rate limiting
- idempotency
- retries and timeouts
- error model
- API versioning
- backend tests
- health/readiness endpoints

### 4. Data

- database choice
- schema and migrations
- indexing
- consistency requirements
- backup / restore
- retention
- archival
- data lifecycle
- object/blob storage
- cache
- search/indexing
- import/export
- data quality
- privacy classification

### 5. Security

- threat model
- secrets management
- least privilege
- dependency scanning
- SAST / linting
- input/output validation
- CSRF/XSS/SSRF protections where relevant
- CORS
- security headers
- audit logs
- encryption in transit / at rest
- access review
- incident response path

### 6. Integrations

- external APIs
- webhooks
- MCP servers
- IDE / coding agents
- GitHub
- Cloudflare
- documentation sources
- AI providers/models
- fallback providers
- quotas / limits
- credentials and scopes

### 7. Quality and testing

- static analysis
- formatting
- unit tests
- component tests
- integration tests
- contract tests
- end-to-end tests
- smoke tests
- regression tests
- performance tests
- security tests
- test fixtures/data
- coverage goals

### 8. Build and release

- deterministic setup
- lockfiles
- build command
- artifact generation
- versioning
- changelog
- release notes
- deployment environments
- dev / test / staging / production
- rollback strategy
- feature flags
- database migration strategy

### 9. CI/CD

- pull-request checks
- branch policy
- build validation
- test gates
- deploy gates
- artifact retention
- deployment status
- rollback hooks
- environment-specific secrets

### 10. Operations

- health checks
- logs
- metrics
- traces where useful
- alerts
- uptime checks
- error reporting
- dashboards
- capacity
- cost tracking
- quota tracking
- backups
- disaster recovery

### 11. Performance and scalability

- performance budgets
- latency targets
- caching strategy
- CDN
- database limits
- concurrency
- queue strategy
- horizontal/vertical scaling
- load-test thresholds
- graceful degradation

### 12. Documentation

- README
- architecture decision records (ADR)
- API docs
- runbooks
- deployment guide
- troubleshooting
- recovery procedure
- project manifest
- component inventory

### 13. Developer experience

- one-command bootstrap
- one-command health check
- one-command test
- one-command build
- one-command deploy where appropriate
- local/dev environment
- reproducible tool versions
- code intelligence/documentation connectors
- project templates

### 14. Storage strategy

The VPS is execution-oriented, not archive-oriented.

- source checkout and active toolchains may live on VPS
- large installers, archives, datasets, generated assets and backups should prefer NAS
- project manifests declare storage policy
- NAS connectivity is health-checked independently
- local cache must remain disposable where possible

## DEV HUB standard project model

```text
project
├── identity
├── repository
├── requirements
├── components[]
│   ├── identity
│   ├── path
│   ├── type
│   ├── runtime
│   ├── dependencies
│   ├── commands
│   │   ├── setup
│   │   ├── lint
│   │   ├── test
│   │   ├── build
│   │   ├── run
│   │   └── deploy
│   ├── interfaces
│   ├── data
│   ├── security
│   ├── observability
│   ├── health
│   └── artifacts
├── integrations
├── agents
├── knowledge
├── environments
├── storage
├── quality_gates
├── release
├── operations
└── governance
```

## Architecture gates

A project should not be considered production-ready until the relevant gates are explicitly marked OK or N/A:

1. PRODUCT
2. FRONTEND
3. BACKEND
4. DATA
5. SECURITY
6. INTEGRATIONS
7. TESTING
8. BUILD
9. CI_CD
10. OBSERVABILITY
11. PERFORMANCE
12. BACKUP_RECOVERY
13. DOCUMENTATION
14. OPERATIONS

This prevents a project from appearing complete merely because its application code works.

## Technology selection policy

The DEV HUB must not hard-code one framework as universally best.

Technology is selected per project using weighted criteria:

- fit for requirements
- maturity
- maintainability
- ecosystem
- security posture
- performance
- deployment compatibility
- documentation quality
- community/vendor health
- migration cost
- operational complexity
- total cost

The orchestrator may recommend a replacement when the expected benefit is material, but must never migrate production technology automatically without explicit approval.

## WfGg mapping

WfGg currently maps naturally to multiple components:

- `frontend/` → web frontend / static delivery
- `worker/` → Cloudflare Worker API
- Cloudflare D1 → relational persistence
- Cloudflare R2 → object storage
- GitHub → source control / CI source
- NAS → archives, artifacts, datasets and large storage
- MDN MCP → web platform reference
- Context7 MCP → library/framework reference
- Antigravity → coding agent
- Skywork Skills → specialized agent/skills layer

The next manifest version should describe those components independently rather than treating WfGg as a single build unit.
