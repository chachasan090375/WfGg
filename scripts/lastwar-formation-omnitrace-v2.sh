#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V1="$ROOT/scripts/lastwar-formation-omnitrace-v1.sh"
SAN="$ROOT/scripts/lastwar-formation-omnitrace-sanitize-v2.py"
LATEST="$ROOT/frontend/lab/master-assets-v2/formation-omnitrace/latest.json"

sanitize_latest(){
  [[ -f "$LATEST" ]] || return 0
  python3 "$SAN" "$LATEST"
  local sid
  sid="$(python3 - "$LATEST" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1],encoding='utf-8')).get('session',''))
except Exception: print('')
PY
)"
  if [[ -n "$sid" ]]; then
    local a="$ROOT/frontend/lab/master-assets-v2/formation-omnitrace/sessions/$sid/analysis.json"
    [[ -f "$a" ]] && python3 "$SAN" "$a" || true
  fi
}

case "${1:-}" in
  start)
    shift
    exec bash "$V1" start "$*"
    ;;
  stop)
    bash "$V1" stop
    sanitize_latest
    echo 'FORMATION_OMNITRACE_V2_SANITIZED'
    echo 'VIEWER=http://127.0.0.1:8788/lab/lastwar-formation-omnitrace.html?v=3'
    ;;
  reanalyze)
    sid="${2:-20260831_161338}"
    session="$ROOT/frontend/lab/master-assets-v2/formation-omnitrace/sessions/$sid"
    [[ -d "$session" ]] || { echo "SESSION_NOT_FOUND=$sid"; exit 2; }
    python3 "$ROOT/scripts/lastwar-formation-omnitrace-analyze-v1.py" "$session" "$LATEST"
    sanitize_latest
    echo "FORMATION_OMNITRACE_V2_REANALYZED session=$sid"
    echo 'VIEWER=http://127.0.0.1:8788/lab/lastwar-formation-omnitrace.html?v=3'
    ;;
  status)
    exec bash "$V1" status
    ;;
  *)
    echo 'Usage: bash scripts/lastwar-formation-omnitrace-v2.sh start "Murphy -> autre héros" | stop | reanalyze [session] | status'
    exit 1
    ;;
esac
