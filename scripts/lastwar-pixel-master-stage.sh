#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="portal-auth-lastwar-lab-v1"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || {
  echo "ERREUR: branche active $(git branch --show-current), attendu $BRANCH" >&2
  exit 1
}

echo "=== WFGG LAST WAR — PIXEL MASTER STAGE ==="
echo "CODE ONLY · aucun rendu de substitution · aucun appel réseau Last War"

echo
echo "[1/2] Assets UI exacts + inventaire/export modèles Unity"
bash scripts/lastwar-phase35-pixel-master.sh

echo
echo "[2/2] Contrôles natifs exacts"
bash scripts/lastwar-phase35b-native-controls.sh

echo
echo "=== PIXEL MASTER STAGE TERMINE ==="
echo "Ne lance pas encore la page Escouades."
echo "L'inventaire véhicule est maintenant versionné dans:"
echo "frontend/lab/master-assets-v2/meta/vehicle-model-inventory.json"
echo "Je peux ensuite construire le renderer véhicule exact à partir de cet inventaire."
