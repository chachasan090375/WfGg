#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Termux may already have another command named `go` in PATH.
# The Last War probe needs the actual Go compiler from the Termux prefix.
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"

if [[ ! -x "$REAL_GO" ]]; then
  echo "Installation du compilateur Go Termux…"
  pkg install -y golang
fi

if [[ ! -x "$REAL_GO" ]]; then
  echo "ERREUR: compilateur Go introuvable dans $REAL_GO" >&2
  exit 1
fi

echo "Compilateur utilisé :"
"$REAL_GO" version

export PATH="${TERMUX_PREFIX}/bin:${PATH}"
exec bash scripts/lastwar-termux-probe.sh
