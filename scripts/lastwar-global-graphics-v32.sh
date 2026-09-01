#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="lab-global-graphics-catalog-v32"
cd "$ROOT"
if [ "$(git branch --show-current)" != "$BRANCH" ]; then
  echo "ERREUR: branche active=$(git branch --show-current), attendu=$BRANCH" >&2
  echo "Commande: git switch $BRANCH" >&2
  exit 2
fi
printf '\n=== WFGG GLOBAL GRAPHICS BASE V31 ===\n'
python scripts/lastwar-global-graphics-catalog-v31.py "$ROOT"
printf '\n=== PORTÉES EVENEMENTS / SAISONS ===\n'
python scripts/lastwar-global-graphics-scope-enrich-v31.py "$ROOT"
python scripts/lastwar-global-graphics-scope-correct-v31.py "$ROOT"
printf '\n=== HIERARCHIE PHYSIQUE ===\n'
python scripts/lastwar-global-graphics-hierarchy-v31.py "$ROOT"
printf '\n=== V32 : NATURE GRAPHIQUE + EVENEMENTS DIRECTS ===\n'
python scripts/lastwar-global-graphics-enrich-v32.py "$ROOT"
printf '\n=== V32 : CROSSWALK EVENEMENTS VIA GRAPHE EXACT ===\n'
python scripts/lastwar-event-graph-crosswalk-v32.py "$ROOT"
printf '\n=== VIEWER V32 ===\n'
exec python scripts/lastwar-global-graphics-server-v32.py "$ROOT"
