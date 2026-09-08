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
printf '\n=== WFGG V40.5 : AGENT + TRACE RUNTIME EXACTE ===\n'
printf 'Graphe Unity exact: ON\n'
printf 'Assembly-CSharp.mdl lecture seule: ON\n'
printf 'Appels MethodDef recursifs profondeur 7: ON\n'
printf 'Chemin runtime: prefab serialise -> LWGA -> bundle -> BundleFragment/APK -> offset/span: ON\n'
printf 'Appels LoadAsset / LoadPrefab / ResourceManager / Instantiate: TRACE ON\n'
printf 'Litteraux de chemins C#: candidats tant que non joints a une relation serialisee: ON\n'
printf 'Diagnostic Material -> Texture2D exact et erreurs cache: ON\n'
printf 'Mouvement continu: chaine CLR prouvee ON; cible/axe/vitesse restent proof-gated\n'
printf 'Rendu V40.4.1 geometrie/UV recovery: ON\n'
printf 'Cache agent separe de audit/index visuel: ON\n'
printf 'Geometrie synthetique: OFF\n'
printf 'Texture synthetique: OFF\n'
printf 'Mouvement synthetique: OFF\n'
exec python scripts/lastwar-global-graphics-server-v405-agent-runtime.py "$ROOT"
