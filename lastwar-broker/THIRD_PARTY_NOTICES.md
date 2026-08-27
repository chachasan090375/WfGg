# Third-party notices — WfGg Last War broker

## lastwar-client

The broker build uses a pinned revision of the open-source project:

- Project: `ljagiello/lastwar-client`
- Upstream revision: `ee5f64de160a8051c2f9f98189b75038dd225a0a`
- Copyright: 2026 Lukasz Jagiello
- License: Apache License 2.0
- Source: https://github.com/ljagiello/lastwar-client

WfGg applies a small local modification to `internal/auth/login.go` so the existing email verification flow can be driven by a staged web UX instead of stdin/FIFO. The modification does not change the Last War wire commands; it only adds callbacks for “verification code sent” and “provide verification code”.

The complete local patch is kept in `patches/0001-wfgg-staged-email-auth.patch`.

Apache License 2.0 terms remain applicable to the upstream work and the modified upstream file included in the broker image build.
