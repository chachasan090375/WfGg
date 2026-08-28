#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WFGG_LASTWAR_TERMUX_PROBE_V2
# Preview/laboratory helper only. Nothing here touches WfGg main or production D1.
#
# Purpose:
# - build a pinned, public Apache-2.0 Last War protocol client in an isolated directory;
# - perform the proven guest -> email code -> account flow locally on the user's device;
# - write ONE redacted account snapshot for data-inventory work;
# - never print or export loginKey/access tokens/verification codes.

UPSTREAM_REPO="https://github.com/ljagiello/lastwar-client.git"
UPSTREAM_COMMIT="ee5f64de160a8051c2f9f98189b75038dd225a0a"
BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
LAB_HOME="${BASE}/home"
BIN="${BASE}/lastwar-client"
LOG="${BASE}/probe.log"
SNAPSHOT="${BASE}/WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt"
FIFO="${BASE}/verification-code.pipe"
DOWNLOADS="${HOME}/storage/downloads"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  rm -f "$FIFO" 2>/dev/null || true
  if [[ -n "${CLIENT_PID:-}" ]] && kill -0 "$CLIENT_PID" 2>/dev/null; then
    kill "$CLIENT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

say "=== WfGg Last War LAB · probe local isolé ==="
say "Branche prévue : portal-auth-lastwar-lab-v1"
say "Aucun secret Last War ne sera envoyé vers GitHub ou la D1 WfGg."
say

for cmd in git go awk mkfifo grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "commande manquante: $cmd"
done

mkdir -p "$BASE" "$LAB_HOME"
chmod 700 "$BASE" "$LAB_HOME" 2>/dev/null || true

if [[ "${WFGG_PROBE_RESET:-0}" == "1" ]]; then
  say "RESET demandé : suppression de l'identité locale du laboratoire."
  rm -rf "$LAB_HOME"
  mkdir -p "$LAB_HOME"
  chmod 700 "$LAB_HOME" 2>/dev/null || true
  rm -f "$SNAPSHOT"
fi

if [[ -s "$SNAPSHOT" ]]; then
  say "Un snapshot expurgé existe déjà :"
  say "$SNAPSHOT"
  if [[ -d "$DOWNLOADS" ]]; then
    cp -f "$SNAPSHOT" "$DOWNLOADS/WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt"
    say "Copie disponible dans Téléchargements : WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt"
  fi
  say "Pour refaire volontairement une authentification neuve :"
  say "WFGG_PROBE_RESET=1 bash scripts/lastwar-termux-probe.sh"
  exit 0
fi

if [[ ! -d "$SRC/.git" ]]; then
  say "Téléchargement du client protocolaire public (commit épinglé)…"
  git clone --quiet --filter=blob:none "$UPSTREAM_REPO" "$SRC"
fi

cd "$SRC"
git fetch --quiet --depth 1 origin "$UPSTREAM_COMMIT"
git checkout --quiet --detach "$UPSTREAM_COMMIT"
git reset --quiet --hard "$UPSTREAM_COMMIT"

# Patch local-only #1: after the successful push.account.login.new, ask the upstream
# SFSObject formatter for its recursively REDACTED representation and save that
# representation to a private file. The upstream formatter masks credential keys
# at every nested level while keeping ordinary accountArr fields inspectable.
AUTH_FILE="$SRC/internal/auth/login.go"
TMP_FILE="$AUTH_FILE.wfgg.tmp"
awk '
  {
    print
    if ($0 ~ /^[[:space:]]*result\.Account = msg2\.Params[[:space:]]*$/) {
      print "\tif snapshotPath := os.Getenv(\"WFGG_LASTWAR_SNAPSHOT_PATH\"); snapshotPath != \"\" {"
      print "\t\tif err := os.WriteFile(snapshotPath, []byte(msg2.Params.StringRedacted()+\"\\n\"), 0o600); err != nil {"
      print "\t\t\tslog.Warn(\"failed to write WfGg redacted Last War probe snapshot\", \"error\", err)"
      print "\t\t}"
      print "\t}"
    }
  }
' "$AUTH_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$AUTH_FILE"
grep -q 'WFGG_LASTWAR_SNAPSHOT_PATH' "$AUTH_FILE" || die "patch de snapshot non appliqué"

# Patch local-only #2: Android/Termux can reject hard-link creation inside the app
# sandbox (EPERM), while the upstream client uses os.Link() to publish a new device-id
# state file atomically. Keep the upstream hard-link path first; only when it fails,
# fall back to O_CREATE|O_EXCL + fsync. EEXIST semantics are preserved, so concurrent
# identity creation is still rejected rather than overwritten.
IDENTITY_FILE="$SRC/internal/auth/identity.go"
TMP_FILE="$IDENTITY_FILE.wfgg.tmp"
awk '
  {
    if ($0 ~ /^[[:space:]]*return os\.Link\(tmpPath, path\)[[:space:]]*$/) {
      print "\tif err := os.Link(tmpPath, path); err == nil {"
      print "\t\treturn nil"
      print "\t}"
      print "\tf, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)"
      print "\tif err != nil {"
      print "\t\treturn err"
      print "\t}"
      print "\tcleanupCreated := true"
      print "\tdefer func() {"
      print "\t\t_ = f.Close()"
      print "\t\tif cleanupCreated {"
      print "\t\t\t_ = os.Remove(path)"
      print "\t\t}"
      print "\t}()"
      print "\tif _, err := f.WriteString(id); err != nil {"
      print "\t\treturn err"
      print "\t}"
      print "\tif err := f.Sync(); err != nil {"
      print "\t\treturn err"
      print "\t}"
      print "\tif err := f.Close(); err != nil {"
      print "\t\treturn err"
      print "\t}"
      print "\tcleanupCreated = false"
      print "\treturn nil"
      next
    }
    print
  }
' "$IDENTITY_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$IDENTITY_FILE"
grep -q 'cleanupCreated := true' "$IDENTITY_FILE" || die "patch Android device-id non appliqué"

say "Compilation du probe…"
GOTOOLCHAIN=auto go build -o "$BIN" ./cmd/lastwar-client
chmod 700 "$BIN"

# If a previous incomplete lab run already persisted a bearer loginKey but did not
# produce the redacted accountArr snapshot, do not silently reuse it: fast-path
# login would skip the email proof and cannot reconstruct accountArr.
if [[ -s "$LAB_HOME/.lastwar_goclient_loginkey" && ! -s "$SNAPSHOT" ]]; then
  die "état LAB incomplet détecté. Relance avec WFGG_PROBE_RESET=1 pour repartir proprement."
fi

printf 'Email du compte Last War (saisie masquée) : '
IFS= read -r -s LW_EMAIL
printf '\n'
[[ -n "$LW_EMAIL" ]] || die "email vide"

rm -f "$FIFO" "$LOG" "$SNAPSHOT"
mkfifo "$FIFO"
chmod 600 "$FIFO"

say "Ouverture d'une session Last War de laboratoire…"
HOME="$LAB_HOME" \
WFGG_LASTWAR_SNAPSHOT_PATH="$SNAPSHOT" \
"$BIN" -no-config -email "$LW_EMAIL" -code-pipe "$FIFO" -list-buildings >"$LOG" 2>&1 &
CLIENT_PID=$!
unset LW_EMAIL

say "Attente de l'acceptation de la demande de code…"
READY=0
for _ in $(seq 1 90); do
  if grep -q 'verification code should now be arriving' "$LOG" 2>/dev/null; then
    READY=1
    break
  fi
  if ! kill -0 "$CLIENT_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [[ "$READY" != "1" ]]; then
  wait "$CLIENT_PID" 2>/dev/null || true
  say "--- dernières lignes du journal expurgé ---"
  tail -n 30 "$LOG" 2>/dev/null || true
  die "le serveur n'a pas confirmé l'envoi du code dans le délai prévu"
fi

say "Le code Last War a été demandé. Consulte l'e-mail reçu."
printf 'Code Last War à 6 chiffres (saisie masquée) : '
IFS= read -r -s LW_CODE
printf '\n'
[[ "$LW_CODE" =~ ^[0-9]{6}$ ]] || die "le code doit contenir exactement 6 chiffres"
printf '%s\n' "$LW_CODE" > "$FIFO"
unset LW_CODE

say "Validation et lecture du snapshot…"
set +e
wait "$CLIENT_PID"
RC=$?
set -e
CLIENT_PID=""

if [[ "$RC" -ne 0 ]]; then
  say "--- dernières lignes du journal expurgé ---"
  tail -n 40 "$LOG" 2>/dev/null || true
  die "le client Last War a terminé avec le code $RC"
fi

[[ -s "$SNAPSHOT" ]] || die "authentification terminée mais snapshot expurgé absent"
chmod 600 "$SNAPSHOT" 2>/dev/null || true

GAME_UID_PRESENT="non"
USERNAME_PRESENT="non"
LOGIN_KEY_PRESENT="non"
[[ -s "$LAB_HOME/.lastwar_goclient_gameuid" ]] && GAME_UID_PRESENT="oui"
[[ -s "$LAB_HOME/.lastwar_goclient_username" ]] && USERNAME_PRESENT="oui"
[[ -s "$LAB_HOME/.lastwar_goclient_loginkey" ]] && LOGIN_KEY_PRESENT="oui"

say
say "=== PROBE OK ==="
say "gameUid persisté : $GAME_UID_PRESENT"
say "nom de rôle persisté : $USERNAME_PRESENT"
say "secret de reconnexion persisté localement : $LOGIN_KEY_PRESENT (valeur jamais affichée)"
say "snapshot expurgé : $SNAPSHOT"

if [[ -d "$DOWNLOADS" ]]; then
  cp -f "$SNAPSHOT" "$DOWNLOADS/WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt"
  say "Copie pour partage : Téléchargements/WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt"
else
  say "Pour l'avoir dans Téléchargements, exécute une fois : termux-setup-storage"
  say "puis relance simplement le script : il copiera le snapshot existant sans refaire l'authentification."
fi

say
say "Le code e-mail n'a pas été conservé. Le loginKey reste uniquement dans le HOME privé du laboratoire Termux."
say "Tu peux maintenant me transmettre UNIQUEMENT le fichier WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt."
