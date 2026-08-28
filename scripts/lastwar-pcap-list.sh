#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — inspect a PCAP/PCAPNG exported by PCAPdroid.
# Safe-by-default: it only LISTS conversations and produces REDACTED decode
# output using upstream StringRedacted(); no credential is written to WfGg.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
PCAP_BIN="${BASE}/pcap"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PCAP_REDACTED.txt"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -d "$SRC/.git" ]] || die "source du probe absente; exécute d'abord la phase 1"
[[ -d "$DOWNLOADS" ]] || die "accès Téléchargements absent; exécute termux-setup-storage"

CAPTURE="${1:-}"
if [[ -z "$CAPTURE" ]]; then
  CAPTURE="$({
    find "$DOWNLOADS" -maxdepth 4 -type f \( -iname '*.pcap' -o -iname '*.pcapng' -o -iname '*.cap' \) -printf '%T@ %p\n' 2>/dev/null || true
  } | sort -nr | head -n1 | cut -d' ' -f2-)"
fi
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun fichier .pcap/.pcapng trouvé dans Téléchargements"

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · inspection PCAP ==="
say "Capture: $CAPTURE"
say "Compilation de l'analyseur local…"
cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$PCAP_BIN" ./cmd/pcap
chmod 700 "$PCAP_BIN"

say
say "=== CONVERSATIONS ==="
LIST="$($PCAP_BIN -in "$CAPTURE" -list 2>&1)"
printf '%s\n' "$LIST"

# Upstream sorts the useful plain conversations before TLS and notes the game
# socket is usually idx 0. Decode idx 0 for a first-pass quality check; if the
# capture has another candidate, the user can pass it manually later.
say
say "=== DECODE REDACTE DU STREAM 0 ==="
{
  printf 'Capture: %s\n\n' "$CAPTURE"
  printf '%s\n\n' "$LIST"
  "$PCAP_BIN" -in "$CAPTURE" -stream 0 -decode
} > "$OUT" 2>&1 || true
chmod 600 "$OUT" 2>/dev/null || true

tail -n 35 "$OUT" 2>/dev/null || true
say
say "Fichier à partager (expurgé): Téléchargements/WFGG_LASTWAR_PCAP_REDACTED.txt"
say "Ne partage PAS le fichier PCAP brut: il peut contenir des identifiants de session en clair."
