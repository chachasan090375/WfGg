#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REGION="${1:-0}"
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SESSION="${HOME}/.wfgg-lastwar-probe/home/.lastwar_goclient_session.json"

[[ "$REGION" =~ ^[0-8]$ ]] || { echo 'ERROR=REGION_MUST_BE_0_TO_8'; exit 2; }
[[ -s "$SESSION" ]] || { echo 'ERROR=LOCAL_SESSION_MISSING'; exit 2; }
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
HELPER="$TMP/collector-region-test.py"
cat > "$HELPER" <<'PY'
import json,os,subprocess,sys,tempfile,urllib.request

region=sys.argv[1]
raw=sys.stdin.read()
try:
    incoming=json.loads(raw)
except Exception:
    print('ERROR=INPUT_PARSE_FAILED')
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
    env=os.environ.copy()
    env['WFGG_COLLECTOR_ORIGIN_INDEX']=region
    try:
        cp=subprocess.run(
            [native,capture,path,'--scan-player','*'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,timeout=45,check=False,env=env,
        )
    except subprocess.TimeoutExpired:
        print('NATIVE_TIMEOUT=YES')
        raise SystemExit(0)
finally:
    try: os.unlink(path)
    except FileNotFoundError: pass

print('COLLECTOR_REGION='+region)
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
print('NATIVE_LOGIN='+str(d.get('loginResponse','')))
players=d.get('players')
if not isinstance(players,list):
    print('NATIVE_PLAYERS=NULL' if players is None else 'NATIVE_PLAYERS=INVALID')
    raise SystemExit(0)
print('NATIVE_PLAYERS='+str(len(players)))

accepted=0
changed=0
for i in range(0,len(players),250):
    body=json.dumps({'players':players[i:i+250]},ensure_ascii=False,separators=(',',':')).encode()
    req=urllib.request.Request('http://127.0.0.1:8790/ingest',data=body,method='POST',headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as r:
        out=json.load(r)
    accepted += int(out.get('accepted',0))
    changed += int(out.get('changed',0))
print('COLLECTOR_CACHE_ACCEPTED='+str(accepted))
print('COLLECTOR_CACHE_CHANGED='+str(changed))
with urllib.request.urlopen('http://127.0.0.1:8790/stats',timeout=5) as r:
    st=json.load(r)
print('COLLECTOR_TOTAL_PLAYERS='+str(st.get('players',0)))
PY

TAG="$$"
REMOTE_HELPER="/tmp/wfgg-collector-region-test-$TAG.py"
scp "${SSH_OPTS[@]}" -q "$HELPER" "$REMOTE:$REMOTE_HELPER"
PAYLOAD="$(python3 - "$SESSION" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    d=json.load(f)
print(json.dumps(d,separators=(',',':')),end='')
PY
)"
printf '%s' "$PAYLOAD" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" python3 "$REMOTE_HELPER" "$REGION"
unset PAYLOAD
ssh "${SSH_OPTS[@]}" "$REMOTE" rm -f "$REMOTE_HELPER" </dev/null >/dev/null 2>&1 || true
