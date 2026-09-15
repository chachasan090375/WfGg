# ChaCha DEV HUB — Adapter Runtime Activation V1

Runtime Activation is the controlled bridge between a repository adapter that is `CONTRACT_OK` and a host installation that is ready to be promoted to `PILOT`.

It does **not** directly mutate the canonical `provider-adapters.v1.json`. A successful activation means `READY_FOR_PROMOTION`, not `PILOT`.

## Sequence

```text
CONTRACT_OK
   |
   +-- verified base evidence
   |
   +-- provision exact bytes on VPS
   |
   +-- verify source -> installed -> executable SHA-256 equality
   |
   +-- bind provisioning receipt into promotion evidence
   |
   +-- run promotion eligibility plan
   v
READY_FOR_PROMOTION
```

The final repository promotion remains a separate authorization step.

## Safety properties

- explicit `--apply` required;
- local/VPS adapters only;
- per-adapter host lock, no concurrent activation writer;
- existing `current` symlink captured before mutation;
- failed provisioning, verification, evidence binding, or promotion eligibility restores the previous symlink;
- rollback never deletes the versioned installation directory;
- subprocesses use argv and `shell=False`;
- canonical provider-adapter registry is read-only to this orchestrator;
- activation receipts contain paths, digests and bounded process output, never private key material;
- stale activation locks are never removed automatically.

## Plan

```bash
python3 dev-hub/bin/adapter-runtime-activation.py \
  --adapter http-smoke-adapter \
  --base-evidence /path/to/http-smoke-base-evidence.json \
  plan
```

## Apply on the DEV HUB host

```bash
python3 dev-hub/bin/adapter-runtime-activation.py \
  --adapter http-smoke-adapter \
  --base-evidence /path/to/http-smoke-base-evidence.json \
  apply \
  --actor platform-cloud-engineer \
  --work-dir /opt/chacha-dev/runtime/adapter-activation/http-smoke-1.0.0 \
  --apply
```

The result directory contains:

- `provisioning-receipt.json`;
- `promotion-evidence.json`;
- `promotion-plan.json`;
- `activation-receipt.json`.

If `activation-receipt.json.status` is `READY_FOR_PROMOTION`, the executable is provisioned and the promotion engine found the exact `CONTRACT_OK -> PILOT` transition eligible. The registry has still not been mutated.

## Sandbox / CI

CI passes `--root <temporary-directory>` so no `/opt/chacha-dev` path is touched. A synthetic but schema-correct base evidence file is used only to test orchestration mechanics. It does not certify the real VPS.

## Final promotion boundary

The canonical adapter may be changed to `PILOT` only after the real host activation receipt and promotion evidence are reviewed and their executable path/digest still match the provisioned runtime.
