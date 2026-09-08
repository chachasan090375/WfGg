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
printf '\n=== WFGG V39.14 : REAL BADGE ROW + PREFABS ANIMES ===\n'
printf 'Mouvement synthetique: OFF\n'
printf 'Recuperation source V39.7: ON\n'
printf 'Hotfix diagnostic navigateur: ON\n'
printf 'Badge animation: VRAIE LIGNE FLEX + IMAGE PHYSIQUEMENT SOUS LA LIGNE\n'
printf 'SoftReferencePrefab V39.12: RESOLUTION EXACTE + MATERIALISATION\n'
printf 'Assemblage fusionne: GARDE jusqu a validation exacte de tous les slots\n'
exec python scripts/lastwar-global-graphics-server-v3913-layout.py "$ROOT"
