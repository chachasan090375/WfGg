# ChaCha DEV HUB — Reference Architecture V5

Status: DESIGN BASELINE

## 1. Objective

V5 turns the DEV HUB into a vendor-neutral development operating model rather than a collection of tools. Every project is described as components + capabilities + environments + quality gates. The framework must make missing bricks visible before production.

Core rules:

1. No vendor is hard-coded into the architecture. Tools are adapters behind capabilities.
2. Every project has one machine-readable manifest.
3. Every mandatory capability is OK, PARTIAL, MISSING, or NOT_APPLICABLE with an explicit reason.
4. No gate can be OK only because it is declared in the manifest; evidence is required.
5. No production technology is replaced automatically.
6. Code is authoritative in Git. Runtime workspace is disposable. Large/long-lived artifacts belong on NAS or cloud storage according to policy.
7. Architecture decisions are versioned as ADRs.
8. Non-functional requirements are first-class: security, performance, resilience, observability, recovery, accessibility, cost and operations.

## 2. Planes

### A. Control Plane

Central orchestration and policy layer.

- `architectctl`: architecture, audit, remediation, technology radar.
- `projectctl`: project lifecycle and component commands.
- policy engine: approvals, destructive-operation guards, production protections.
- capability registry: maps abstract capabilities to installed tools/connectors.
- scheduler: periodic health, radar, audit, backup/recovery drills.
- evidence store: audit reports, test results, architecture scores and decisions.

### B. Knowledge Plane

Sources used by humans and agents to reason with current information.

- MDN MCP — web platform documentation.
- Context7 MCP — current library/framework documentation.
- GitHub — source, issues, PRs, releases and project history.
- Technology Radar — official releases, vendor advisories, curated discovery.
- ADRs / runbooks / architecture docs.

Knowledge providers are replaceable adapters. Agents must record which source was used for consequential technical decisions.

### C. Execution Plane

Where work is executed.

- VPS: active workspace, toolchains, agents, builds, tests, short-lived caches.
- CI provider: repeatable remote verification and deployment pipelines.
- local/mobile terminal: operator access only, not authoritative build infrastructure.

Execution workspaces are reproducible and may be rebuilt from Git + manifest + secrets references.

### D. Storage Plane

Storage is tiered by purpose.

**Git**
- source code
- configuration
- manifests
- migrations
- test definitions
- documentation

**VPS local SSD**
- active checkout
- installed runtime/toolchain
- temporary build/test data
- bounded caches

**NAS**
- archives
- build artifacts
- datasets
- large assets
- recovery packages
- historical reports
- snapshots where appropriate

**Cloud runtime storage**
- production databases
- object storage
- queues/caches
- secrets/managed runtime state

Storage Governor decides whether an operation is allowed based on free space, projected usage and policy.

### E. Project Plane

Each project is an independent architecture described by a Manifest V3.

A project can contain any number of components:

- frontend-web
- frontend-mobile
- backend-api
- worker/edge
- service
- database
- object-storage
- cache
- queue/event-bus
- scheduled-job
- data-pipeline
- ai-agent
- cli
- desktop
- 3d/blender pipeline
- static-assets
- documentation site

Components declare dependencies on other components rather than relying on implicit folder conventions.

## 3. Full-stack capability model

Every project is evaluated against the following capability domains. A capability can be NOT_APPLICABLE only with a justification.

### 1. Product & Domain
- product objective
- users/personas
- functional requirements
- domain model
- acceptance criteria
- ownership

### 2. UX / Frontend
- information architecture
- responsive UI
- accessibility
- localization/i18n
- state management
- error/empty/loading states
- browser/device support
- client telemetry

### 3. API / Backend
- API contracts
- validation
- domain/application services
- error model
- idempotency where required
- pagination/rate limiting where required
- background jobs

### 4. Data
- schema/model
- migrations
- integrity constraints
- retention
- classification
- lifecycle
- backup/restore

### 5. Integrations
- external APIs
- webhooks
- queues/events
- retries/timeouts
- circuit breaking where relevant
- contract/version management

### 6. Identity & Security
- authentication
- authorization
- secrets management
- dependency scanning
- SAST / relevant security tests
- input/output protection
- CORS/CSP/security headers where relevant
- audit logging
- data protection/privacy requirements
- threat model for sensitive projects

### 7. Testing
- unit
- integration
- contract
- E2E
- smoke
- security
- performance/load where relevant
- regression
- test data strategy

### 8. Build & Dependency Management
- deterministic dependencies/lockfiles
- reproducible build
- artifact versioning
- SBOM when required
- dependency update policy

### 9. CI/CD & Release
- pull-request checks
- protected deployment path
- environment promotion
- rollback
- release/version strategy
- migrations orchestration

### 10. Environments & Infrastructure
- dev
- test/preview
- staging when needed
- production
- infrastructure/configuration as code where useful
- configuration separation
- secrets references

### 11. Observability
- structured logs
- metrics
- tracing where relevant
- dashboards
- alerting
- health/readiness checks
- business-critical telemetry

### 12. Performance
- budgets/SLOs
- caching strategy
- load/performance tests where needed
- frontend Web Vitals where applicable
- database query/performance controls
- capacity assumptions

### 13. Reliability & Resilience
- timeout/retry policy
- graceful degradation
- failure modes
- dependency outage behavior
- concurrency/idempotency controls
- availability targets

### 14. Backup & Disaster Recovery
- RPO
- RTO
- backup policy
- restore procedure
- tested restore evidence
- production recovery drill policy

### 15. Documentation
- README
- architecture overview
- ADRs
- API/schema documentation
- deployment notes
- runbooks
- developer onboarding

### 16. Operations / SRE
- incident runbook
- rollback procedure
- on-call/ownership where relevant
- quotas/limits
- certificate/domain lifecycle
- scheduled maintenance

### 17. FinOps / Capacity
- cost ownership
- cloud quotas
- storage growth
- resource budgets
- abnormal-cost alerts where relevant
- right-sizing policy

### 18. Governance / Compliance
- licenses
- dependency provenance
- data/privacy obligations
- retention policy
- approval rules
- audit evidence retention

## 4. Manifest V3

The manifest is the contract between project and DEV HUB.

Top-level sections:

- `identity`
- `repository`
- `ownership`
- `components`
- `dependencies`
- `environments`
- `capabilities`
- `quality_gates`
- `non_functional_requirements`
- `security`
- `data`
- `observability`
- `recovery`
- `delivery`
- `storage`
- `agents`
- `knowledge_sources`
- `technology_policy`
- `operations`

Each component declares:

- type
- path
- runtime
- framework
- package/dependency manager
- interfaces
- dependencies
- setup/check/test/build/run/deploy commands
- artifacts
- environment variables/secrets references
- observability hooks
- owner

## 5. Orchestration model — ChaCha Dev Architect

`ChaCha Dev Architect` is the coordinator, not a monolithic coding agent.

### Core responsibilities

1. Interpret project intent and manifest.
2. Detect which capabilities/components are involved.
3. Select tools and specialist agents from the capability registry.
4. Obtain current documentation through knowledge adapters when needed.
5. Produce a plan with risk and expected evidence.
6. Execute only operations permitted by policy.
7. Run verification gates.
8. Persist evidence and architecture decisions.
9. Generate remediation priorities.
10. Maintain the technology radar.

### Specialist roles

The coordinator can delegate to logical roles even if several roles are initially implemented by the same underlying model/tool:

- Product/Domain Architect
- Frontend Architect
- Backend/API Architect
- Data Architect
- Security Reviewer
- Test Engineer
- Platform/Cloud Engineer
- SRE/Observability Engineer
- Performance Engineer
- Recovery Engineer
- Release Engineer
- Documentation/ADR Agent
- Technology Radar Agent

Roles are capability-based, so replacing Antigravity, Skywork, or any future agent does not change project manifests.

## 6. Capability Registry

Example capabilities:

- `source-control`
- `code-edit`
- `code-review`
- `web-docs`
- `library-docs`
- `web-research`
- `cloud-deploy`
- `unit-test`
- `e2e-test`
- `security-scan`
- `performance-test`
- `browser-automation`
- `database-migrate`
- `artifact-store`
- `backup-store`
- `3d-pipeline`
- `technology-radar`

A registry entry contains provider, version, health, cost class, limits, data-access scope, alternatives and fallback.

## 7. Technology Radar policy

Technology surveillance separates discovery from recommendation.

Stages:

- DISCOVER — found on the market
- WATCH — potentially relevant
- ASSESS — evidence collection in progress
- PILOT — isolated proof of concept approved
- RECOMMEND — comparative evidence supports adoption
- ADOPT — approved default
- DEPRECATE — planned removal
- RETIRE — no longer permitted

Promotion requires evidence appropriate to risk. GitHub stars/activity can be discovery signals but never sufficient for PILOT/RECOMMEND.

Comparison dimensions:

- functionality
- quality
- maturity
- security
- maintainability
- documentation
- ecosystem
- performance
- resource consumption
- integration cost
- migration cost
- rollback quality
- vendor lock-in
- financial cost

No production replacement is automatic.

## 8. Quality gates

A gate result contains:

- status: OK / PARTIAL / MISSING / NOT_APPLICABLE
- score
- evidence[]
- missing[]
- risks[]
- remediation[]
- last_verified_at
- verification_method

Project-level readiness must not be reduced to one score. The score is informational; blocking policies use explicit critical gates.

Example production blockers:

- unresolved critical security risk
- build/test failure
- missing deployment rollback for risky changes
- unavailable required backup/recovery evidence for stateful production components
- missing production secrets/configuration

## 9. Golden Paths

V5 should offer reusable reference templates instead of one universal stack.

Initial golden paths:

1. Static/PWA + edge API + managed database/object storage.
2. SPA/SSR frontend + API service + SQL database.
3. Worker/serverless API.
4. Python service/API.
5. Data pipeline/batch job.
6. AI-enabled service with model/provider abstraction.
7. 3D/asset processing pipeline.

Each golden path declares recommended defaults but remains replaceable through the capability registry.

## 10. Project lifecycle

`IDEA -> DESIGN -> BOOTSTRAP -> DEVELOP -> VERIFY -> PREVIEW -> RELEASE -> OPERATE -> IMPROVE -> RETIRE`

At each transition, required evidence is defined. Agents may automate evidence collection but may not forge or infer successful verification.

## 11. WfGg as first reference implementation

Current WfGg component model:

- frontend: Web/PWA
- api: Cloudflare Worker
- database: D1
- object storage: R2

WfGg is the first adopter, not a special case. DEV HUB itself must remain able to onboard unrelated future projects without WfGg-specific logic.

## 12. V5 implementation order

1. Freeze this reference architecture as the design contract.
2. Define Manifest V3 JSON Schema.
3. Implement capability registry.
4. Refactor project/component discovery against Manifest V3.
5. Expand evidence gates from 14 to the 18 capability domains above.
6. Implement specialist-agent routing.
7. Add remediation planner with dependency ordering.
8. Add golden-path templates.
9. Add environment/promotion model.
10. Add architecture graph and dependency graph.
11. Add dashboard/report export.
12. Migrate WfGg V2 manifest to V3 without changing production.

## 13. Definition of success

The framework is considered structurally complete when a brand-new project can be registered with only its repository and intent, after which DEV HUB can:

- discover or propose components;
- identify missing architecture capabilities;
- generate a Manifest V3 proposal;
- select appropriate tools/agents;
- build a safe implementation plan;
- verify code and infrastructure with evidence;
- manage artifacts/storage correctly;
- produce release and recovery readiness reports;
- monitor installed technology and suggest evidence-backed alternatives;
- remain usable if individual vendors/tools are replaced.
