# ChaCha DEV HUB — Adapter Runtime Provisioning V1

Adapter Runtime Provisioning is the controlled installation layer between `CONTRACT_OK` and `PILOT` for local/VPS adapters.

It is deliberately separate from adapter promotion. Provisioning installs bytes and proves what was installed; promotion decides whether the registered lifecycle status may advance.

## Invariants

- no implicit apply;
- immutable version directories;
- SHA-256 source -> installed -> current executable equality;
- atomic `current` symlink switch;
- non-destructive structured runtime probe;
- machine-readable provisioning receipt;
- provisioning never mutates `provider-adapters.v1.json`;
- provisioning never promotes an adapter;
- promotion to `PILOT` requires `provisioning-pass` evidence.

## HTTP smoke layout

The canonical production/VPS layout is:

```text
/opt/chacha-dev/adapters/
  http-smoke/
    1.0.0/
      http-smoke-adapter
    current -> 1.0.0
```

The executable registered for the pilot is therefore:

```text
/opt/chacha-dev/adapters/http-smoke/current/http-smoke-adapter
```

The version directory is immutable. An upgrade installs a new version directory first and changes `current` atomically only after digest checks.

## Provisioning receipt

`chacha.dev/adapter-provisioning-receipt/v1` records:

- adapter and version;
- actor and timestamp;
- source path + SHA-256;
- installed path + SHA-256;
- current executable path + SHA-256;
- current symlink target and previous target;
- file mode;
- structured runtime probe result.

A receipt is evidence, not an authorization. It contains no private secret value.

## Commands

Plan only:

```bash
python3 dev-hub/bin/adapter-provision.py \
  plan --adapter http-smoke-adapter
```

Real apply on the DEV HUB host:

```bash
python3 dev-hub/bin/adapter-provision.py \
  apply --adapter http-smoke-adapter \
  --actor platform-cloud-engineer \
  --receipt /opt/chacha-dev/runtime/adapter-provisioning/http-smoke-1.0.0.json \
  --apply
```

Verify an existing install:

```bash
python3 dev-hub/bin/adapter-provision.py \
  verify --adapter http-smoke-adapter \
  --receipt /opt/chacha-dev/runtime/adapter-provisioning/http-smoke-1.0.0.json
```

CI uses `--root <temporary-directory>` so it cannot provision the real VPS path.

## Promotion evidence bridge

`adapter-provisioning-evidence.py` binds the provisioning receipt into `chacha.dev/adapter-promotion-evidence/v1` as `provisioning-pass`.

It rechecks that source, installed and executable digests are identical, that the executable still exists with the recorded digest, and that the provisioning probe passed.

The promotion chain is therefore:

```text
CONTRACT_OK
   |
   +-- runtime-contract-pass
   +-- sandbox-only
   +-- provisioning-pass
   v
PILOT
```

For external-only adapters, `provisioning-pass` represents a provider-specific external runtime binding proof and must not invent a local executable.

## Current activation boundary

The repository registry remains unchanged until the adapter has actually been provisioned on the DEV HUB host and the resulting receipt has been converted into promotion evidence. CI success alone does not promote the real adapter.
