#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo 'ERREUR: branche LAB incorrecte' >&2; exit 1; }

echo '=== WFGG LAST WAR VISUAL INDEX INIT ==='
echo '1/3 Graphics master index'
bash scripts/lastwar-graphics-master-index-refresh.sh

echo '2/3 CLR known/unknown discovery atlas'
bash scripts/lastwar-code-discovery-atlas-refresh.sh

echo '3/3 Visual reconstruction graph'
bash scripts/lastwar-reconstruction-map-refresh.sh

echo '=== VISUAL INDEX INIT OK ==='
echo 'Query examples:'
echo '  python scripts/lastwar-reconstruction-map-query.py --bundle 6933 --depth 2 --recipe'
echo '  python scripts/lastwar-reconstruction-map-query.py --contains HeroShowBlend --depth 3 --recipe'
echo '  python scripts/lastwar-code-index-query.py --unknown'
echo '  python scripts/lastwar-code-index-query.py --tag render-camera'
