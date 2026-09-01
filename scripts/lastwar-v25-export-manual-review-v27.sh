#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
BRANCH="portal-auth-lastwar-lab-v1"
CUR="$(git branch --show-current)"
if [ "$CUR" != "$BRANCH" ]; then
  echo "ERREUR: branche active=$CUR, attendu=$BRANCH" >&2
  exit 2
fi
python scripts/lastwar-v25-export-manual-review-v27.py "$PWD"
git add frontend/lab/manual-review-v27/inbox
if git diff --cached --quiet; then
  echo "Aucun changement à publier."
else
  git commit -m "lab: upload V25 candidates for manual Murphy/Audie review"
  git push origin "$BRANCH"
fi
echo "OK — corpus V27 publié pour revue manuelle."
