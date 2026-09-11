#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Diagnose the READONLY player scan directly on ChaChaVPS, bypassing Tailscale
# Funnel and Cloudflare. The Last War token is read locally and streamed over
# SSH stdin only; it is never written to disk or echoed.

QUERY="${1:-Zazavibes}"
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SESSION="${HOME}/.wfgg-lastwar-probe/home/.lastwar_goclient_session.json"

[[ -s "$SESSION" ]] || { echo 'ERROR=LOCAL_SESSION_MISSING'; exit 2; }
[[ -n "${QUERY//[[:space:]]/}" ]] || { echo 'ERROR=QUERY_EMPTY'; exit 2; }
for cmd in python3 ssh scp; do command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR=${cmd}_MISSING"; exit 2; }; done

TOKEN="$(python3 - "$SESSION" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    t=str(json.load(f).get('accessToken','')).strip()
if len(t)<8:
    raise SystemExit(2)
print(t,end='')
PY
)" || { echo 'ERROR=LOCAL_TOKEN_MISSING'; exit 2; }

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
HELPER="$TMP/direct-player-scan.py"
cat > "$HELPER" <<'PY'
import hashlib,hmac,json,secrets,time,urllib.request,urllib.error,sys

raw=sys.stdin.read()
try:
    incoming=json.loads(raw)
except Exception:
    print("ERROR=INPUT_PARSE_FAILED")
    raise SystemExit(2)
query=str(incoming.get("query","")).strip()
token=str(incoming.get("token","")).strip()
incoming=None; raw=""
if not query or len(token)<8:
    print("ERROR=INPUT_INVALID")
    raise SystemExit(2)

env={}
with open("/opt/wfgg-radar/radar.env",encoding="utf-8") as f:
    for line in f:
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k,v=line.split("=",1)
        v=v.strip()
        if len(v)>=2 and v[0]==v[-1] and v[0] in "\"'":
            v=v[1:-1]
        env[k.strip()]=v
secret=env.get("RADAR_CONNECTOR_SHARED_KEY","")
if len(secret)<32:
    print("ERROR=SHARED_KEY_MISSING")
    raise SystemExit(2)

path="/v1/scan/player"
body=json.dumps({"token":token,"query":query},separators=(",",":")).encode()
token=""
ts=str(int(time.time()))
nonce=secrets.token_hex(16)
body_hash=hashlib.sha256(body).hexdigest()
canonical="\n".join(["POST",path,ts,nonce,body_hash])
sig=hmac.new(secret.encode(),canonical.encode(),hashlib.sha256).hexdigest()
secret=""
req=urllib.request.Request("http://127.0.0.1:8788"+path,data=body,method="POST",headers={
    "Content-Type":"application/json",
    "X-Radar-Timestamp":ts,
    "X-Radar-Nonce":nonce,
    "X-Radar-Signature":sig,
})
start=time.monotonic()
try:
    with urllib.request.urlopen(req,timeout=75) as r:
        out=r.read().decode("utf-8","replace")
        status=r.status
except urllib.error.HTTPError as e:
    status=e.code
    out=e.read().decode("utf-8","replace")
except Exception as e:
    print("DIRECT_EXCEPTION="+type(e).__name__)
    print("DIRECT_SECONDS=%.2f"%(time.monotonic()-start))
    raise SystemExit(0)
print("DIRECT_HTTP="+str(status))
print("DIRECT_SECONDS=%.2f"%(time.monotonic()-start))
try:
    d=json.loads(out)
    if isinstance(d,dict):
        if "error" in d:
            print("DIRECT_ERROR="+str(d.get("error")))
        players=d.get("players")
        if isinstance(players,list):
            print("DIRECT_PLAYERS="+str(len(players)))
    else:
        print("DIRECT_JSON=NON_OBJECT")
except Exception:
    print("DIRECT_BODY_NONJSON=YES")
PY

TAG="$$"
REMOTE_HELPER="/tmp/wfgg-radar-direct-scan-$TAG.py"
scp "${SSH_OPTS[@]}" -q "$HELPER" "$REMOTE:$REMOTE_HELPER"

PAYLOAD="$(python3 - "$QUERY" "$TOKEN" <<'PY'
import json,sys
print(json.dumps({'query':sys.argv[1],'token':sys.argv[2]},separators=(',',':')),end='')
PY
)"
unset TOKEN

set +e
printf '%s' "$PAYLOAD" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" python3 "$REMOTE_HELPER"
RC=$?
set -e
unset PAYLOAD
ssh "${SSH_OPTS[@]}" "$REMOTE" rm -f "$REMOTE_HELPER" </dev/null >/dev/null 2>&1 || true
exit "$RC"
