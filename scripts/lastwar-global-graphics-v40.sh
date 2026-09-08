#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="lab-animation-graph-agent-v40"
cd "$ROOT"
if [ "$(git branch --show-current)" != "$BRANCH" ]; then
  echo "ERREUR: branche active=$(git branch --show-current), attendu=$BRANCH" >&2
  echo "Commande: git switch $BRANCH" >&2
  exit 2
fi
printf '\n=== WFGG V40.6 : FERMETURE RUNTIME EXACTE ===\n'
printf 'Trace V40.5 Unity/catalogue/CLR: ON\n'
printf 'Cibles par defaut: racine + WORK + IDLE exacts locaux\n'
printf 'Fermeture bundle staged: 48/3 -> 96/5 -> 160/7\n'
printf 'Arret des que Material -> Texture2D exact est resolu: ON\n'
printf 'Re-enrichissement Unity PPtr + export PNG: ON\n'
printf 'Rendu V40.4.1 reutilise les manifests rafraichis: ON\n'
printf 'Audit/index visuel: INCHANGES\n'
printf 'Geometrie synthetique: OFF\n'
printf 'Texture synthetique: OFF\n'
printf 'Mouvement synthetique: OFF\n'
exec python scripts/lastwar-global-graphics-server-v406-agent-runtime.py "$ROOT"
