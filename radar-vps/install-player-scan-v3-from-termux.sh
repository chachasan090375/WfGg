#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Radar — READONLY player scan v3 installer.
# V3 no longer depends on a captured literal pseudo. It learns the map-query
# templates from the PCAP, indexes player bases, then enriches matches through
# get.user.info.multi when that read-only template is available.
# No Last War access token is copied to or stored on the VPS.

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
REPO_RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/radar-production-v1/radar-vps/release"
REMOTE_PRIVATE="/opt/wfgg-radar/private"
REMOTE_CAPTURE="$REMOTE_PRIVATE/lastwar-native-capture.pcap"
REMOTE_ENV="/opt/wfgg-radar/radar.env"
REMOTE_BIN="/opt/wfgg-radar/bin"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

for cmd in python3 curl ssh scp sha256sum; do command -v "$cmd" >/dev/null 2>&1 || die "$cmd absent"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say "SSH_ROUTE=ChaChaVPS"
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
    say "SSH_ROUTE=PUBLIC_IPV4"
  else
    die "ChaChaVPS inaccessible via Tailscale et IPv4 publique"
  fi
fi

say "=== WfGg Radar · Player Scan READONLY v3 ==="
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

say "2/6 Téléchargement de la release v3"
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
RCAP="/tmp/wfgg-radar-v3-$TAG.pcap"
RCON="/tmp/wfgg-radar-connector-v3-$TAG"
RNAT="/tmp/wfgg-radar-native-v3-$TAG"
scp "${SSH_OPTS[@]}" -q "$CAPTURE" "$REMOTE:$RCAP"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-connector" "$REMOTE:$RCON"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-native-template" "$REMOTE:$RNAT"

say "4/6 Installation atomique sur le VPS"
ssh "${SSH_OPTS[@]}" "$REMOTE" "set -eu; install -d -o root -g wfgg-radar -m 0750 '$REMOTE_PRIVATE'; install -d -o root -g root -m 0755 '$REMOTE_BIN'; install -o root -g wfgg-radar -m 0640 '$RCAP' '$REMOTE_CAPTURE'; install -o root -g root -m 0755 '$RCON' '$REMOTE_BIN/radar-connector'; install -o root -g root -m 0755 '$RNAT' '$REMOTE_BIN/radar-native-template'; rm -f '$RCAP' '$RCON' '$RNAT'" </dev/null

say "5/6 Activation du moteur READONLY v3"
PYHELPER="$TMP/install-v3-context.py"
cat > "$PYHELPER" <<'PY'
import os, pathlib, sys, tempfile
env_path, capture_path = sys.argv[1:3]
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
    'LASTWAR_CLIENT_TIMEOUT_SECONDS=75',
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
print('PLAYER_SCAN_V3_CONTEXT=INSTALLED')
print('LEGACY_SCAN_SEED=REMOVED')
print('ACCESS_TOKEN_STORED_ON_VPS=NO')
PY
RPY="/tmp/wfgg-radar-v3-context-$TAG.py"
scp "${SSH_OPTS[@]}" -q "$PYHELPER" "$REMOTE:$RPY"
ssh "${SSH_OPTS[@]}" "$REMOTE" "set -eu; python3 '$RPY' '$REMOTE_ENV' '$REMOTE_CAPTURE'; rm -f '$RPY'; systemctl restart wfgg-radar-connector; sleep 2; test \"\$(systemctl is-active wfgg-radar-connector)\" = active; echo SERVICE=active" </dev/null

say "6/6 Contrôle final"
ssh "${SSH_OPTS[@]}" "$REMOTE" "set -eu; test -s '$REMOTE_CAPTURE'; ! grep -q '^LASTWAR_NATIVE_SCAN_SEED=' '$REMOTE_ENV'; test -x '$REMOTE_BIN/radar-native-template'; test -x '$REMOTE_BIN/radar-connector'; strings '$REMOTE_BIN/radar-native-template' | grep -Fq 'native-template-readonly-v3'; echo PLAYER_SCAN_V3=READY; echo STRATEGY=world.get.block+get.user.info.multi; echo ACCESS_TOKEN_ON_VPS=NO" </dev/null
say "=== PLAYER SCAN READONLY V3 : OK ==="
