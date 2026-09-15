# ChaCha DEV HUB — Adapter Provisioning & Promotion V1

Adapter Promotion is the controlled bridge between an adapter being merely designed and an adapter being allowed to execute.

The registry lifecycle remains:

`DESIGNED -> CONTRACT_OK -> PILOT -> ENABLED -> DEGRADED/DISABLED -> RETIRED`

The engine never runs a provider and never promotes automatically. It only evaluates recorded evidence and, with an explicit `apply` command plus `--apply`, performs an atomic registry mutation and writes a promotion receipt.

## Promotion requirements

The canonical transition requirements come from `dev-hub/config/adapter-contract.v1.json`:

- `DESIGNED -> CONTRACT_OK`: `static-contract-pass`
- `CONTRACT_OK -> PILOT`: `runtime-contract-pass` + `sandbox-only`
- `PILOT -> ENABLED`: `repeatable-pass` + `provider-health-pass` + `rollback-defined`
- degradation/disablement transitions require their corresponding health or policy evidence.

`PILOT`, `ENABLED` and `DEGRADED` require a concrete absolute executable path. This deliberately prevents a designed external/provider connector from becoming executable until an actual bridge/runtime adapter exists.

## Production-capable adapters

If an adapter exposes any protected production permission (`production-deploy`, `production-data-write`, `secret-change`, `destructive-operation`, `technology-replacement`), promotion to `ENABLED` also requires an explicit approval id. The approval must exist in the evidence document, identify the exact adapter and target status, and name a human actor.

The engine cannot manufacture that approval.

## Evidence

Input evidence uses `chacha.dev/adapter-promotion-evidence/v1`. Every required evidence item must be `PASS`, have a source, and be fresh under the promotion policy. Missing, stale, future-dated or failed evidence blocks the transition.

## CLI

Plan only:

```bash
python3 dev-hub/bin/adapter-promotion.py \
  --evidence /path/evidence.json \
  plan --adapter antigravity-adapter --target CONTRACT_OK
```

Apply to a registry only after the plan is eligible:

```bash
python3 dev-hub/bin/adapter-promotion.py \
  --registry /path/provider-adapters.v1.json \
  --evidence /path/evidence.json \
  apply --adapter antigravity-adapter --target CONTRACT_OK \
  --actor platform-engineer \
  --receipt /path/promotion-receipt.json \
  --apply
```

No `--apply`, no mutation.

## Provisioning

An executable binding can be supplied through `--executable`. Runtime statuses require it to be an absolute path. The binding and status change are committed in the same atomic registry write and captured in the receipt, so the runtime identity cannot silently drift away from the promotion record.

## Safety boundary

CI tests use temporary registry copies only. The branch registry remains unchanged until an explicit promotion is requested with evidence. This mechanism does not grant production deployment approval and does not change application production state.
