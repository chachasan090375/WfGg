#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
TRIGGER="${1:-MANUAL}"
QUERY="${2:-}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector/incremental-update-v2-from-termux.sh"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT INT TERM
curl -fsSL "$RAW" -o "$TMP"
python3 - "$TMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
s=s.replace("-H 'Content-Type: application/json'", "-H Content-Type:application/json")
s=s.replace("-H Content-Type: application/json", "-H Content-Type:application/json")
p.write_text(s)
PY
bash "$TMP" "$TRIGGER" "$QUERY"
