#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="lab-global-graphics-animated-prefab-v39"
cd "$ROOT"
if [ "$(git branch --show-current)" != "$BRANCH" ]; then
  echo "ERREUR: branche active=$(git branch --show-current), attendu=$BRANCH" >&2
  echo "Commande: git switch $BRANCH" >&2
  exit 2
fi
printf '\n=== WFGG V39 : PREFABS ANIMES / DIAGNOSTIC UNITY EXACT ===\n'
printf 'Mouvement synthetique: OFF\n'
exec python scripts/lastwar-global-graphics-server-v39-animated.py "$ROOT"
