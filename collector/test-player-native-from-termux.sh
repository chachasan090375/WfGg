#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

QUERY="${1:-zazavibes}"
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SESSION="${HOME}/.wfgg-lastwar-probe/home/.lastwar_goclient_session.json"

[[ -s "$SESSION" ]] || { echo 'ERROR=LOCAL_SESSION_MISSING'; exit 2; }
[[ -n "${QUERY//[[:space:]]/}" ]] || { echo 'ERROR=QUERY_EMPTY'; exit 2; }
for cmd in python3 ssh scp; do command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR=${cmd}_MISSING"; exit 2; }; done

python3 - "$SESSION" <<'PY' >/dev/null
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    d=json.load(f)
if len(str(d.get('accessToken','')).strip()) < 8:
    raise SystemExit(2)
PY

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  echo 'SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || { echo 'ERROR=VPS_UNREACHABLE'; exit 2; }
  echo 'SSH_ROUTE=PUBLIC_IPV4'
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
HELPER="$TMP/collector-native-test.py"
cat > "$HELPER" <<'PY'
import json,os,subprocess,sys,tempfile,urllib.request

raw=sys.stdin.read()
try:
    incoming=json.loads(raw)
except Exception:
    print('ERROR=INPUT_PARSE_FAILED')
    raise SystemExit(2)
query=str(incoming.pop('_query','')).strip()
if not query:
    print('ERROR=QUERY_EMPTY')
    raise SystemExit(2)

native='/opt/wfgg-collector/bin/radar-native-template'
capture='/opt/wfgg-radar/private/lastwar-native-capture.pcap'
if not (os.path.isfile(native) and os.access(native,os.X_OK)):
    print('ERROR=COLLECTOR_NATIVE_MISSING')
    raise SystemExit(2)
if not os.path.isfile(capture):
    print('ERROR=CAPTURE_MISSING')
    raise SystemExit(2)

fd,path=tempfile.mkstemp(prefix='wfgg-collector-session-',suffix='.json')
try:
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        json.dump(incoming,f,separators=(',',':'))
        f.flush(); os.fsync(f.fileno())
    incoming=None; raw=''
    try:
        cp=subprocess.run(
            [native,capture,path,'--scan-player',query],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,timeout=90,check=False,
        )
    except subprocess.TimeoutExpired:
        print('NATIVE_TIMEOUT=YES')
        raise SystemExit(0)
finally:
    try: os.unlink(path)
    except FileNotFoundError: pass

print('NATIVE_RC='+str(cp.returncode))
for line in cp.stderr.splitlines():
    if line.startswith('WFGG_SCAN_V4'):
        print(line)
try:
    d=json.loads(cp.stdout)
except Exception:
    print('NATIVE_JSON=NO')
    raise SystemExit(0)
print('NATIVE_JSON=YES')
print('NATIVE_MODE='+str(d.get('mode','')))
print('NATIVE_LOGIN='+str(d.get('loginResponse','')))
players=d.get('players')
if not isinstance(players,list):
    print('NATIVE_PLAYERS=NULL' if players is None else 'NATIVE_PLAYERS=INVALID')
    raise SystemExit(0)
print('NATIVE_PLAYERS='+str(len(players)))
if players:
    p=players[0] if isinstance(players[0],dict) else {}
    safe={k:p.get(k) for k in ('pseudo','gameUid','serverId','allianceTag','x','y','hqLevel','power') if k in p}
    print('NATIVE_FIRST_PLAYER='+json.dumps(safe,ensure_ascii=False,separators=(',',':')))
    body=json.dumps({'players':players},ensure_ascii=False,separators=(',',':')).encode()
    try:
        req=urllib.request.Request('http://127.0.0.1:8790/ingest',data=body,method='POST',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=5) as r:
            cached=json.load(r)
        print('COLLECTOR_CACHE_ACCEPTED='+str(cached.get('accepted',0)))
    except Exception:
        print('COLLECTOR_CACHE=UNAVAILABLE')
PY

TAG="$$"
REMOTE_HELPER="/tmp/wfgg-collector-native-test-$TAG.py"
scp "${SSH_OPTS[@]}" -q "$HELPER" "$REMOTE:$REMOTE_HELPER"
PAYLOAD="$(python3 - "$SESSION" "$QUERY" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    d=json.load(f)
d['_query']=sys.argv[2]
print(json.dumps(d,separators=(',',':')),end='')
PY
)"
printf '%s' "$PAYLOAD" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" python3 "$REMOTE_HELPER"
unset PAYLOAD
ssh "${SSH_OPTS[@]}" "$REMOTE" rm -f "$REMOTE_HELPER" </dev/null >/dev/null 2>&1 || true
