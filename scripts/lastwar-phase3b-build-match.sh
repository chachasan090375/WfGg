#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 3B
# The captured Android access token was issued by Last War 1.0.359 / build 1864.
# Upstream's pinned client still advertises Android 1.0.351 / 1835, while its own
# documentation states the access token is bound to AppVersion/VersionCode as well
# as package/platform. This script changes ONLY those two public build identifiers,
# rebuilds the already-local probe, then retries the same read-only login.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
LAB_HOME="${BASE}/home"
BIN="${BASE}/lastwar-client"
SESSION="${LAB_HOME}/.lastwar_goclient_session.json"
DOWNLOADS="${HOME}/storage/downloads"
OUT_PRIVATE="${BASE}/WFGG_LASTWAR_PHASE3B_BUILD_MATCH_REDACTED.txt"
OUT_SHARE="${DOWNLOADS}/WFGG_LASTWAR_PHASE3B_BUILD_MATCH_REDACTED.txt"
GSL_FILE="${SRC}/internal/gsl/gsl.go"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -d "$SRC/.git" ]] || die "source locale du probe absente"
[[ -s "$SESSION" ]] || die "session extraite du PCAP absente; exécute d'abord la phase 3"
[[ -f "$GSL_FILE" ]] || die "gsl.go introuvable"

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 3B ==="
say "Alignement identité publique du client: 1.0.359 / build 1864"
say "Aucun token, deviceId ou shumeiBoxId ne sera affiché."
say "Aucune commande -collect ne sera utilisée."

# Idempotent replacement: accept either the original upstream values or a prior 3B run.
python - "$GSL_FILE" <<'PY'
from pathlib import Path
import re, sys
p = Path(sys.argv[1])
s = p.read_text()
s2, n1 = re.subn(r'(?m)^\s*AppVersion\s*=\s*"[^"]+"\s*$', '\tAppVersion  = "1.0.359"', s, count=1)
s3, n2 = re.subn(r'(?m)^\s*VersionCode\s*=\s*"[^"]+"\s*$', '\tVersionCode = "1864"', s2, count=1)
if n1 != 1 or n2 != 1:
    raise SystemExit(f"patch build impossible: AppVersion={n1}, VersionCode={n2}")
p.write_text(s3)
PY

grep -q 'AppVersion  = "1.0.359"' "$GSL_FILE" || die "AppVersion non alignée"
grep -q 'VersionCode = "1864"' "$GSL_FILE" || die "VersionCode non aligné"

say "Recompilation du client de laboratoire…"
cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$BIN" ./cmd/lastwar-client
chmod 700 "$BIN"

say "Test de reconnexion lecture seule…"
set +e
HOME="$LAB_HOME" "$BIN" -config "$SESSION" -list-buildings -log-level info >"$OUT_PRIVATE" 2>&1
RC=$?
set -e
chmod 600 "$OUT_PRIVATE" 2>/dev/null || true

if [[ -d "$DOWNLOADS" ]]; then
  cp -f "$OUT_PRIVATE" "$OUT_SHARE"
  chmod 600 "$OUT_SHARE" 2>/dev/null || true
fi

say "=== PHASE 3B TERMINEE ==="
say "EXIT=$RC"
say "Identité publique utilisée: Android 1.0.359 / 1864"
if [[ -f "$OUT_SHARE" ]]; then
  say "Rapport expurgé: Téléchargements/WFGG_LASTWAR_PHASE3B_BUILD_MATCH_REDACTED.txt"
else
  say "Rapport expurgé privé: $OUT_PRIVATE"
fi
say
say "--- dernières lignes expurgées ---"
tail -n 45 "$OUT_PRIVATE" 2>/dev/null || true

exit "$RC"
