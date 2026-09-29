# ChaCha Remote Operator MCP

ChaCha Remote Operator is the self-hosted remote-operations capability for ChaCha DEV. Its goal is to remove the platform's operational dependency on commercial remote-terminal call quotas while keeping ChaCha DEV governance intact.

## V0.1 — read-only foundation

V0.1 exposes MCP tools for health, system status, file reading, directory listing, bounded file search, process listing, and systemd status. The historical `command_run` tool is present but disabled by policy.

The server uses MCP Streamable HTTP and binds to `127.0.0.1` by default. It must not be exposed directly to the public Internet.

## V0.2 — governed named read operations

V0.2 adds a separate `governed_operation` tool. It does **not** accept a shell string or client-supplied argv. Instead, the caller selects one named operation and the server constructs the exact executable arguments itself.

Current operation IDs:

- `git_status` — `git status --short --branch` in an allowlisted cwd.
- `git_head` — read the exact Git HEAD in an allowlisted cwd.
- `git_tree` — read the exact Git tree in an allowlisted cwd.
- `service_is_active` — query one allowlisted ChaCha DEV systemd unit.
- `service_is_enabled` — query one allowlisted ChaCha DEV systemd unit.
- `uptime` — local uptime read.
- `free_bytes` — local memory read.
- `uname` — local kernel/platform read.

Every V0.2 governed operation is protected by canonical STOP, a single-writer lease, Guardian PRE/POST and append-only audit. The legacy raw `command_run` surface remains disabled by the V0.2 policy.

V0.2 uses a separate localhost pilot endpoint on `127.0.0.1:8766/mcp`, so V0.1 can remain online while V0.2 is qualified.

## Security invariants

- Canonical emergency STOP is checked before every operation; governed execution rechecks STOP after Guardian PRE.
- No `shell=True` and no client-provided command string.
- Paths are constrained to allowlisted roots and resolved before access.
- Output and file reads are bounded.
- At most one governed operation may execute at once.
- Guardian PRE and POST are mandatory for V0.2 governed operations.
- Every tool call is appended to a local audit JSONL ledger.
- Credential reads, secret export, file writes, Git mutation, service mutation, destructive operations, production deployment and automatic external spend remain forbidden.
- Network exposure remains forbidden until an authenticated Bastion-reviewed gateway is separately qualified.
- Automatic external spend is always 0 EUR.

## Planned phases

1. V0.1 — read-only diagnostic MCP on ChaChaVPS. **Pilot PASS.**
2. V0.2 — fixed named read operations with Guardian PRE/POST and single-writer lease. **Candidate under qualification.**
3. V0.3 — governed file writes, Git operations, service controls and rollback receipts.
4. V0.4 — multi-target agents for ChaChaVPS, ChaChaNas and ChaChaTel.
5. V1.0 — remote authenticated gateway/tunnel and ChatGPT/custom-app packaging when supported.
6. Later — graphical desktop/screen interaction only if it adds real value.

## Local development

V0.1:

```bash
cd dev-hub/projects/chacha-remote-operator
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python -m chacha_remote_operator.server
```

V0.2:

```bash
export CHACHA_REMOTE_OPERATOR_POLICY="$PWD/config/policy.v2.json"
python -m chacha_remote_operator.server_v02
```

The project must remain independently testable and must not mutate `/opt/chacha-dev/platform/current` or any production release during development.
