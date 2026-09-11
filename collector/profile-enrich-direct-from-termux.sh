#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

CYCLE_ID="${1:-2}"
SEARCH_QUERY="${2:-}"
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
SESSION="${HOME}/.wfgg-lastwar-probe/home/.lastwar_goclient_session.json"

[[ "$CYCLE_ID" =~ ^[0-9]+$ ]] || { echo 'ERROR=CYCLE_ID_INVALID'; exit 2; }
[[ -s "$SESSION" ]] || { echo 'ERROR=LOCAL_SESSION_MISSING'; exit 2; }
for c in python3 ssh scp; do command -v "$c" >/dev/null 2>&1 || { echo "ERROR=${c}_MISSING"; exit 2; }; done

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" true </dev/null >/dev/null 2>&1; then
  echo 'SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" true </dev/null >/dev/null 2>&1 || { echo 'ERROR=VPS_UNREACHABLE'; exit 2; }
  echo 'SSH_ROUTE=PUBLIC_IPV4'
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
HELPER="$TMP/profile-enrich-direct.py"

cat >"$HELPER" <<'PY'
import json,os,sqlite3,subprocess,sys,tempfile,urllib.request,urllib.parse
cycle_id=int(sys.argv[1])
search_query=str(sys.argv[2] if len(sys.argv)>2 else '').strip()
raw=sys.stdin.read()
incoming=json.loads(raw)

db_path='/opt/wfgg-collector/data/collector.db'
conn=sqlite3.connect(db_path,timeout=20)
conn.row_factory=sqlite3.Row
try:
    cy=conn.execute('SELECT started_at FROM cycles WHERE id=?',(cycle_id,)).fetchone()
    if not cy:
        raise SystemExit('CYCLE_NOT_FOUND')
    rows=conn.execute('''
      SELECT p.game_uid
      FROM players p
      LEFT JOIN cycle_baseline b ON b.cycle_id=? AND b.game_uid=p.game_uid
      WHERE p.last_seen>=?
        AND (b.game_uid IS NULL OR COALESCE(p.state_hash,'')<>COALESCE(b.state_hash,''))
      ORDER BY p.game_uid
    ''',(cycle_id,cy['started_at'])).fetchall()
finally:
    conn.close()

uids=[]; seen=set()
def add_uid(uid):
    uid=str(uid or '').strip()
    if uid and uid.isdigit() and uid not in seen:
        seen.add(uid); uids.append(uid)

for row in rows:
    add_uid(row['game_uid'])

# A SEARCH cycle always refreshes the requested player's profile after the map pass,
# even when its map-visible fields did not change during this cycle.
if search_query:
    try:
        q=urllib.parse.quote(search_query,safe='')
        with urllib.request.urlopen(f'http://127.0.0.1:8790/player?q={q}',timeout=10) as r:
            player=json.load(r).get('player') or {}
        add_uid(player.get('game_uid'))
    except Exception:
        pass

print('COLLECTOR_DIRECT_CANDIDATES='+str(len(uids)))
if not uids:
    print('COLLECTOR_DIRECT_RETURNED=0')
    print('COLLECTOR_DIRECT_CACHE_ACCEPTED=0')
    print('COLLECTOR_DIRECT_FAILED_BATCHES=0')
    raise SystemExit(0)

native='/opt/wfgg-collector/bin/radar-native-template'
capture='/opt/wfgg-radar/private/lastwar-native-capture.pcap'
accepted=returned=failed_batches=0

for start in range(0,len(uids),50):
    batch=uids[start:start+50]
    fd,path=tempfile.mkstemp(prefix='wfgg-direct-session-',suffix='.json')
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(incoming,f,separators=(',',':')); f.flush(); os.fsync(f.fileno())
        cp=subprocess.run([native,capture,path,'--scan-player','@profile:'+','.join(batch)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180,check=False)
    finally:
        try: os.unlink(path)
        except FileNotFoundError: pass
    if cp.returncode != 0:
        failed_batches += 1
        print('COLLECTOR_DIRECT_BATCH_RC='+str(cp.returncode))
        continue
    try:
        data=json.loads(cp.stdout)
        players=data.get('players')
        if not isinstance(players,list): players=[]
    except Exception:
        players=[]
    returned += len(players)
    if players:
        body=json.dumps({'players':players,'cycleId':cycle_id},ensure_ascii=False,separators=(',',':')).encode()
        req=urllib.request.Request('http://127.0.0.1:8790/ingest',data=body,method='POST',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as r:
            out=json.load(r)
        accepted += int(out.get('accepted',0))

print('COLLECTOR_DIRECT_RETURNED='+str(returned))
print('COLLECTOR_DIRECT_CACHE_ACCEPTED='+str(accepted))
print('COLLECTOR_DIRECT_FAILED_BATCHES='+str(failed_batches))
PY

TAG="$$"
REMOTE_HELPER="/tmp/wfgg-profile-enrich-direct-$TAG.py"
scp "${SSH_OPTS[@]}" -q "$HELPER" "$REMOTE:$REMOTE_HELPER"
PAYLOAD="$(python3 - "$SESSION" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f: d=json.load(f)
print(json.dumps(d,separators=(',',':')),end='')
PY
)"
printf '%s' "$PAYLOAD" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" python3 "$REMOTE_HELPER" "$CYCLE_ID" "$SEARCH_QUERY"
unset PAYLOAD
ssh "${SSH_OPTS[@]}" -T "$REMOTE" rm -f "$REMOTE_HELPER" </dev/null >/dev/null 2>&1 || true
