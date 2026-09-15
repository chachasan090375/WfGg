# ChaCha DEV HUB — Project Control V1.2

Project Control is the single operator-facing control surface for a project. It does not replace the lifecycle, scheduler, run controller, evidence, state, verification, recovery, or cryptographic engines; it delegates to them without bypassing their policies.

## Interfaces

Two interfaces share the same unified router:

- `dev-hub/bin/project-control-cli.py`: human/operator CLI router. Standard operations delegate to `project-control.py`; recovery operations delegate to `transaction-recovery.py`.
- `dev-hub/bin/project-control-api.py`: local JSON stdin/stdout adapter for agents and integrations; it invokes the same CLI router.

There is deliberately no network listener. A future HTTP/gRPC surface must be a separate reviewed adapter and must not weaken approval boundaries.

## Canonical state

`/opt/chacha-dev/runtime/state/<project>/state.json` is the fast current-state projection. `audit.jsonl` remains the authoritative append-only history. Project Control reads the lifecycle stage from the Control Plane projection and creates only an ephemeral compatibility state when invoking the lifecycle checker. There is no second persistent lifecycle truth.

## Project status

The public status model is:

- `READY`: the next lifecycle transition has no blockers.
- `BLOCKED`: one or more non-approval requirements are missing, invalid, or a control transaction requires recovery.
- `AWAITING_APPROVAL`: the only remaining blockers are explicit human approvals.
- `DEGRADED`: reserved for operation that remains possible under an explicitly accepted degraded policy.
- `UNKNOWN`: canonical state is missing or cannot be established.
- `COMPLETE`: lifecycle is at `RETIRE`.

The response always carries concrete blockers. Cryptographic release requirements therefore appear like any other lifecycle blocker, for example a missing signed checkpoint or trust-anchor quorum.

## Implemented operations

Project Control now implements `status`, `explain`, `verify-state`, `transactions`, `recover-transaction`, `plan-transition`, `schedule`, `prepare-run`, `dispatch`, `verify-result`, `record-control-event`, `advance`, and `crypto-verify`.

`transactions` is read-only. It lists control transaction receipts and reports whether any transaction is still blocking lifecycle promotion.

`recover-transaction` is inspect-only unless `--apply` is explicit. Recovery is forward-only: it may rebuild a stale state projection from a valid authoritative journal or finalize a staged Evidence Ledger when the expected digests match, but it never rewrites or rolls back an audit event. Ambiguous states return `MANUAL_REVIEW`. See `TRANSACTION_RECOVERY_V1.md`.

`dispatch` requires explicit `--execute`. Even with that flag, Run Controller policy remains authoritative; while the Run Controller is `dispatch-only`, execution stays blocked.

`verify-result` delegates to the Independent Verification Broker. Without `--ingest` it is read-only. With explicit `--ingest`, the verified Task Result is first applied to a staged copy of the Evidence Ledger, then linked to an `EVIDENCE_RECORDED` audit event, and finally atomically finalized into the live ledger. Partial commits remain recoverable and visible through transaction receipts.

`advance` is the only generic Project Control path for persistent lifecycle promotion. It rechecks Control Plane integrity, lifecycle evidence, quality gates and approvals under a per-project lock. It then records one `LIFECYCLE_TRANSITION` audit event carrying the evidence-ledger digest and applies the lifecycle state patch through the Control Plane Store. Post-commit integrity is rechecked before success is reported.

`record-control-event` is not a bypass. Protected event types and protected lifecycle/approval state sections are rejected and require dedicated controlled operations.

## Transaction receipts

Mutating multi-step control work is tracked under:

```text
/opt/chacha-dev/runtime/transactions/<project>/<transaction-id>/receipt.json
```

The receipt schema is `chacha.dev/control-transaction-receipt/v1`. Incomplete states such as `PREPARED`, `CONTROL_EVENT_COMMITTED_LEDGER_PENDING`, or `COMMIT_UNCERTAIN` block further lifecycle promotion until reconciled. Recovery closes a safely recovered transaction as `COMMITTED`, or a transaction that never crossed the authoritative commit boundary as `FAILED`, and appends a `recovery_history` entry to the receipt.

## CLI examples

```bash
python3 dev-hub/bin/project-control-cli.py --repo-root . --json status --project wfgg

python3 dev-hub/bin/project-control-cli.py --repo-root . --json transactions --project wfgg

python3 dev-hub/bin/project-control-cli.py --repo-root . --json \
  recover-transaction --project wfgg --transaction-id ctx-123

python3 dev-hub/bin/project-control-cli.py --repo-root . --json \
  recover-transaction --project wfgg --transaction-id ctx-123 --apply --actor recovery-engineer

python3 dev-hub/bin/project-control-cli.py --repo-root . --json verify-result \
  --project wfgg --result result.json --graph graph.json --ingest

python3 dev-hub/bin/project-control-cli.py --repo-root . --json advance \
  --project wfgg --target PREVIEW --actor project-owner
```

## Local JSON API

Request:

```json
{
  "schema": "chacha.dev/project-control-request/v1",
  "project": "wfgg",
  "operation": "recover-transaction",
  "arguments": {
    "transaction_id": "ctx-123",
    "apply": false
  }
}
```

Invocation:

```bash
cat request.json | python3 dev-hub/bin/project-control-api.py
```

Response schema: `chacha.dev/project-control-response/v1`.

The adapter maps structured request fields to structured argv. It never invokes a shell and never accepts arbitrary command strings. Agent-facing JSON requests cannot assert human verification, and recovery cannot mutate unless `apply=true` is explicit.

## Security invariants

Project Control cannot return private signing-key material, cannot silently dispatch work, cannot perform an unsigned release, cannot manufacture human approval, cannot promote with missing required evidence, cannot mark unverified evidence successful, and cannot rewrite authoritative audit history during recovery. Cryptographic verification is delegated to `crypto-trust.py`; execution to `run-controller.py`; independent result verification to `verification-broker.py`; evidence admission to `evidence-collector.py`; canonical state mutation/integrity to `control-plane-store.py`; and interrupted-transaction reconciliation to `transaction-recovery.py`.

## Architecture

```text
Human / Agent / IDE
        |
        +-- unified CLI router
        +-- local JSON API
                |
        PROJECT CONTROL
                |
      transaction / lock layer
                |
   +------------+---------------------+
   |            |                     |
State Store  Lifecycle        Transaction Recovery
   |            |                     |
   +------+-----+----------+----------+
          |                |
      Task Graph       Verification
          |                |
      Scheduler        Evidence Ledger
          |                |
     Run Controller   Crypto Trust
          |
       Adapters
```

Project Control is an orchestration facade, transaction boundary, and recovery entry point — not a privileged bypass.
