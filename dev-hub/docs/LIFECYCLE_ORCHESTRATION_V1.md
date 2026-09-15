# ChaCha DEV HUB — Lifecycle & Orchestration V1

This layer turns the V5 architecture model into a controlled project lifecycle. It does not deploy anything by itself. It decides whether a project is allowed to progress and records why.

## State machine

`IDEA -> DESIGN -> READY -> BUILD -> VERIFY -> PREVIEW -> RELEASE -> OPERATE -> RETIRE`

Normal stage skipping is forbidden. Every transition is evidence-driven.

### IDEA

Purpose: define the problem before choosing a stack.

Required exit evidence:
- Project Intent.

### DESIGN

Purpose: transform intent into architecture.

Required exit evidence:
- Project Plan;
- Manifest V3;
- successful manifest validation;
- capability/provider resolution;
- required architecture decisions resolved.

No implementation should begin while a required architectural decision is unresolved.

### READY

Purpose: prove that the development environment can safely execute the plan.

Required exit evidence:
- workspace health;
- storage preflight;
- dependency resolution.

Heavy operations must pass Storage Governor preflight.

### BUILD

Purpose: implement a bounded change set.

Required exit evidence:
- recorded change set;
- reproducible build result;
- static/syntax/type checks as applicable.

### VERIFY

Purpose: challenge the build independently of the implementation claim.

Required exit evidence:
- test execution result;
- security scan;
- CI result;
- preview candidate.

The identity/security, testing, build/dependency and CI/CD gates must be `OK` or justified `NOT_APPLICABLE` before PREVIEW.

### PREVIEW

Purpose: validate the release candidate outside production.

Required exit evidence includes E2E, smoke, preview validation, rollback plan, release traceability and backup/recovery readiness.

Promotion to RELEASE additionally requires an explicit `production-release` approval. An agent must never infer this approval.

### RELEASE

Purpose: perform the explicitly approved production promotion and capture its receipt.

Required exit evidence for OPERATE:
- production deployment receipt;
- post-deploy smoke result;
- production health;
- observability health.

### OPERATE

Purpose: run, observe, recover, maintain and continuously reassess technology choices.

The Technology Radar operates here as an advisory capability. It can propose alternatives but cannot replace a production technology automatically.

### RETIRE

Purpose: deliberately remove a system or component without losing required data or operational knowledge.

Retirement requires explicit approval plus archive, data disposition and dependency-retirement evidence.

## Evidence contract

Lifecycle claims are stored in an Evidence Ledger. A successful claim must identify its source and observation time. Generated prose or an agent statement without execution is `UNVERIFIED` and cannot unlock a transition.

Gate statuses remain:

`OK | PARTIAL | MISSING | NOT_APPLICABLE | UNVERIFIED`

For release, blocking gates accept only `OK` or justified `NOT_APPLICABLE`. A non-blocking `PARTIAL` gate requires an explicit risk acceptance if release policy allows it.

## Orchestration model

The ChaCha Dev Architect is the orchestrator. Specialist roles perform bounded tasks but cannot promote their own project stage.

The orchestration policy separates permissions:

- `read`
- `plan`
- `workspace-write`
- `repository-write`
- `preview-deploy`
- `production-deploy`
- `production-data-write`
- `secret-change`
- `destructive-operation`
- `technology-replacement`

Production deployment, production-data mutation, secret changes, destructive operations and technology replacements require explicit human approval.

Only one write-capable specialist should mutate a project at a time. Read-only research and audit tasks may run in parallel.

## Provider abstraction

Lifecycle requirements describe capabilities, not brands. The Capability Registry resolves the current provider. A provider may be `ADOPT`, `PILOT`, `WATCH`, etc.; conditional providers must remain conditional until evidence justifies promotion.

## Engine

`dev-hub/bin/lifecycle-engine.py` supports:

```bash
python3 dev-hub/bin/lifecycle-engine.py init \
  --project wfgg \
  --state /tmp/wfgg.lifecycle.json

python3 dev-hub/bin/lifecycle-engine.py status \
  --state /tmp/wfgg.lifecycle.json

python3 dev-hub/bin/lifecycle-engine.py check \
  --state /tmp/wfgg.lifecycle.json \
  --target DESIGN \
  --evidence /tmp/wfgg.evidence.json

python3 dev-hub/bin/lifecycle-engine.py advance \
  --state /tmp/wfgg.lifecycle.json \
  --target DESIGN \
  --evidence /tmp/wfgg.evidence.json \
  --actor project-owner
```

`check` never mutates state. `advance --dry-run` proves that a promotion would be accepted without writing the state file.

## Separation of concerns

The V5 control flow is now:

```text
Project Intent
      |
      v
Project Planner
      |
      v
Project Plan + Manifest V3
      |
      v
Manifest Engine
      |
      v
Lifecycle Engine <---- Evidence Ledger
      |                       ^
      v                       |
ChaCha Dev Architect ---- Specialist Agents
      |
      v
Capability Registry ---- Tool / MCP / IDE providers
```

The orchestrator decides *who should do the work*. The Lifecycle Engine decides *whether the evidence permits progression*. The Capability Registry decides *which provider supplies a capability*. These responsibilities must stay separate.

## Emergency changes

The lifecycle configuration defines a hotfix path for an already-operated service. It still requires an incident reference, production approval and post-hoc evidence. Emergency mode is not a general bypass.

## Next layer

The next architectural layer is the Evidence Collector / Task Graph: converting lifecycle requirements into executable specialist tasks, collecting machine-verifiable outputs, and feeding those results back into the ledger without allowing agents to self-certify success.
