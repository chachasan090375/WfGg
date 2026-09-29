# ChaCha Remote Operator MCP

ChaCha Remote Operator is the self-hosted remote-operations capability for ChaCha DEV. Its goal is to remove the platform's operational dependency on commercial remote-terminal call quotas while keeping ChaCha DEV governance intact.

## V0.1 scope

V0.1 is intentionally read-first. It exposes MCP tools for health, system status, file reading, directory listing, bounded file search, process listing, and systemd status. A controlled `command_run` tool exists but is disabled by policy by default.

The server uses MCP Streamable HTTP and binds to `127.0.0.1` by default. It must not be exposed directly to the public Internet. A later governed gateway/tunnel layer will provide remote access and authentication.

## Security invariants

- Canonical emergency STOP is checked before every operation.
- No `shell=True`; commands are argv-only.
- Paths are constrained to allowlisted roots and resolved before access.
- Output and file reads are bounded.
- Every tool call is appended to a local audit JSONL ledger.
- Destructive operations, arbitrary shell, credential reads, secret export, production deployment, and external spend are forbidden in V0.1.
- Command execution remains disabled until a later Guardian/Bastion-governed profile explicitly enables it.
- Automatic external spend is always 0 EUR.

## Planned phases

1. V0.1 — read-only diagnostic MCP on ChaChaVPS.
2. V0.2 — allowlisted command execution with Guardian PRE/POST and lease ownership.
3. V0.3 — governed file writes, Git operations, service controls, rollback receipts.
4. V0.4 — multi-target agents for ChaChaVPS, ChaChaNas and ChaChaTel.
5. V1.0 — remote authenticated gateway/tunnel and optional ChatGPT/custom-app packaging.
6. Later — graphical desktop/screen interaction only if it adds real value.

## Local development

```bash
cd dev-hub/projects/chacha-remote-operator
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python -m chacha_remote_operator.server
```

Default endpoint: `http://127.0.0.1:8765/mcp`.

The project must remain independently testable and must not mutate `/opt/chacha-dev/platform/current` or any production release during development.