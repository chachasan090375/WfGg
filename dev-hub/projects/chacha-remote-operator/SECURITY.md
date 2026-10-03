# Security model — ChaCha Remote Operator MCP

## Trust boundaries

The MCP protocol endpoint is not itself an authorization boundary. V0.1 therefore binds to `127.0.0.1` only and must not be directly exposed to the Internet.

A future remote gateway must terminate authenticated transport before forwarding to the local MCP service. Network exposure requires a separate Bastion review and qualification.

## Primary threats

1. Arbitrary command execution through shell interpolation.
2. Path traversal or symlink escape outside approved roots.
3. Secret or private-key exfiltration through file tools.
4. Concurrent operators causing conflicting mutations.
5. Prompt injection or untrusted content attempting to escalate tool permissions.
6. Destructive operations performed without explicit governance.
7. Audit tampering or evidence loss.
8. Public network exposure without authenticated transport.
9. Resource exhaustion through unbounded reads, searches, output or long-running commands.
10. A remote operator bypassing the canonical emergency STOP.

## V0.1 mitigations

- Localhost-only bind.
- Read-first tool surface.
- Command execution disabled by default.
- No shell interpolation (`shell=False` only).
- Resolved-path allowlist and blocked secret path classes.
- Bounded reads, searches, process lists and command output.
- Explicit systemd-unit allowlist.
- Append-only JSONL audit ledger with mode `0600`.
- Canonical STOP checked before operational tool calls.
- No file writes, service mutations, Git mutations or destructive operations.
- No automatic external spend.

## Future write profile requirements

Before enabling any write or mutation tool, the project must add and qualify:

- Guardian PRE/POST binding to each mutation class.
- Bastion policy for remote/network exposure.
- Single-writer lease ownership for conflicting operations.
- Immutable mutation receipts and rollback evidence.
- Separate permissions for read, write and destructive actions.
- Explicit secret redaction rules for command arguments, outputs and audit details.
- Authentication for remote transport; bearer/OAuth credentials must never be exposed as MCP resources or tool outputs.
- Exact-SHA Sentinelle and project qualification.
- Explicit production approval.

## Fail-closed rule

Missing policy, unreadable STOP state, out-of-root paths, non-allowlisted services, disabled command execution, or unknown mutation classes must block the operation rather than degrade to permissive behavior.
