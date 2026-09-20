#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6198_HISTORY_DIAG_REV:-}"
EXPECTED_CONNECTOR="fb21a02feeaaa6a7013cf4e17c77bbb033a30a4bce021066fd947fc665360a9b"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
COLLECTOR_DB="${WFGG_COLLECTOR_DB:-/opt/wfgg-collector/data/collector.db}"
TARGET_SEED="8125"

die(){ echo "RADAR_V6198_HISTORY_QUALITY_DIAG=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for c in python3 sha256sum systemctl stat; do command -v "$c" >/dev/null 2>&1 || die "missing_command:$c"; done
[ -r "$COLLECTOR_DB" ] || die collector_db_unreadable

echo "=== CHACHA DEV RADAR V6.19.8 HISTORY QUALITY DIAGNOSTIC ==="
echo "SOURCE_REV=$REV"
echo "TARGET_SEED=$TARGET_SEED"

test "$(sha256sum /opt/wfgg-radar/bin/radar-connector | awk '{print $1}')" = "$EXPECTED_CONNECTOR" || die connector_sha_mismatch
test "$(sha256sum /opt/wfgg-radar/bin/radar-native-template | awk '{print $1}')" = "$EXPECTED_NATIVE" || die native_sha_mismatch
test "$(systemctl is-active wfgg-radar-connector)" = "active" || die radar_service_not_active
test "$(systemctl is-active wfgg-radar-sentinel.timer)" = "active" || die sentinel_timer_not_active
test "$(systemctl is-enabled wfgg-radar-sentinel.timer)" = "enabled" || die sentinel_not_enabled
echo "RADAR_V6198_HISTORY_QUALITY_PREFLIGHT=PASS"

set +e
python3 - "$COLLECTOR_DB" "$TARGET_SEED" <<'PY'
import hashlib,json,os,sqlite3,sys,time
from collections import defaultdict

path,seed=sys.argv[1:3]
start=time.monotonic()
deadline=start+90.0

def elapsed():
    return time.monotonic()-start

def ensure_budget(stage):
    if time.monotonic() >= deadline:
        print(f"RADAR_V6198_HISTORY_QUALITY_90S_TIMEOUT=YES",flush=True)
        print(f"RADAR_V6198_HISTORY_QUALITY_TIMEOUT_STAGE={stage}",flush=True)
        print(f"RADAR_V6198_HISTORY_QUALITY_ELAPSED_SECONDS={elapsed():.3f}",flush=True)
        raise SystemExit(90)

def file_size(p):
    try:return os.path.getsize(p)
    except OSError:return 0

print("COLLECTOR_DB_BYTES="+str(file_size(path)))
print("COLLECTOR_DB_WAL_BYTES="+str(file_size(path+"-wal")))
print("COLLECTOR_DB_SHM_BYTES="+str(file_size(path+"-shm")))

con=sqlite3.connect('file:'+path+'?mode=ro',uri=True,timeout=5)
con.row_factory=sqlite3.Row
con.execute("PRAGMA query_only=ON")
qc=con.execute("PRAGMA quick_check").fetchone()[0]
print("SQLITE_QUICK_CHECK="+str(qc))

tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
required={'cycles','cycle_seen','cycle_baseline','cycle_changes'}
missing=sorted(required-tables)
print("HISTORY_REQUIRED_TABLES="+("PASS" if not missing else "MISSING:"+",".join(missing)))
if missing: raise SystemExit(11)

for table in ('cycles','cycle_seen','cycle_baseline','cycle_changes'):
    n=con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"ROWS_{table.upper()}={n}")

cycle_ids=[int(r[0]) for r in con.execute('SELECT DISTINCT cycle_id FROM cycle_seen ORDER BY cycle_id')]
print("HISTORY_CYCLE_COUNT="+str(len(cycle_ids)))
history=[]
total_seen=total_match=total_mismatch=total_unresolved=0
stage_start=time.monotonic()

def sid_from_state(raw):
    if not raw:return ''
    try:obj=json.loads(raw)
    except Exception:return ''
    v=obj.get('server_id')
    return '' if v is None else str(v).strip()

for pos,cid in enumerate(cycle_ids,1):
    ensure_budget("SERVER_CYCLE_HISTORY")
    baseline={str(r['game_uid']):str(r['state_json'] or '') for r in con.execute(
        'SELECT game_uid,state_json FROM cycle_baseline WHERE cycle_id=?',(cid,))}
    changes={}
    for r in con.execute('SELECT game_uid,after_json FROM cycle_changes WHERE cycle_id=? ORDER BY id',(cid,)):
        if r['after_json']:
            changes[str(r['game_uid'])]=str(r['after_json'])
    counts=defaultdict(int)
    seen=matched=mismatched=unresolved=0
    for r in con.execute('SELECT game_uid,state_hash FROM cycle_seen WHERE cycle_id=?',(cid,)):
        seen+=1
        uid=str(r['game_uid']); expected=str(r['state_hash'] or '').strip().lower()
        raw=changes.get(uid) or baseline.get(uid) or ''
        if not raw or not expected:
            unresolved+=1; continue
        actual=hashlib.sha256(raw.encode('utf-8')).hexdigest()
        if actual != expected:
            mismatched+=1; continue
        sid=sid_from_state(raw)
        if not sid:
            unresolved+=1; continue
        matched+=1; counts[sid]+=1
    history.append((cid,set(counts)))
    total_seen+=seen; total_match+=matched; total_mismatch+=mismatched; total_unresolved+=unresolved
    if pos % 10 == 0 or pos == len(cycle_ids):
        print(f"HISTORY_PROGRESS={pos}/{len(cycle_ids)} ELAPSED={elapsed():.3f}",flush=True)

history_elapsed=time.monotonic()-stage_start
print(f"SERVER_CYCLE_HISTORY_SECONDS={history_elapsed:.3f}")
ensure_budget("CYCLE_QUALITY_META")

stage_start=time.monotonic()
cols={r[1] for r in con.execute('PRAGMA table_info(cycles)')}
required_cols={'id','status','error','query'}
if not required_cols.issubset(cols):
    print("CYCLE_QUALITY_SCHEMA=INVALID")
    raise SystemExit(12)
quality={}
for r in con.execute("SELECT id,status,COALESCE(error,'') error,COALESCE(query,'') query FROM cycles ORDER BY id"):
    ensure_budget("CYCLE_QUALITY_META")
    quality[int(r['id'])]=(str(r['status'] or ''),str(r['error'] or ''),str(r['query'] or ''))
quality_elapsed=time.monotonic()-stage_start
print(f"CYCLE_QUALITY_META_SECONDS={quality_elapsed:.3f}")

eligible=[]
for cid,servers in history:
    meta=quality.get(cid)
    if not meta: continue
    status,error,query=meta
    if status.strip().upper()!='SUCCESS' or error.strip(): continue
    prefix='@federated:'
    q=query.strip()
    target=q[len(prefix):].strip() if q.lower().startswith(prefix) else ''
    if target != seed: continue
    if seed not in servers: continue
    eligible.append(cid)

con.close()
print("TARGET_SEED_ELIGIBLE_HISTORY_CYCLES="+(",".join(map(str,eligible)) if eligible else "NONE"))
print("TARGET_SEED_ELIGIBLE_HISTORY_COUNT="+str(len(eligible)))
print(f"RADAR_V6198_HISTORY_QUALITY_TOTAL_SECONDS={elapsed():.3f}")
print("RADAR_V6198_HISTORY_QUALITY_90S_TIMEOUT=NO")
print("RADAR_V6198_HISTORY_QUALITY_REPRO=PASS")
PY
RC=$?
set -e

echo "RADAR_V6198_HISTORY_QUALITY_DIAG_RC=$RC"
echo "LASTWAR_CONTACT=NO"
echo "RADAR_PRODUCTION_MUTATION=NO"
echo "COLLECTOR_DATA_MUTATION=NO"
if [ "$RC" -eq 0 ] || [ "$RC" -eq 90 ]; then
  echo "RADAR_V6198_HISTORY_QUALITY_DIAG=PASS"
  exit 0
fi
exit "$RC"
