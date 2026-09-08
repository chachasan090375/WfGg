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
printf '\n=== WFGG V40.4.1 : AGENT + RENDU JEU EXACT RECOVERY ===\n'
printf 'Graphe Unity exact: ON\n'
printf 'Assembly-CSharp.mdl lecture seule: ON\n'
printf 'Appels MethodDef recursifs profondeur 7: ON\n'
printf 'Mouvement continu separe de initialisation: ON\n'
printf 'Assemblage prefab recursif profondeur 3: ON\n'
printf 'Etats assemblage: IDLE / WORK\n'
printf 'Transform parents: exact ou suffixe unique prouve ON\n'
printf 'Materiaux / Texture2D exacts par PPtr: ON\n'
printf 'UV + WebGL: ON\n'
printf 'Recovery V40.4.1: reutilise session V40.3 deja validee ON\n'
printf 'Retry OBJ: URL originale + endpoint canonique model-file ON\n'
printf 'Recalcul graphe pendant recovery: OFF\n'
printf 'Cache agent separe de audit/index visuel: ON\n'
printf 'Geometrie synthetique: OFF\n'
printf 'Texture synthetique: OFF\n'
printf 'Mouvement synthetique: OFF\n'
exec python scripts/lastwar-global-graphics-server-v4041-agent-runtime.py "$ROOT"
