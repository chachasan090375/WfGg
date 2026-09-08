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
printf '\n=== WFGG V40.3.1 : AGENT + ASSEMBLAGE PREFAB EXACT ===\n'
printf 'Graphe Unity exact: ON\n'
printf 'Assembly-CSharp.mdl lecture seule: ON\n'
printf 'Appels MethodDef recursifs profondeur 7: ON\n'
printf 'Phases FRAME / INIT / STATE / TEARDOWN: ON\n'
printf 'Mouvement continu separe de initialisation: ON\n'
printf 'Scripts sous-prefabs exacts locaux: ON\n'
printf 'Assemblage prefab recursif profondeur 2: ON\n'
printf 'Etats assemblage: IDLE / WORK\n'
printf 'Transform parents nodePath exacts: ON\n'
printf 'ID WfGg exact: bypass filtre apercu client ON\n'
printf 'Sous-prefab sans racine animation: feuille non fatale ON\n'
printf 'Runtime auto: WORK puis IDLE uniquement: ON\n'
printf 'Cache agent separe de audit/index visuel: ON\n'
printf 'Geometrie synthetique: OFF\n'
printf 'Mouvement synthetique: OFF\n'
exec python scripts/lastwar-global-graphics-server-v403-agent-runtime.py "$ROOT"
