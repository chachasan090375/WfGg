#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
if [ "$(git branch --show-current)" != "$BRANCH" ]; then
  echo "ERREUR: branche active=$(git branch --show-current), attendu=$BRANCH" >&2
  exit 2
fi
printf '\n=== MURPHY / AUDIE FRAGMENT MATERIALIZE V30 ===\n'
python scripts/lastwar-murphy-fragment-materialize-v30.py "$ROOT"
printf '\n=== REBUILD VISUAL DATA V29 ===\n'
python scripts/lastwar-murphy-visual-review-build-v29.py "$ROOT"
printf '\nRecharge le même viewer :\nhttp://127.0.0.1:8788/lab/lastwar-murphy-visual-review-v29.html?v=30\n'
