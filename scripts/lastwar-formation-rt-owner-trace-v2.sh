#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/lastwar-formation-rt-owner-trace-v1.sh"
TMP="$ROOT/scripts/.lastwar-formation-rt-owner-trace-v2.$$.sh"
trap 'rm -f "$TMP"' EXIT
[[ -s "$SRC" ]] || { echo "ERREUR: traceur v1 absent" >&2; exit 1; }
sed 's/PANEL_GO_PID=869585497998244933/PANEL_GO_PID=8695854979998244933/' "$SRC" > "$TMP"
chmod 700 "$TMP"
exec bash "$TMP"
