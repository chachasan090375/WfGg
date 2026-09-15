# ChaCha DEV HUB — Project Control V1

Project Control is the single operator-facing control surface for a project. It does not replace the lifecycle, scheduler, run controller, evidence, state, or cryptographic engines; it delegates to them without bypassing their policies.

## Interfaces

Two interfaces share the same control engine:

- `dev-hub/bin/project-control.py`: human/operator CLI.
- `dev-hub/bin/project-control-api.py`: local JSON stdin/stdout adapter for agents and integrations.

There is deliberately no network listener in V1. A future HTTP/gRPC surface must be a separate, reviewed adapter and must not weaken approval boundaries.

## Canonical state

`/opt/chacha-dev/runtime/state/<project>/state.json` is the fast current-state projection. `audit.jsonl` remains the authoritative immutable history. Project Control reads the lifecycle stage from the control-plane projection and creates only an ephemeral compatibility state when invoking the existing lifecycle checker. It does not create a second persistent lifecycle truth.

## Project status

The public status model is:

- `READY`: the next lifecycle transition has no blockers.
- `BLOCKED`: one or more non-approval requirements are missing or invalid.
- `AWAITING_APPROVAL`: the only remaining blockers are explicit human approvals.
- `DEGRADED`: reserved for a future state where operation is possible with degraded providers/policy.
- `UNKNOWN`: canonical state is missing or cannot be established.
- `COMPLETE`: lifecycle is at `RETIRE`.

The response always carries the concrete blockers. Cryptographic release requirements are therefore visible as normal lifecycle blockers, e.g. missing signed checkpoint or trust-anchor quorum.

## Implemented operations

`status`, `explain`, `verify-state`, `plan-transition`, `schedule`, `prepare-run`, `dispatch`, and `crypto-verify` are implemented in V1.

`dispatch` requires an explicit `--execute` flag. Even with that flag, the Run Controller policy remains authoritative; while the Run Controller is `dispatch-only`, execution stays blocked. Project Control cannot enable execution by itself.

`verify-result`, `record-control-event`, and lifecycle `advance` are intentionally reserved for the next increment because they combine verified evidence and canonical state mutation and therefore need one transactional control path.

## CLI examples

```bash
python3 dev-hub/bin/project-control.py --repo-root . --json status --project wfgg

python3 dev-hub/bin/project-control.py --repo-root . --json plan-transition --project wfgg

python3 dev-hub/bin/project-control.py --repo-root . --json schedule --project wfgg
```

## Local JSON API

Request:

```json
{
  "schema": "chacha.dev/project-control-request/v1",
  "project": "wfgg",
  "operation": "status",
  "arguments": {}
}
```

Invocation:

```bash
cat request.json | python3 dev-hub/bin/project-control-api.py
```

Response schema: `chacha.dev/project-control-response/v1`.

The adapter maps structured request fields to structured argv. It never invokes a shell and never accepts arbitrary command strings.

## Security invariants

Project Control cannot return private signing-key material, cannot silently dispatch work, cannot perform an unsigned release, cannot manufacture human approval, and cannot mark unverified evidence successful. Cryptographic verification is delegated to `crypto-trust.py`; execution is delegated to `run-controller.py`; state integrity is delegated to `control-plane-store.py`.

## V1 architecture

```text
Human / Agent / IDE
        │
        ├── CLI
        └── local JSON API
                │
        PROJECT CONTROL
                │
   ┌────────────┼──────────────┐
   │            │              │
State Store  Lifecycle      Crypto Trust
   │            │              │
   └──────┬─────┴──────┬───────┘
          │            │
      Task Graph   Evidence Ledger
          │
      Scheduler
          │
     Run Controller
          │
       Adapters
```

Project Control is an orchestration facade, not a privileged bypass.
