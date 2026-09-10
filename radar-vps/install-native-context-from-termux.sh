#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Radar — secure native-template context installer
# Runs on the owner's Termux phone. It never prints or uploads accessToken.
# It copies only a sanitized session context and the user's own native PCAP
# over the existing SSH alias ChaChaVPS, then restarts the read-only connector.

SESSION="$HOME/.wfgg-lastwar-probe/home/.lastwar_goclient_session.json"
REMOTE="ChaChaVPS"
REMOTE_PRIVATE="/opt/wfgg-radar/private"
REMOTE_CONTEXT="$REMOTE_PRIVATE/lastwar-session-context.json"
REMOTE_CAPTURE="$REMOTE_PRIVATE/lastwar-native-capture.pcap"
REMOTE_ENV="/opt/wfgg-radar/radar.env"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

PY="$(command -v python3 || command -v python || true)"
[[ -n "$PY" ]] || die "Python absent dans Termux"
command -v ssh >/dev/null 2>&1 || die "ssh absent"
command -v scp >/dev/null 2>&1 || die "scp absent"
[[ -s "$SESSION" ]] || die "session Phase 3 absente: $SESSION"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
CTX="$TMP/session-context.json"

say "=== WfGg Radar · récupération Phase 5 ==="
say "1/6 Vérification de la session historique locale"

"$PY" - "$SESSION" "$CTX" <<'PY'
import json, os, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, 'r', encoding='utf-8') as f:
    data = json.load(f)
required = ['zone', 'gameUid', 'deviceId', 'shumeiBoxId']
missing = [k for k in required if not str(data.get(k, '')).strip()]
if missing:
    raise SystemExit('SESSION_INCOMPLETE=' + ','.join(missing))
out = {
    'ip': data.get('ip', ''),
    'port': int(data.get('port') or 0),
    'zone': str(data['zone']),
    'gameUid': str(data['gameUid']),
    'deviceId': str(data['deviceId']),
    'shumeiBoxId': str(data['shumeiBoxId']),
    'iosMode': bool(data.get('iosMode', False)),
}
# accessToken is deliberately excluded.
with open(dst, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
os.chmod(dst, 0o600)
print('SESSION_CONTEXT=OK')
print('ACCESS_TOKEN_EXPORTED=NO')
PY

say "2/6 Recherche du PCAP natif historique"
CAPTURE="$("$PY" - <<'PY'
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
        # Keep the search bounded enough for Android storage.
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
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun PCAP/PCAPNG historique trouvé"
CAP_SIZE="$(wc -c < "$CAPTURE" | tr -d ' ')"
say "PCAP=FOUND bytes=$CAP_SIZE"

say "3/6 Préparation du coffre privé sur ChaChaVPS"
ssh "$REMOTE" "set -eu; id wfgg-radar >/dev/null; install -d -o root -g wfgg-radar -m 0750 '$REMOTE_PRIVATE'"

TAG="$$"
RCTX="/tmp/wfgg-radar-context-$TAG.json"
RCAP="/tmp/wfgg-radar-capture-$TAG.pcap"

say "4/6 Transfert chiffré SSH (aucun credential affiché)"
scp -q "$CTX" "$REMOTE:$RCTX"
scp -q "$CAPTURE" "$REMOTE:$RCAP"

ssh "$REMOTE" "set -eu; install -o root -g wfgg-radar -m 0640 '$RCTX' '$REMOTE_CONTEXT'; install -o root -g wfgg-radar -m 0640 '$RCAP' '$REMOTE_CAPTURE'; rm -f '$RCTX' '$RCAP'"

say "5/6 Activation native-template-readonly-v1"
ssh "$REMOTE" python3 - "$REMOTE_CONTEXT" "$REMOTE_CAPTURE" "$REMOTE_ENV" <<'PY'
import json, os, pathlib, sys, tempfile
ctx_path, capture_path, env_path = map(pathlib.Path, sys.argv[1:4])
ctx = json.loads(ctx_path.read_text(encoding='utf-8'))
if 'accessToken' in ctx:
    raise SystemExit('ACCESS_TOKEN_FORBIDDEN_IN_SERVER_CONTEXT')
raw = json.dumps(ctx, ensure_ascii=False, separators=(',', ':'))
if "'" in raw or '\n' in raw or '\r' in raw:
    raise SystemExit('SESSION_CONTEXT_UNSAFE_FOR_ENVFILE')
p = pathlib.Path(env_path)
lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []
keys = {
    'LASTWAR_SESSION_CONTEXT_JSON',
    'LASTWAR_NATIVE_CAPTURE',
    'LASTWAR_NATIVE_TEMPLATE_BIN',
    'LASTWAR_CLIENT_TIMEOUT_SECONDS',
}
kept = [line for line in lines if line.split('=',1)[0].strip() not in keys]
kept += [
    "LASTWAR_SESSION_CONTEXT_JSON='" + raw + "'",
    'LASTWAR_NATIVE_CAPTURE=' + str(capture_path),
    'LASTWAR_NATIVE_TEMPLATE_BIN=/opt/wfgg-radar/bin/radar-native-template',
    'LASTWAR_CLIENT_TIMEOUT_SECONDS=45',
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
print('SERVER_CONTEXT=INSTALLED')
print('ACCESS_TOKEN_STORED_ON_VPS=NO')
PY

ssh "$REMOTE" "set -eu; systemctl restart wfgg-radar-connector; sleep 2; test \"\$(systemctl is-active wfgg-radar-connector)\" = active; echo SERVICE=active; journalctl -u wfgg-radar-connector -n 12 --no-pager | grep -E 'radar connector listening|protocol=' | tail -n 1"

say "6/6 Contrôle de présence sans afficher les secrets"
ssh "$REMOTE" "set -eu; test -r '$REMOTE_CAPTURE'; test -s '$REMOTE_CONTEXT'; grep -q '^LASTWAR_SESSION_CONTEXT_JSON=' '$REMOTE_ENV'; grep -q '^LASTWAR_NATIVE_CAPTURE=' '$REMOTE_ENV'; echo NATIVE_CONTEXT=READY; echo ACCESS_TOKEN_ON_VPS=NO"

say "=== PHASE 5 CONTEXT VPS : OK ==="
