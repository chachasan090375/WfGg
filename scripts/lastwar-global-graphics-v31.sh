#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="lab-global-graphics-catalog-v31"
cd "$ROOT"
if [ "$(git branch --show-current)" != "$BRANCH" ]; then
  echo "ERREUR: branche active=$(git branch --show-current), attendu=$BRANCH" >&2
  echo "Commande: git switch $BRANCH" >&2
  exit 2
fi
printf '\n=== WFGG GLOBAL GRAPHICS CATALOG V31 ===\n'
python scripts/lastwar-global-graphics-catalog-v31.py "$ROOT"
printf '\n=== ENRICHISSEMENT EVENEMENTS / SAISONS / INTER-SAISON ===\n'
python scripts/lastwar-global-graphics-scope-enrich-v31.py "$ROOT"
printf '\n=== CORRECTION DES PORTÉES / FAUX POSITIFS REGIONAUX ===\n'
python scripts/lastwar-global-graphics-scope-correct-v31.py "$ROOT"
printf '\n=== HIERARCHIE DOSSIERS / SOUS-DOSSIERS / FICHIERS ===\n'
python scripts/lastwar-global-graphics-hierarchy-v31.py "$ROOT"
printf '\n=== VIEWER A LA DEMANDE ===\n'
exec python scripts/lastwar-global-graphics-server-v31.py "$ROOT"
