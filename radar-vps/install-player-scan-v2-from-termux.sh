#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Radar — READONLY player scan v2 installer.
# Run after creating a fresh PCAP containing one in-game player search.
# No access token is copied to or stored on the VPS.

SEED="${1:-Zazavibes}"
REMOTE="ChaChaVPS"
REPO_RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/radar-production-v1/radar-vps/release"
REMOTE_PRIVATE="/opt/wfgg-radar/private"
REMOTE_CAPTURE="$REMOTE_PRIVATE/lastwar-native-capture.pcap"
REMOTE_ENV="/opt/wfgg-radar/radar.env"
REMOTE_BIN="/opt/wfgg-radar/bin"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -n "${SEED//[[:space:]]/}" ]] || die "pseudo de calibration vide"
[[ "$SEED" != *"'"* && "$SEED" != *$'\n'* && "$SEED" != *$'\r'* ]] || die "pseudo de calibration non supporté"
for cmd in python3 curl ssh scp sha256sum; do command -v "$cmd" >/dev/null 2>&1 || die "$cmd absent"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

say "=== WfGg Radar · Player Scan READONLY v2 ==="
say "1/6 Recherche du PCAP le plus récent"
CAPTURE="$(python3 - <<'PY'
import os
roots = [
    os.path.expanduser('~/storage/downloads'),
    os.path.expanduser('~/storage/shared/Download'),
    os.path.expanduser('~/storage/shared/Documents'),
    os.path.expanduser('~/storage/shared/PCAPdroid'),
    '/storage/emulated/0/Download',
    '/storage/emulated/0/Documents',
]
exts = ('.pcap', '.pcapng', '.cap')
best = None
for root in roots:
    if not os.path.exists(root):
        continue
    for base, dirs, files in os.walk(root):
        rel = os.path.relpath(base, root)
        if rel != '.' and rel.count(os.sep) >= 6:
            dirs[:] = []
        for name in files:
            if not name.lower().endswith(exts):
                continue
            p = os.path.join(base, name)
            try:
                item = (os.path.getmtime(p), p)
            except OSError:
                continue
            if best is None or item > best:
                best = item
if best:
    print(best[1])
PY
)"
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun PCAP/PCAPNG trouvé"
say "PCAP=FOUND bytes=$(wc -c < "$CAPTURE" | tr -d ' ')"
say "SCAN_SEED=$SEED"

say "2/6 Téléchargement de la release v2"
curl -fsSL "$REPO_RAW/SHA256SUMS" -o "$TMP/SHA256SUMS"
curl -fsSL "$REPO_RAW/radar-connector" -o "$TMP/radar-connector"
curl -fsSL "$REPO_RAW/radar-native-template" -o "$TMP/radar-native-template"
(
  cd "$TMP"
  sha256sum -c SHA256SUMS
) >/dev/null
chmod 0755 "$TMP/radar-connector" "$TMP/radar-native-template"
say "RELEASE_SHA256=OK"

say "3/6 Transfert chiffré vers ChaChaVPS"
TAG="$$"
RCAP="/tmp/wfgg-radar-scan-$TAG.pcap"
RCON="/tmp/wfgg-radar-connector-$TAG"
RNAT="/tmp/wfgg-radar-native-$TAG"
scp -q "$CAPTURE" "$REMOTE:$RCAP"
scp -q "$TMP/radar-connector" "$REMOTE:$RCON"
scp -q "$TMP/radar-native-template" "$REMOTE:$RNAT"

say "4/6 Installation atomique sur le VPS"
ssh "$REMOTE" "set -eu; install -d -o root -g wfgg-radar -m 0750 '$REMOTE_PRIVATE'; install -d -o root -g root -m 0755 '$REMOTE_BIN'; install -o root -g wfgg-radar -m 0640 '$RCAP' '$REMOTE_CAPTURE'; install -o root -g root -m 0755 '$RCON' '$REMOTE_BIN/radar-connector'; install -o root -g root -m 0755 '$RNAT' '$REMOTE_BIN/radar-native-template'; rm -f '$RCAP' '$RCON' '$RNAT'"

say "5/6 Activation du gabarit de recherche READONLY"
printf '%s' "$SEED" | base64 -w0 > "$TMP/seed.b64"
SEED_B64="$(cat "$TMP/seed.b64")"
ssh "$REMOTE" python3 - "$REMOTE_ENV" "$REMOTE_CAPTURE" "$SEED_B64" <<'PY'
import base64, os, pathlib, sys, tempfile
env_path, capture_path, seed_b64 = sys.argv[1:4]
seed = base64.b64decode(seed_b64).decode('utf-8')
if not seed.strip() or "'" in seed or '\n' in seed or '\r' in seed:
    raise SystemExit('SCAN_SEED_UNSAFE')
p = pathlib.Path(env_path)
lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []
keys = {
    'LASTWAR_NATIVE_CAPTURE',
    'LASTWAR_NATIVE_TEMPLATE_BIN',
    'LASTWAR_NATIVE_SCAN_SEED',
    'LASTWAR_CLIENT_TIMEOUT_SECONDS',
}
kept = [line for line in lines if line.split('=', 1)[0].strip() not in keys]
kept += [
    'LASTWAR_NATIVE_CAPTURE=' + capture_path,
    'LASTWAR_NATIVE_TEMPLATE_BIN=/opt/wfgg-radar/bin/radar-native-template',
    "LASTWAR_NATIVE_SCAN_SEED='" + seed + "'",
    'LASTWAR_CLIENT_TIMEOUT_SECONDS=60',
]
fd, tmp = tempfile.mkstemp(prefix='.radar-env-', dir=str(p.parent))
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write('\n'.join(kept) + '\n')
        f.flush(); os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)
finally:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
print('SCAN_CONTEXT=INSTALLED')
print('ACCESS_TOKEN_STORED_ON_VPS=NO')
PY

ssh "$REMOTE" "set -eu; systemctl restart wfgg-radar-connector; sleep 2; test \"\$(systemctl is-active wfgg-radar-connector)\" = active; echo SERVICE=active; journalctl -u wfgg-radar-connector -n 20 --no-pager | grep -E 'radar connector listening' | tail -n 1"

say "6/6 Contrôle final"
ssh "$REMOTE" "set -eu; test -s '$REMOTE_CAPTURE'; grep -q '^LASTWAR_NATIVE_SCAN_SEED=' '$REMOTE_ENV'; test -x '$REMOTE_BIN/radar-native-template'; test -x '$REMOTE_BIN/radar-connector'; echo PLAYER_SCAN_V2=READY; echo ACCESS_TOKEN_ON_VPS=NO"
say "=== PLAYER SCAN READONLY V2 : OK ==="
