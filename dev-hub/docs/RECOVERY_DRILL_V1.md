# ChaCha DEV HUB — Recovery Drill & Fault Injection V1

Recovery Drill proves that the Control Plane can survive incomplete transactions without rewriting authoritative history.

The harness is deliberately **sandbox-only**. It derives temporary Control Plane and Transaction Recovery policies whose runtime roots point to an isolated temporary directory. It refuses roots under the real DEV HUB runtime and NAS paths defined by policy.

## Scenarios

The first drill suite contains five fault classes:

1. `prepared-before-authority` — transaction receipt exists but no authoritative audit event was written. Expected recovery: safe abort and receipt closure as `FAILED`.
2. `journal-before-projection` — `LIFECYCLE_TRANSITION` is durably present in the audit journal but `state.json` is stale. Expected recovery: rebuild projection from the valid journal and close the receipt as `COMMITTED`.
3. `evidence-before-ledger-finalize` — `EVIDENCE_RECORDED` is authoritative but the live Evidence Ledger still has its old digest. Expected recovery: verify old/new/staged digests, rebuild projection if needed, atomically finalize the staged Ledger, then close the receipt as `COMMITTED`.
4. `tampered-journal` — an existing audit event is modified without recomputing its digest. Expected behavior: classify the transaction `INVALID`, expose `AUDIT_JOURNAL_INVALID`, and refuse automatic recovery.
5. `divergent-ledger` — the live Ledger matches neither the declared old digest nor the staged new digest. Expected behavior: `MANUAL_REVIEW`; the live Ledger must not be overwritten.

## Safety model

Fault injection never runs against `/opt/chacha-dev/runtime` or the NAS DEV HUB root. The harness creates synthetic projects and transaction receipts only inside the drill sandbox. It does not deploy, call cloud providers, touch production data, generate signing keys, or mutate Git repositories.

The drill tests the same production recovery code (`transaction-recovery.py`) and the same Control Plane event format/hash-chain implementation (`control-plane-store.py`). The fault injector itself may deliberately append a valid authoritative event without updating the projection in order to model a crash between those two durability boundaries.

## Success criteria

A drill is `PASS` only when all selected scenarios pass. Recoverable partial commits must finish with a valid audit chain and consistent projection. Tampered history must be detected, not repaired. Divergent Evidence Ledger state must require manual review, not blind overwrite.

The machine-readable result uses `chacha.dev/recovery-drill-report/v1`.

## CLI

```bash
python3 dev-hub/bin/recovery-drill.py --repo-root . run --scenario all
```

To retain the synthetic sandbox for inspection:

```bash
python3 dev-hub/bin/recovery-drill.py --repo-root . --keep-workdir run --scenario all
```

CI runs the full suite on branch `dev-hub-v5.0`. This is recovery evidence for the DEV HUB architecture itself; it is not evidence that an application project's production data restore has been tested. Production restore drills remain a separate Recovery gate.
