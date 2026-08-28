#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — local browser preview only.
# Serves frontend/ on 127.0.0.1 so the phase-7 JSON can be opened in Chrome
# without uploading player data to Cloudflare/GitHub/D1.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
PORT="${WFGG_LASTWAR_VIEWER_PORT:-8877}"
URL="http://127.0.0.1:${PORT}/lab/lastwar-data.html"

command -v python >/dev/null 2>&1 || {
  echo "Installation de Python Termux…"
  pkg install -y python
}

[[ -f "$FRONTEND/lab/lastwar-data.html" ]] || {
  echo "ERREUR: explorateur Last War absent. Fais d'abord git pull --ff-only." >&2
  exit 1
}

echo "=== WfGg Last War LAB · explorateur local ==="
echo "Adresse: $URL"
echo "Serveur lié uniquement à 127.0.0.1 (téléphone local)."
echo "Arrêt: CTRL+C dans Termux."
echo

if command -v termux-open-url >/dev/null 2>&1; then
  (sleep 1; termux-open-url "$URL" >/dev/null 2>&1 || true) &
fi

cd "$FRONTEND"
exec python -m http.server "$PORT" --bind 127.0.0.1
