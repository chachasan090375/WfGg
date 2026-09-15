# ChaCha DEV HUB — Transaction Recovery & Reconciliation V1

Transaction Recovery handles interrupted Project Control transactions without weakening the append-only audit model. The audit journal remains authoritative. Recovery may repair derived projections or finalize a staged Evidence Ledger, but it never rewrites, deletes, truncates, or rolls back an audit event.

## Public operations

The unified Project Control CLI now exposes:

```text
transactions
recover-transaction
```

`transactions` is read-only and lists transaction receipts plus whether they block further lifecycle promotion.

`recover-transaction` is inspect-only by default. It performs a mutation only with an explicit `--apply`. The local JSON API follows the same rule: `apply=true` must be present for recovery to mutate runtime data.

## Recovery authority

Recovery decisions use this precedence:

```text
valid audit journal
      ↓
authoritative transaction event
      ↓
derived state projection / Evidence Ledger
      ↓
transaction receipt
```

A receipt cannot override an authoritative event. Conversely, a `PREPARED` receipt with no matching authoritative event can be safely closed as an aborted transaction after journal integrity is confirmed.

## Advance recovery

For `advance`, the engine searches the verified audit journal for the transaction's `LIFECYCLE_TRANSITION` event.

- No event: the transaction never crossed the authoritative commit boundary. Recovery may rebuild a stale projection from the journal and closes the receipt as `FAILED` with recovery outcome `ABORTED_BEFORE_AUTHORITATIVE_COMMIT`.
- Event present: the transition is authoritative. If the projection is stale, it is rebuilt from the verified journal. The receipt is then closed as `COMMITTED` with recovery outcome `RECOVERED_FROM_AUTHORITATIVE_EVENT`.
- Multiple or contradictory authoritative events: automatic recovery stops and reports `MANUAL_REVIEW`.

No committed lifecycle event is ever rolled back.

## Evidence Ledger recovery

For `verify-result --ingest`, the engine searches for the transaction's `EVIDENCE_RECORDED` event and compares three canonical SHA-256 digests: old live ledger, staged ledger, and expected new ledger.

Safe automatic finalization requires:

```text
EVIDENCE_RECORDED exists
AND journal chain is valid
AND live ledger digest == expected old digest
AND staged ledger digest == expected new digest
```

Only then may `--apply` atomically replace the live ledger with the staged ledger.

If the live ledger already equals the expected new digest, recovery simply closes the receipt as `COMMITTED` with outcome `LEDGER_ALREADY_FINALIZED`. If the live digest is neither the expected old nor expected new digest, recovery refuses to overwrite it and returns `MANUAL_REVIEW`.

Staged recovery files are never deleted automatically.

## Projection repair

A state projection may be rebuilt only when the audit journal itself verifies. Rebuild delegates to `control-plane-store.py`; the journal is not altered. This is reconciliation of a derived view, not history rewriting.

## Assessments

The recovery report uses:

```text
TERMINAL
SAFE_TO_ABORT
SAFE_TO_FINALIZE
ALREADY_EFFECTIVE
REPAIRABLE
MANUAL_REVIEW
INVALID
```

`MANUAL_REVIEW` and `INVALID` never apply mutations automatically.

## Transaction receipt closure

The existing receipt schema remains compatible. Recovery closes successful reconciliations with `status=COMMITTED` and aborted pre-commit transactions with `status=FAILED`. A `recovery_outcome` and append-only `recovery_history` are added to the receipt. This preserves the existing rule that only `PREPARED`, `CONTROL_EVENT_COMMITTED_LEDGER_PENDING`, and `COMMIT_UNCERTAIN` remain blocking.

## Safety invariants

- no audit-event deletion;
- no journal truncation;
- no implicit recovery;
- no blind ledger overwrite;
- no projection rebuild from an invalid journal;
- no deletion of staged recovery evidence;
- per-project recovery serialization;
- ambiguous states require manual review.

## Examples

```bash
python3 dev-hub/bin/project-control-cli.py --repo-root . --json \
  transactions --project wfgg

python3 dev-hub/bin/project-control-cli.py --repo-root . --json \
  recover-transaction --project wfgg --transaction-id ctx-123

python3 dev-hub/bin/project-control-cli.py --repo-root . --json \
  recover-transaction --project wfgg --transaction-id ctx-123 --apply --actor recovery-engineer
```

The first two commands are read-only. Only the final command is allowed to reconcile runtime data.
