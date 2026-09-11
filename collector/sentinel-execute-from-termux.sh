#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SESSION="${HOME}/.wfgg-lastwar-probe/home/.lastwar_goclient_session.json"
REQUEST="/opt/wfgg-collector/data/sentinel-enrichment-request.env"
RESULT="/opt/wfgg-collector/data/sentinel-enrichment-result.env"

[[ -s "$SESSION" ]] || { echo 'ERROR=LOCAL_SESSION_MISSING'; exit 2; }
for c in python3 ssh scp; do command -v "$c" >/dev/null 2>&1 || { echo "ERROR=${c}_MISSING"; exit 2; }; done

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

REQ_RAW="$(ssh "${SSH_OPTS[@]}" -T "$REMOTE" "test -s '$REQUEST' && cat '$REQUEST' || true")"
if [[ -z "$REQ_RAW" ]]; then
  echo 'SENTINEL_EXECUTOR=IDLE'
  exit 0
fi

readarray -t REQ < <(python3 - <<'PY' <<<"$REQ_RAW"
import sys
vals={}
for line in sys.stdin.read().splitlines():
    if '=' in line:
        k,v=line.split('=',1); vals[k.strip()]=v.strip()
print(vals.get('SENTINEL_REQUEST_TYPE',''))
print(vals.get('SENTINEL_REQUEST_SAMPLE',''))
print(vals.get('SENTINEL_REQUEST_UID',''))
PY
)
TYPE="${REQ[0]:-}"
SAMPLE="${REQ[1]:-}"
GAME_UID="${REQ[2]:-}"
[[ "$TYPE" == "ENRICH_PROFILE" ]] || { echo "SENTINEL_EXECUTOR=UNSUPPORTED:$TYPE"; exit 2; }
QUERY="$GAME_UID"
[[ -n "$QUERY" ]] || QUERY="$SAMPLE"
[[ -n "$QUERY" ]] || { echo 'ERROR=SENTINEL_REQUEST_INVALID'; exit 2; }

echo 'SENTINEL_EXECUTOR=RUNNING'
echo "SENTINEL_ACTION=$TYPE"
echo "SENTINEL_SAMPLE=$SAMPLE"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
HELPER="$TMP/sentinel-enrichment-helper.py"
cat >"$HELPER" <<'PY'
import json,os,re,subprocess,sys,tempfile,urllib.request
raw=sys.stdin.read()
try:
    incoming=json.loads(raw)
except Exception:
    print('ERROR=INPUT_PARSE_FAILED')
    raise SystemExit(2)
query=str(incoming.pop('_query','')).strip()
sample=str(incoming.pop('_sample','')).strip()
uid=str(incoming.pop('_uid','')).strip()
if not query:
    print('ERROR=QUERY_EMPTY')
    raise SystemExit(2)
native='/opt/wfgg-collector/bin/radar-native-template'
capture='/opt/wfgg-radar/private/lastwar-native-capture.pcap'
result='/opt/wfgg-collector/data/sentinel-enrichment-result.env'
if not (os.path.isfile(native) and os.access(native,os.X_OK)):
    print('ERROR=COLLECTOR_NATIVE_MISSING')
    raise SystemExit(2)
if not os.path.isfile(capture):
    print('ERROR=CAPTURE_MISSING')
    raise SystemExit(2)
fd,path=tempfile.mkstemp(prefix='wfgg-sentinel-session-',suffix='.json')
try:
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        json.dump(incoming,f,separators=(',',':')); f.flush(); os.fsync(f.fileno())
    incoming=None; raw=''
    try:
        cp=subprocess.run([native,capture,path,'--scan-player',query],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90,check=False)
    except subprocess.TimeoutExpired:
        cp=None
finally:
    try: os.unlink(path)
    except FileNotFoundError: pass

panic='NO'; funcs=[]; codes=[]; players=[]; cache_accepted=0
rc=124 if cp is None else cp.returncode
if cp is not None:
    lines=cp.stderr.splitlines()
    panic='YES' if any(x.startswith('panic:') for x in lines) else 'NO'
    if panic=='YES':
        for line in lines:
            s=line.strip()
            m=re.match(r'^(?:lastwar-client/)?(?:cmd/wfgg-collector-native/)?([A-Za-z0-9_./-]+)\(',s)
            if m:
                name=m.group(1).split('/')[-1]
                if name and name not in funcs: funcs.append(name)
            if len(funcs)>=8: break
    for src in (cp.stderr,cp.stdout):
        for code in re.findall(r'\b(?:LASTWAR_)?PLAYER_[A-Z0-9_]+\b',src):
            if code not in codes: codes.append(code)
    for line in lines:
        if line.startswith('WFGG_SCAN_V4'):
            print(line)
    try:
        d=json.loads(cp.stdout)
        p=d.get('players')
        if isinstance(p,list): players=p
    except Exception:
        pass

if players:
    try:
        body=json.dumps({'players':players},ensure_ascii=False,separators=(',',':')).encode()
        req=urllib.request.Request('http://127.0.0.1:8790/ingest',data=body,method='POST',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:
            cached=json.load(r)
        cache_accepted=int(cached.get('accepted',0))
    except Exception:
        cache_accepted=0
status='SUCCESS' if rc==0 and len(players)>0 else 'FAILED'
from datetime import datetime,timezone
stamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def safe(v):
    return ''.join(ch for ch in str(v) if ch.isalnum() or ch in '._,-')[:300]
with open(result,'w',encoding='utf-8') as f:
    f.write('SENTINEL_ENRICHMENT_STATUS='+status+'\n')
    f.write('SENTINEL_ENRICHMENT_AT='+stamp+'\n')
    f.write('SENTINEL_ENRICHMENT_SAMPLE='+safe(sample)+'\n')
    f.write('SENTINEL_ENRICHMENT_UID='+safe(uid)+'\n')
    f.write('SENTINEL_ENRICHMENT_RC='+str(rc)+'\n')
    f.write('SENTINEL_ENRICHMENT_PANIC='+panic+'\n')
    f.write('SENTINEL_ENRICHMENT_PANIC_FUNCS='+safe(','.join(funcs) if funcs else 'NONE')+'\n')
    f.write('SENTINEL_ENRICHMENT_ERROR_CODES='+safe(','.join(codes) if codes else 'NONE')+'\n')
    f.write('SENTINEL_ENRICHMENT_PLAYERS='+str(len(players))+'\n')
    f.write('SENTINEL_ENRICHMENT_CACHE_ACCEPTED='+str(cache_accepted)+'\n')
os.chmod(result,0o640)
print('SENTINEL_ENRICHMENT_STATUS='+status)
print('SENTINEL_ENRICHMENT_RC='+str(rc))
print('SENTINEL_ENRICHMENT_PANIC='+panic)
print('SENTINEL_ENRICHMENT_PANIC_FUNCS='+(','.join(funcs) if funcs else 'NONE'))
print('SENTINEL_ENRICHMENT_ERROR_CODES='+(','.join(codes) if codes else 'NONE'))
print('SENTINEL_ENRICHMENT_PLAYERS='+str(len(players)))
print('SENTINEL_ENRICHMENT_CACHE_ACCEPTED='+str(cache_accepted))
PY

TAG="$$"
REMOTE_HELPER="/tmp/wfgg-sentinel-enrichment-$TAG.py"
scp "${SSH_OPTS[@]}" -q "$HELPER" "$REMOTE:$REMOTE_HELPER"
PAYLOAD="$(python3 - "$SESSION" "$QUERY" "$SAMPLE" "$GAME_UID" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f: d=json.load(f)
d['_query']=sys.argv[2]; d['_sample']=sys.argv[3]; d['_uid']=sys.argv[4]
print(json.dumps(d,separators=(',',':')),end='')
PY
)"
printf '%s' "$PAYLOAD" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" python3 "$REMOTE_HELPER"
unset PAYLOAD
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "rm -f '$REMOTE_HELPER'; systemctl start wfgg-collector-sentinel.service; sleep 1; echo '=== SENTINEL STATE ==='; cat /opt/wfgg-collector/data/sentinel-collector-state.env; echo '=== SENTINEL ENRICHMENT RESULT ==='; cat '$RESULT'" </dev/null
