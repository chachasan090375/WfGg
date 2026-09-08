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
printf '\n=== WFGG V39.15 : SOUS-PREFABS RUNTIME EXACTS ===\n'
printf 'Mouvement synthetique: OFF\n'
printf 'Recuperation source V39.7: ON\n'
printf 'Badge animation V39.14: VRAIE LIGNE FLEX + AUCUN RECOUVREMENT IMAGE\n'
printf 'SoftReferencePrefab V39.12: RESOLUTION EXACTE + MATERIALISATION\n'
printf 'Apercu sous-prefab: WORK D ABORD + IDLE EN REPLI + MODELE V33 EXACT\n'
printf 'Assemblage fusionne parent+enfant: OFF tant que non prouve; aucun faux rendu\n'
exec python scripts/lastwar-global-graphics-server-v3915-runtime-preview.py "$ROOT"
