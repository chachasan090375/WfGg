#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
PROJECT="${1:-}"

if [ -z "$PROJECT" ]; then
  echo "USAGE=source-sync <project>" >&2
  exit 2
fi

MANIFEST="$ROOT/registry/manifests/$PROJECT.json"
if [ ! -s "$MANIFEST" ]; then
  echo "MANIFEST_NOT_FOUND=$MANIFEST" >&2
  exit 2
fi

IFS=$'\t' read -r WORKSPACE REPO BRANCH < <(python3 - "$MANIFEST" <<'PY'
import json, sys
m=json.load(open(sys.argv[1]))
w=m.get('workspace',{})
r=m.get('repository',{})
print((w.get('local') or w.get('path') or '')+'\t'+(r.get('url') or '')+'\t'+(r.get('default_branch') or 'main'))
PY
)

if [ -z "$WORKSPACE" ] || [ -z "$REPO" ]; then
  echo "SOURCE_CONFIG_INVALID=1" >&2
  echo "WORKSPACE=$WORKSPACE" >&2
  echo "REPO=$REPO" >&2
  exit 3
fi

mkdir -p "$(dirname "$WORKSPACE")"

echo "=== SOURCE SYNC ==="
echo "PROJECT=$PROJECT"
echo "WORKSPACE=$WORKSPACE"
echo "REPO=$REPO"
echo "BRANCH=$BRANCH"

if [ -d "$WORKSPACE/.git" ]; then
  echo "SOURCE_STATE=EXISTING_GIT_WORKTREE"
  git -C "$WORKSPACE" remote -v | head -n 2 || true
  git -C "$WORKSPACE" fetch --depth 1 origin "$BRANCH" || true
else
  if [ -d "$WORKSPACE" ] && [ -n "$(find "$WORKSPACE" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    echo "SOURCE_SYNC_REFUSED=NONEMPTY_NON_GIT_WORKSPACE" >&2
    exit 4
  fi
  rmdir "$WORKSPACE" 2>/dev/null || true
  echo "SOURCE_STATE=CLONING_SHALLOW_FILTERED"
  git clone --depth 1 --filter=blob:none --single-branch --branch "$BRANCH" "$REPO" "$WORKSPACE"
fi

FILES="$(find "$WORKSPACE" -type f -not -path '*/.git/*' | wc -l | tr -d ' ')"
if [ "$FILES" -eq 0 ]; then
  echo "SOURCE_FILES=0" >&2
  exit 5
fi

HEAD="$(git -C "$WORKSPACE" rev-parse --short HEAD 2>/dev/null || echo unknown)"
CURRENT_BRANCH="$(git -C "$WORKSPACE" branch --show-current 2>/dev/null || true)"
SIZE="$(du -sh "$WORKSPACE" 2>/dev/null | awk '{print $1}')"

echo "SOURCE_FILES=$FILES"
echo "SOURCE_HEAD=$HEAD"
echo "SOURCE_BRANCH=${CURRENT_BRANCH:-detached}"
echo "SOURCE_SIZE=$SIZE"
echo "SOURCE_SYNC=OK"
