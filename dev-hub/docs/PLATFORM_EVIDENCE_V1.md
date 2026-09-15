# ChaCha DEV HUB — Platform Evidence V1

Platform Evidence is the normalization boundary between runtime probes and the Platform Readiness gate.

It deliberately does **not** execute provider-specific commands. A GitHub connector, MCP probe, local runtime adapter, NAS probe, Storage Governor, or future provider adapter performs its own check and emits structured evidence. `platform-evidence.py` then validates identity, freshness and status and produces the two canonical runtime artifacts consumed by readiness:

```text
provider probe results
        |
        v
Platform Evidence normalizer
        |
        +--> provider-health-snapshot/v1
        |
Storage Governor raw output
        |
        +--> storage-preflight/v1
```

## Provider health

Each independent probe emits `chacha.dev/provider-probe-result/v1` with:

- provider id;
- `HEALTHY`, `DEGRADED`, `UNAVAILABLE` or `UNKNOWN`;
- probe source;
- timezone-aware `checked_at`;
- optional latency, reason, details and evidence digest.

The provider catalog in `provider-health-probes.v1.json` is authoritative. The normalizer selects the newest valid result per provider. Missing providers become `UNKNOWN`. Results older than the freshness window become `UNKNOWN`, never `HEALTHY`. Excessively future-dated results also become `UNKNOWN`. Unknown provider ids are rejected by default.

This means an old successful probe cannot keep the platform falsely green.

Example:

```bash
python3 dev-hub/bin/platform-evidence.py --repo-root . health \
  --project wfgg \
  --result-dir /opt/chacha-dev/runtime/probes/wfgg \
  --output /opt/chacha-dev/runtime/health/wfgg/providers.json
```

## Storage normalization

Storage Governor may currently produce key/value output such as:

```text
NEED_MB=600
RESERVE_MB=1280
REQUIRED_FREE_MB=1880
CURRENT_FREE_MB=1215
CURRENT_USED_PERCENT=86
STORAGE_PRESSURE=WARN
PREFLIGHT=BLOCKED
```

The normalizer converts this into `chacha.dev/storage-preflight/v1`, preserving the capacity values and adding deterministic reasons such as `INSUFFICIENT_FREE_SPACE`.

```bash
python3 dev-hub/bin/platform-evidence.py --repo-root . storage \
  --project wfgg \
  --input /tmp/storage-preflight.txt \
  --output /opt/chacha-dev/runtime/evidence/wfgg/storage-preflight.json
```

The same command accepts JSON input with `--format json`; `--format auto` detects JSON versus key/value text.

## Trust boundary

The normalizer never invokes arbitrary shell commands and never upgrades an evidence state. It cannot turn `UNKNOWN` into `HEALTHY`, cannot promote an adapter, cannot enable Run Controller, cannot create a production approval and cannot read private signing material.

Probe execution remains the responsibility of the provider/adaptor layer. This separation keeps provider-specific credentials and transports out of the common evidence parser.

## Readiness integration

`platform-readiness.v1.json` identifies these normalized artifacts as the canonical runtime evidence. Contract certification does not require live runtime evidence. Development and production certification do.

The current DEV HUB therefore remains intentionally **not runtime-ready** until adapters/probes are provisioned and promoted and Run Controller is explicitly enabled; Platform Evidence gives that future activation a deterministic input contract rather than ad-hoc command parsing.
