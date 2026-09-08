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
printf '\n=== WFGG V39.8 : PREFABS ANIMES / DIAGNOSTIC CORRIGE ===\n'
printf 'Mouvement synthetique: OFF\n'
printf 'Recuperation source V39.7: ON\n'
printf 'Hotfix diagnostic navigateur: ON\n'
exec python scripts/lastwar-global-graphics-server-v398-hotfix.py "$ROOT"
