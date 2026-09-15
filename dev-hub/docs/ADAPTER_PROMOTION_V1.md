# ChaCha DEV HUB — Adapter Provisioning & Promotion V1

Adapter Promotion is the controlled bridge between an adapter being merely designed and an adapter being allowed to execute.

The registry lifecycle remains:

`DESIGNED -> CONTRACT_OK -> PILOT -> ENABLED -> DEGRADED/DISABLED -> RETIRED`

The promotion engine never runs a provider and never promotes automatically. It evaluates recorded evidence and, only with an explicit `apply` command plus `--apply`, performs an atomic registry mutation and writes a promotion receipt.

Runtime installation is handled separately by `adapter-provision.py`. That separation prevents installation side effects from silently changing authorization state.

## Promotion requirements

The canonical transition requirements come from `dev-hub/config/adapter-contract.v1.json`:

- `DESIGNED -> CONTRACT_OK`: `static-contract-pass`
- `CONTRACT_OK -> PILOT`: `runtime-contract-pass` + `sandbox-only` + `provisioning-pass`
- `PILOT -> ENABLED`: `repeatable-pass` + `provider-health-pass` + `rollback-defined`
- degradation/disablement transitions require their corresponding health or policy evidence.

For VPS/local adapters, `provisioning-pass` is derived from a concrete `chacha.dev/adapter-provisioning-receipt/v1` and binds the installed executable path and digest. For external-only adapters, it is provider-specific evidence that the external runtime binding exists; no local executable is invented.

`PILOT`, `ENABLED` and `DEGRADED` require a concrete absolute executable path only for execution kinds configured as local/VPS. External-only adapters keep `executable=null`.

## Production-capable adapters

If an adapter exposes any protected production permission (`production-deploy`, `production-data-write`, `secret-change`, `destructive-operation`, `technology-replacement`), promotion to `ENABLED` also requires an explicit approval id. The approval must exist in the evidence document, identify the exact adapter and target status, and name a human actor.

The engine cannot manufacture that approval.

## Evidence

Input evidence uses `chacha.dev/adapter-promotion-evidence/v1`. Every required evidence item must be `PASS`, have a source, and be fresh under the promotion policy. Missing, stale, future-dated or failed evidence blocks the transition.

For local adapters the flow is:

```text
source code
   ↓
adapter-provision.py
   ↓ SHA-256 + runtime probe
provisioning receipt
   ↓
adapter-provisioning-evidence.py
   ↓
provisioning-pass
   ↓
adapter-promotion.py
```

## CLI

Plan only:

```bash
python3 dev-hub/bin/adapter-promotion.py \
  --evidence /path/evidence.json \
  plan --adapter http-smoke-adapter --target PILOT \
  --executable /opt/chacha-dev/adapters/http-smoke/current/http-smoke-adapter
```

Apply only after the plan is eligible:

```bash
python3 dev-hub/bin/adapter-promotion.py \
  --registry /path/provider-adapters.v1.json \
  --evidence /path/evidence.json \
  apply --adapter http-smoke-adapter --target PILOT \
  --executable /opt/chacha-dev/adapters/http-smoke/current/http-smoke-adapter \
  --actor platform-cloud-engineer \
  --receipt /path/promotion-receipt.json \
  --apply
```

No `--apply`, no mutation.

## Safety boundary

CI uses temporary runtime roots and temporary registry copies. A CI success proves the mechanism; it does not install the adapter on the VPS and does not mutate the real registry.

Real `CONTRACT_OK -> PILOT` therefore requires two distinct facts: the executable was actually provisioned on the DEV HUB host, and promotion evidence derived from that exact install is accepted by the promotion engine.
