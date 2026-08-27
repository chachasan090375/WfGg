# WfGg Last War local connector — INTERNAL TOOLING

This directory is **not the end-user product**.

The Node CLI exists only to validate the pairing/token/snapshot protocol during development and diagnostics. Production users must not be asked to install Termux, open a terminal, type commands, copy tokens, edit JSON credentials or manage configuration files.

The end-user UX contract is documented in `docs/LASTWAR_CONNECTOR_UX_V1.md`.

Production target: browser-first linking, with a graphical cross-platform `WfGg Connect` helper only if browser-only Last War session establishment proves impossible.
