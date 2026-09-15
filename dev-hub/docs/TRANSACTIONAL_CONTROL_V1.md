# ChaCha DEV HUB — Transactional Control V1

Transactional Control closes the gap between lifecycle checks, verified evidence, the Evidence Ledger, and the canonical Control Plane State.

## Authority model

The append-only audit journal remains the authoritative history. `state.json` is the fast projection of that history. The persistent lifecycle stage is stored only inside the Control Plane projection; `lifecycle-engine.py` is used as a deterministic eligibility checker and does not own a second persistent lifecycle state.

Project Control serializes mutating control operations with a per-project file lock and verifies the Control Plane before a mutation. Lifecycle promotion re-runs the lifecycle checker against the current Evidence Ledger while the lock is held, captures the current projection version and journal head, then writes one `LIFECYCLE_TRANSITION` audit event carrying the evidence-ledger digest and a state patch. The resulting projection and hash chain are verified again before the transaction is reported committed.

## Lifecycle advance

The logical commit is:

```text
current projection + current journal
              |
              v
       integrity verification
              |
              v
      lifecycle requirements
 evidence + gates + approvals
              |
              v
        PREPARED receipt
              |
              v
 LIFECYCLE_TRANSITION audit event
              |
              v
      atomic state projection
              |
              v
       integrity re-verification
              |
              v
        COMMITTED receipt
```

The transaction records the transition, actor, evidence-ledger digest, pre-commit version, pre-commit journal head, resulting event sequence and resulting event digest. If post-commit verification is inconclusive the receipt becomes `COMMIT_UNCERTAIN` and further promotion is blocked.

Release boundaries are not weakened by Transactional Control. `PREVIEW -> RELEASE` still requires the signed Ed25519 release checkpoint, external trust-anchor quorum and explicit production approval defined by Lifecycle policy before the transaction can begin.

## Verified evidence ingestion

`verify-result` first delegates to the Independent Verification Broker. Verification by itself is read-only and produces a verification report plus an immutable verified Task Result.

With explicit `--ingest`, the Evidence Ledger update uses a recoverable journal-first protocol:

```text
Task Result
   |
Independent Verification
   |
verified Task Result
   |
copy current ledger -> staged ledger
   |
Evidence Collector updates staged ledger
   |
PREPARED receipt + old/new ledger digests
   |
EVIDENCE_RECORDED audit event
   |
atomic staged-ledger -> live-ledger finalize
   |
COMMITTED receipt
```

If the audit event is committed but ledger finalization fails, the staged ledger is retained and the receipt becomes `CONTROL_EVENT_COMMITTED_LEDGER_PENDING`. Project status then blocks promotion until recovery. This prevents a partial write from being silently treated as success.

## Generic control events

`record-control-event` is available for ordinary audited state/control records, but it is not a bypass. Protected events such as lifecycle transitions, approvals, risk acceptance, key activation/rotation/revocation and project retirement are rejected by the generic path. Generic patches also cannot directly modify protected `lifecycle` or `approvals` state sections.

## Transaction receipts

Receipts use `chacha.dev/control-transaction-receipt/v1` and live under:

```text
/opt/chacha-dev/runtime/transactions/<project>/<transaction-id>/receipt.json
```

Important states are `PREPARED`, `VERIFIED_ONLY`, `CONTROL_EVENT_COMMITTED_LEDGER_PENDING`, `COMMIT_UNCERTAIN`, `COMMITTED`, and `FAILED`.

`PREPARED`, `CONTROL_EVENT_COMMITTED_LEDGER_PENDING`, and `COMMIT_UNCERTAIN` are blocking states. Project Control surfaces them as concrete blockers rather than hiding them.

## Unified CLI examples

```bash
python3 dev-hub/bin/project-control.py --repo-root . --json \
  verify-result --project wfgg --result result.json --graph graph.json

python3 dev-hub/bin/project-control.py --repo-root . --json \
  verify-result --project wfgg --result result.json --graph graph.json --ingest

python3 dev-hub/bin/project-control.py --repo-root . --json \
  advance --project wfgg --target PREVIEW --actor project-owner
```

No command above enables production execution by itself. Run Controller, Lifecycle approval requirements, Cryptographic Trust policy and human approval boundaries remain authoritative.
