#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/frontend/lab/master-assets-v2/formation-omnitrace"
SESS="$BASE/sessions"
ACTION="${1:-20260831_161338}"
BASELINE="${2:-}"
[[ -d "$SESS/$ACTION" ]] || { echo "ACTION_SESSION_NOT_FOUND=$ACTION"; exit 2; }
if [[ -z "$BASELINE" ]]; then
  BASELINE="$(find "$SESS" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -r | awk -v a="$ACTION" '$0!=a{print;exit}')"
fi
[[ -n "$BASELINE" && -d "$SESS/$BASELINE" ]] || { echo 'BASELINE_SESSION_NOT_FOUND'; exit 3; }
OUT="$BASE/differential-latest.json"
python3 "$ROOT/scripts/lastwar-formation-omnitrace-differential-v2.py" "$SESS/$ACTION" "$SESS/$BASELINE" "$OUT"
if ! curl -fsS --max-time 1 http://127.0.0.1:8788/ >/dev/null 2>&1; then
  nohup python3 -m http.server 8788 --directory "$ROOT/frontend" >"$BASE/http.log" 2>&1 &
  sleep 1
fi
echo "ACTION=$ACTION"
echo "BASELINE=$BASELINE"
echo 'VIEWER=http://127.0.0.1:8788/lab/lastwar-formation-omnitrace-differential.html?v=2'
