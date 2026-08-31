#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent (pkg install -y android-tools)"
printf 'FORMATION_LIVE_TRACE_PAIR_V2_START\n'
printf '%s\n' 'Cette version n’utilise PAS mDNS.'
printf '%s\n' '1) Android > Options développeur > Débogage sans fil > Associer appareil avec code de jumelage.'
printf 'Adresse IP et port de JUMELAGE (ex: 192.168.1.20:37123): '
IFS= read -r PAIR_EP
printf 'Code de jumelage à 6 chiffres: '
IFS= read -r PAIR_CODE
[[ "$PAIR_EP" == *:* && "$PAIR_CODE" =~ ^[0-9]{6}$ ]] || fail "adresse de jumelage ou code invalide"
printf '%s\n' '--- ADB PAIR ---'
adb pair "$PAIR_EP" "$PAIR_CODE"
printf '\n%s\n' '2) Reviens sur l’écran principal « Débogage sans fil ». Relève la ligne « Adresse IP et port » (ce port est souvent différent du port de jumelage).'
printf 'Adresse IP et port de CONNEXION (ex: 192.168.1.20:41237): '
IFS= read -r CONNECT_EP
[[ "$CONNECT_EP" == *:* ]] || fail "adresse de connexion invalide"
printf '%s\n' '--- ADB CONNECT ---'
adb connect "$CONNECT_EP" || true
sleep 1
printf '%s\n' '--- ADB DEVICES ---'
adb devices -l || true
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}')"
if [[ -z "$SERIAL" ]]; then
  printf 'RESULT=PAIR_DONE_BUT_NOT_CONNECTED\n'
  printf 'Vérifie que le Débogage sans fil est toujours activé et que tu as utilisé le port de CONNEXION de l’écran principal, pas le port de jumelage.\n'
  exit 3
fi
printf 'RESULT=ADB_CONNECTED serial=%s\n' "$SERIAL"
printf 'package='; adb -s "$SERIAL" shell pm path "$PKG" 2>/dev/null | head -1 | tr -d '\r' || true
printf 'pid='; adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' || true; printf '\n'
printf 'NEXT=bash scripts/lastwar-formation-live-trace-v1.sh start "Murphy -> autre héros"\n'
