#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB phase 2 — read-only reconnect probe.
# This deliberately does NOT ask for email/code and does NOT use -collect.
# It temporarily hides the persisted loginKey so the pinned client chooses
# GSL opt=fix from the already-persisted gameUid, then restores loginKey.

BASE="${HOME}/.wfgg-lastwar-probe"
LAB_HOME="${BASE}/home"
BIN="${BASE}/lastwar-client"
LOGINKEY="${LAB_HOME}/.lastwar_goclient_loginkey"
BACKUP="${LAB_HOME}/.lastwar_goclient_loginkey.wfgg-phase2-backup"
DOWNLOADS="${HOME}/storage/downloads"
OUT_PRIVATE="${BASE}/WFGG_LASTWAR_PHASE2_READONLY.txt"
OUT_SHARE="${DOWNLOADS}/WFGG_LASTWAR_PHASE2_READONLY.txt"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

restore_login_key() {
  if [[ -f "$BACKUP" ]]; then
    rm -f "$LOGINKEY" 2>/dev/null || true
    mv "$BACKUP" "$LOGINKEY"
    chmod 600 "$LOGINKEY" 2>/dev/null || true
  fi
}
trap restore_login_key EXIT INT TERM

[[ -x "$BIN" ]] || die "binaire du probe introuvable: $BIN"
[[ -d "$LAB_HOME" ]] || die "HOME du laboratoire introuvable: $LAB_HOME"
[[ -s "$LAB_HOME/.lastwar_goclient_gameuid" ]] || die "gameUid local absent; phase 1 requise"
[[ -s "$LOGINKEY" ]] || die "loginKey local absent; phase 1 requise"
[[ ! -e "$BACKUP" ]] || die "backup loginKey déjà présent: $BACKUP (ne rien supprimer; demander vérification)"

say "=== WfGg Last War LAB · PHASE 2 lecture seule ==="
say "Test de reconnexion via gameUid (GSL opt=fix), sans e-mail ni code."
say "Aucune commande de collecte/automatisation ne sera envoyée."

mv "$LOGINKEY" "$BACKUP"
chmod 600 "$BACKUP" 2>/dev/null || true

set +e
HOME="$LAB_HOME" "$BIN" -no-config -list-buildings -log-level info >"$OUT_PRIVATE" 2>&1
RC=$?
set -e

restore_login_key
trap - EXIT INT TERM

chmod 600 "$OUT_PRIVATE" 2>/dev/null || true

if [[ -d "$DOWNLOADS" ]]; then
  cp -f "$OUT_PRIVATE" "$OUT_SHARE"
  chmod 600 "$OUT_SHARE" 2>/dev/null || true
fi

say "=== PHASE 2 TERMINEE ==="
say "EXIT=$RC"
if [[ -f "$OUT_SHARE" ]]; then
  say "Fichier: Téléchargements/WFGG_LASTWAR_PHASE2_READONLY.txt"
else
  say "Fichier privé: $OUT_PRIVATE"
fi
say "loginKey restauré localement: oui"
say
say "--- dernières lignes expurgées ---"
tail -n 35 "$OUT_PRIVATE" 2>/dev/null || true

exit "$RC"
