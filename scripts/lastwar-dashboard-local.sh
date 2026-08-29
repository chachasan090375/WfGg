#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — local browser preview only.
# Serves frontend/ on 127.0.0.1 without uploading player data or extracted graphics.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
PORT="${WFGG_LASTWAR_VIEWER_PORT:-8877}"
MODE="${1:-data}"
case "$MODE" in
  formation|squads|replica) PAGE="lastwar-formation-screen.html" ;;
  renderer|webgl|auth) PAGE="lastwar-auth-renderer.html" ;;
  data|explorer) PAGE="lastwar-data.html" ;;
  *) echo "Usage: $0 [data|formation|renderer]" >&2; exit 2 ;;
esac
URL="http://127.0.0.1:${PORT}/lab/${PAGE}"

command -v python >/dev/null 2>&1 || {
  echo "Installation de Python Termux…"
  pkg install -y python
}

[[ -f "$FRONTEND/lab/$PAGE" ]] || {
  echo "ERREUR: page Last War absente. Fais d'abord git pull --ff-only." >&2
  exit 1
}

echo "=== WfGg Last War LAB · aperçu local ==="
echo "Adresse: $URL"
echo "Formation: http://127.0.0.1:${PORT}/lab/lastwar-formation-screen.html"
echo "Renderer technique: http://127.0.0.1:${PORT}/lab/lastwar-auth-renderer.html"
echo "Explorateur: http://127.0.0.1:${PORT}/lab/lastwar-data.html"
echo "Serveur lié uniquement à 127.0.0.1 (téléphone local)."
echo "Arrêt: CTRL+C dans Termux."
echo

if command -v termux-open-url >/dev/null 2>&1; then
  (sleep 1; termux-open-url "$URL" >/dev/null 2>&1 || true) &
fi

cd "$FRONTEND"
exec python -m http.server "$PORT" --bind 127.0.0.1
