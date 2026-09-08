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
printf '\n=== WFGG V40 : ANIMATION GRAPH AGENT ===\n'
printf 'V39.15 runtime child preview: ON\n'
printf 'Graphe Unity exact: ON\n'
printf 'Analyse Assembly-CSharp.mdl en lecture seule: ON\n'
printf 'TypeDef / MethodDef / appels CLR valides: ON\n'
printf 'Recettes mouvement avec confiance: ON\n'
printf 'Cache V40 separe de audit/index visuel: ON\n'
printf 'Mouvement synthetique: OFF\n'
exec python scripts/lastwar-global-graphics-server-v40-agent.py "$ROOT"
