# ChaCha DEV HUB — Platform Readiness / Certification Gate V1

Platform Readiness answers one controlled question from evidence rather than declarations:

```text
DEV HUB READY FOR EXECUTION = YES / NO
```

The gate is read-only. It does not enable an adapter, dispatch a task, generate or read private signing keys, create a human approval, change a provider binding, or mutate production.

## Three profiles

`contract` verifies that the architecture itself is internally executable as a design: repository JSON/Python contracts parse, the Adapter Contract Harness passes its static checks, and the full sandbox Recovery Drill passes. A successful contract profile is **not** authorization to execute runtime tasks, so `ready_for_execution` remains `NO` by design.

`development` inherits the contract checks and additionally requires a valid Control Plane hash chain/projection, no pending control transaction, a provider-health snapshot, a successful Storage Governor preflight, runtime-capable adapter coverage for `read`, `plan` and `workspace-write`, and an execution-enabled Run Controller.

`production` inherits development readiness and additionally requires ENABLED adapter coverage for repository/production deployment, a HEALTHY Ed25519 signing provider with an ENABLED crypto adapter, two independent healthy/enabled trust anchors, and intact explicit-human production approval boundaries.

## Evidence aggregation

```text
Repository contracts ─────────┐
Adapter contract ─────────────┤
Recovery fault injection ─────┤
Control Plane integrity ──────┤
Pending transactions ─────────┤
Provider health ──────────────┤
Storage preflight ────────────┤
Adapter runtime coverage ─────┤──> Platform Readiness Gate
Run Controller mode ──────────┤              │
Ed25519 runtime ──────────────┤              ├── YES
Trust anchors ────────────────┤              └── NO + exact blockers
Human approval boundaries ────┘
```

`UNKNOWN` is never treated as ready. Missing runtime evidence therefore blocks development/production certification instead of silently passing.

## Current architectural consequence

The current Provider Adapter Registry intentionally keeps adapters at `DESIGNED`, and Run Controller remains `dispatch-only`. Therefore a contract certification can pass while runtime certification correctly returns `NO`. This is expected: architecture definition and recovery safety can be proven before runtime adapters are provisioned and explicitly promoted.

Adapter promotion remains governed by `adapter-contract.v1.json`; Platform Readiness only observes the resulting status. It cannot promote adapters itself.

## Recovery requirement

Recovery readiness is not inferred from documentation. The contract profile requires a `chacha.dev/recovery-drill-report/v1` with the five fault-injection scenarios passing. The gate can run that sandbox suite itself with `--run-recovery-drill` or consume a previously generated report.

## CLI

Contract certification in an isolated environment:

```bash
python3 dev-hub/bin/platform-readiness.py \
  --repo-root . \
  --profile contract \
  --run-recovery-drill \
  --json
```

Development runtime certification later on the DEV HUB host:

```bash
python3 dev-hub/bin/platform-readiness.py \
  --repo-root . \
  --profile development \
  --project wfgg \
  --provider-health /opt/chacha-dev/runtime/health/wfgg/providers.json \
  --storage-preflight /opt/chacha-dev/runtime/evidence/wfgg/storage-preflight.json \
  --run-recovery-drill \
  --json
```

The machine-readable output schema is `chacha.dev/platform-readiness-report/v1`.

## Project Control

Platform Readiness is exposed through the Unified Project Control surface as `platform-readiness`. The local JSON API may request the same read-only certification. Neither interface changes the underlying readiness rules.

## Boundary with application recovery

The sandbox Recovery Drill validates the DEV HUB Control Plane transaction/reconciliation machinery. It does not certify restoration of a project's real production database or object store. Application production restore evidence remains part of the project's `backup-recovery` quality gate.
