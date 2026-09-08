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
printf '\n=== WFGG V40 : ANIMATION GRAPH AGENT ===\n'
printf 'Viewer V39.15: CONSERVE\n'
printf 'Badge V39.14: CONSERVE\n'
printf 'Graphe Unity: catalogue + PPtr + SoftReferencePrefab\n'
printf 'Assembly-CSharp: CLR metadata + appels IL bornes, lecture seule\n'
printf 'Code du jeu execute: NON\n'
printf 'Mouvement/geometrie synthetique: NON\n'
printf 'Cache agent: ~/.cache/wfgg-lastwar-v40/animation-graph.sqlite3\n'
printf 'Validation reference: LWGA-C37A0F67197299 -> building_10123000 -> SimpleAnimation\n'
exec python scripts/lastwar-global-graphics-server-v40-agent.py "$ROOT"
