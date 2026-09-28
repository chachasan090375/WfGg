#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=${1:-/opt/chacha-dev/platform/current}
install -m 0644 "$ROOT/dev-hub/systemd/chacha-dev-branch-foundry-lifecycle.service" /etc/systemd/system/chacha-dev-branch-foundry-lifecycle.service
install -m 0644 "$ROOT/dev-hub/systemd/chacha-dev-branch-foundry-lifecycle.tmpfiles.conf" /etc/tmpfiles.d/chacha-dev-branch-foundry-lifecycle.conf
systemd-tmpfiles --create /etc/tmpfiles.d/chacha-dev-branch-foundry-lifecycle.conf
systemctl daemon-reload
echo CHACHA_DEV_BRANCH_FOUNDRY_LIFECYCLE_INSTALL=PASS
