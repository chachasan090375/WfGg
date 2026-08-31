#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PORT=8788
URL="http://127.0.0.1:${PORT}/lab/lastwar-formation-lua-trace-viewer.html?v=3"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
printf 'FORMATION_LUA_TRACE_VIEWER_V3_START\n'
if [[ -x scripts/lastwar-lwlua-container-il-trace-v1.sh || -f scripts/lastwar-lwlua-container-il-trace-v1.sh ]]; then
  bash scripts/lastwar-lwlua-container-il-trace-v1.sh || printf 'WARN il-trace failed; viewer will reuse existing metadata\n' >&2
fi
if [[ -x scripts/lastwar-lua-runtime-materialize-v1.sh || -f scripts/lastwar-lua-runtime-materialize-v1.sh ]]; then
  bash scripts/lastwar-lua-runtime-materialize-v1.sh || printf 'WARN runtime materialization failed; viewer will reuse existing sources\n' >&2
fi
if [[ -x scripts/lastwar-lua-runtime-diagnostic-v1.sh || -f scripts/lastwar-lua-runtime-diagnostic-v1.sh ]]; then
  bash scripts/lastwar-lua-runtime-diagnostic-v1.sh || printf 'WARN runtime diagnostic failed\n' >&2
fi
bash scripts/lastwar-formation-lua-trace-viewer-build-v1.sh
# Diagnostic is generated before build and retained beside the manifest.
printf 'Viewer: %s\n' "$URL"
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then
  printf 'FORMATION_LUA_TRACE_VIEWER_V3_SERVER_REUSE port=%s\n' "$PORT"
  printf 'OPEN=%s\n' "$URL"
  exit 0
fi
printf 'FORMATION_LUA_TRACE_VIEWER_V3_SERVER_START port=%s\n' "$PORT"
cd "$ROOT/frontend"
printf 'OPEN=%s\n' "$URL"
exec python -m http.server "$PORT" --bind 127.0.0.1
