#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — HeroShow structural discovery + durable graphics index refresh.
# This wrapper guarantees that every discovery from the HeroShow scan is folded
# into the reusable graphics master index before the workflow is considered done.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== HEROSHOW STRUCTURE + MASTER INDEX ==="
bash scripts/lastwar-heroshow-structure-fingerprint.sh

echo
echo "=== RAFRAICHISSEMENT INDEX GRAPHIQUE MAITRE ==="
bash scripts/lastwar-graphics-master-index.sh

echo
echo "=== HEROSHOW + MASTER INDEX TERMINE ==="
echo "Index JSON : frontend/lab/master-assets-v2/meta/graphics-master-index-v1.json"
echo "Lookup TSV : frontend/lab/master-assets-v2/meta/graphics-master-index-v1.tsv"
echo "A partir de maintenant, les futurs travaux graphiques doivent interroger cet index avant tout nouveau scan lourd."
