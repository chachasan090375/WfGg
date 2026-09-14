#!/usr/bin/env bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
SRC_BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-bootstrap/dev-hub"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo 'Run this bootstrap as root.' >&2
  exit 1
fi

echo '=== ChaCha DEV HUB bootstrap ==='
echo "ROOT=$ROOT"

mkdir -p \
  "$ROOT/platform/bin" \
  "$ROOT/platform/config" \
  "$ROOT/platform/templates" \
  "$ROOT/platform/scripts" \
  "$ROOT/registry/projects" \
  "$ROOT/agents/antigravity" \
  "$ROOT/agents/skywork" \
  "$ROOT/agents/future" \
  "$ROOT/engines/blender" \
  "$ROOT/engines/unitypy" \
  "$ROOT/engines/python" \
  "$ROOT/engines/node" \
  "$ROOT/projects" \
  "$ROOT/shared/assets" \
  "$ROOT/shared/cache" \
  "$ROOT/shared/datasets" \
  "$ROOT/shared/libraries" \
  "$ROOT/artifacts/builds" \
  "$ROOT/artifacts/exports" \
  "$ROOT/artifacts/reports" \
  "$ROOT/artifacts/previews" \
  "$ROOT/logs" \
  "$ROOT/backups"

curl -fsSL "$SRC_BASE/projectctl" -o "$ROOT/platform/bin/projectctl"
chmod 0755 "$ROOT/platform/bin/projectctl"
ln -sfn "$ROOT/platform/bin/projectctl" /usr/local/bin/projectctl

# Baseline runtimes shared by all projects.
if ! command -v node >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs npm >/dev/null
fi

# Register existing shared engines without moving or modifying them.
if [[ -x /root/.local/bin/blender ]]; then
  ln -sfn /root/.local/bin/blender "$ROOT/engines/blender/current"
fi
if [[ -x /root/wfgg-tools/unitypy-venv/bin/python ]]; then
  ln -sfn /root/wfgg-tools/unitypy-venv "$ROOT/engines/unitypy/current"
fi
if command -v python3 >/dev/null 2>&1; then
  ln -sfn "$(command -v python3)" "$ROOT/engines/python/current"
fi
if command -v node >/dev/null 2>&1; then
  ln -sfn "$(command -v node)" "$ROOT/engines/node/current"
fi

cat > "$ROOT/platform/config/platform.conf" <<EOF
CHACHA_DEV_ROOT=$ROOT
PLATFORM_VERSION=0.1.1
PLATFORM_MODE=shared-multi-project
CREATED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

cat > "$ROOT/README.txt" <<'EOF'
ChaCha DEV HUB
===============
Shared development platform for current and future projects.

Key commands:
  projectctl doctor
  projectctl engines
  projectctl list
  projectctl register <name> <owner/repo> [type]
  projectctl status <name>
  projectctl path <name>

Existing tools are registered by symlink. The bootstrap does not move or delete
working Blender/UnityPy installations.
EOF

# First generic WfGg registration: this is only metadata/workspace creation.
if [[ ! -f "$ROOT/registry/projects/wfgg.conf" ]]; then
  projectctl register wfgg chachasan090375/WfGg web >/dev/null
fi

echo '=== DEV HUB READY ==='
projectctl doctor
echo '--- ENGINES ---'
projectctl engines
echo '--- PROJECTS ---'
projectctl list
