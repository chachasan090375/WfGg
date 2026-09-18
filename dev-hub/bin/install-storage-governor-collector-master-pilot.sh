#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="dev-hub-v5-storage-governor-collector-master-pilot-prep"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${BRANCH}"
BASE="/opt/chacha-dev/adapters/storage-governor"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
NAS_ROOT="/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
WORK="/tmp/chacha-storage-governor-$STAMP"

cleanup() {
  rm -rf -- "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "STORAGE_GOVERNOR_PILOT=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 ssh sha256sum systemctl install ln df; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "STORAGE_GOVERNOR_PILOT=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$RELEASE" "$EVIDENCE_DIR" "$WORK"

echo "=== STORAGE GOVERNOR COLLECTOR MASTER PILOT ==="

curl -fsSL "$RAW/dev-hub/adapters/storage-governor-adapter.py" -o "$RELEASE/storage-governor-adapter"
chmod 0755 "$RELEASE/storage-governor-adapter"
python3 -m py_compile "$RELEASE/storage-governor-adapter"
echo "STORAGE_GOVERNOR_INSTALL=STAGED"

COLLECTOR_BEFORE="$(systemctl is-active wfgg-collector || true)"
PID_BEFORE="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
echo "COLLECTOR_SERVICE_BEFORE=$COLLECTOR_BEFORE"
echo "COLLECTOR_PID_BEFORE=$PID_BEFORE"
test "$COLLECTOR_BEFORE" = "active"

FREE_BEFORE="$(df -Pk / | awk 'NR==2{print $4}')"
echo "VPS_FREE_KB_BEFORE=$FREE_BEFORE"

echo "=== COLLECTOR SQLITE DISCOVERY ==="
COLLECTOR_DB="$(
python3 - <<'PY'
from pathlib import Path
import sqlite3,sys

root=Path("/opt/wfgg-collector/data")
if not root.is_dir():
    print("COLLECTOR_DATA_DIR_MISSING",file=sys.stderr)
    raise SystemExit(20)

candidates=[]
for p in root.rglob("*"):
    if not p.is_file():
        continue
    try:
        if p.stat().st_size < 4096:
            continue
        conn=sqlite3.connect(f"file:{p}?mode=ro",uri=True,timeout=2)
        try:
            tables=int(conn.execute("select count(*) from sqlite_master where type='table'").fetchone()[0])
            if tables > 0:
                candidates.append((tables,p.stat().st_size,str(p)))
        finally:
            conn.close()
    except Exception:
        pass

candidates.sort(reverse=True)
for tables,size,path in candidates:
    print(f"CANDIDATE|tables={tables}|bytes={size}|path={path}",file=sys.stderr)

if len(candidates) != 1:
    print(f"COLLECTOR_SQLITE_CANDIDATE_COUNT={len(candidates)}",file=sys.stderr)
    raise SystemExit(21)

print(candidates[0][2])
PY
)"
export WFGG_COLLECTOR_DB="$COLLECTOR_DB"
echo "COLLECTOR_DB_DISCOVERED=$COLLECTOR_DB"

python3 - "$WORK/assess.json" <<'PY'
import json,sys
out=sys.argv[1]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"wfgg-radar",
  "transition":"collector-master-assess",
  "run_id":"storage-governor-master-pilot",
  "wave":1,
  "task":{
    "id":"collector-master-assess",
    "kind":"storage-governance",
    "description":"Assess immutable Collector MASTER readiness.",
    "owner_role":"storage-governor",
    "permission":"read",
    "outputs":[{"type":"gate","id":"collector-master-readiness"}],
    "verification":{"required":True,"mode":"machine"}
  },
  "bindings":[{
    "capability":"storage-governance",
    "provider":"storage-governor",
    "adapter":"storage-governor-adapter",
    "fallback_used":False,
    "health_state":"pilot"
  }],
  "policy_context":{
    "resource_class":"heavy",
    "requires_storage_preflight":True,
    "human_approval_required":False,
    "approval_id":None,
    "timeout_seconds":30
  },
  "workspace":"/opt/chacha-dev",
  "metadata":{"storage_governor":{"action":"assess"}}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

WFGG_COLLECTOR_DB="$COLLECTOR_DB" CHACHA_NAS_ADAPTER="/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter" CHACHA_NAS_HOST="chachanas" CHACHA_NAS_ROOT="$NAS_ROOT" "$RELEASE/storage-governor-adapter" < "$WORK/assess.json" > "$WORK/assess-result.json"

python3 - "$WORK/assess-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["schema"]=="chacha.dev/task-result/v1",x
assert x["status"]=="OK",x
assert x["summary"]=="STORAGE_GOVERNOR_ASSESS_OK",x
assert x["verification"]["status"]=="UNVERIFIED",x
print("STORAGE_GOVERNOR_ASSESS=PASS")
PY

python3 - "$WORK/master.json" <<'PY'
import json,sys
out=sys.argv[1]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"wfgg-radar",
  "transition":"collector-master-create",
  "run_id":"storage-governor-master-pilot",
  "wave":1,
  "task":{
    "id":"collector-master-create",
    "kind":"backup-store",
    "description":"Create immutable Collector MASTER on NAS.",
    "owner_role":"storage-governor",
    "permission":"workspace-write",
    "outputs":[{"type":"artifact","id":"collector-master"}],
    "verification":{"required":True,"mode":"machine"}
  },
  "bindings":[{
    "capability":"storage-governance",
    "provider":"storage-governor",
    "adapter":"storage-governor-adapter",
    "fallback_used":False,
    "health_state":"pilot"
  }],
  "policy_context":{
    "resource_class":"heavy",
    "requires_storage_preflight":True,
    "human_approval_required":False,
    "approval_id":None,
    "timeout_seconds":1800
  },
  "workspace":"/opt/chacha-dev",
  "metadata":{"storage_governor":{"action":"collector-master-snapshot"}}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

echo "STORAGE_GOVERNOR_MASTER=START"
WFGG_COLLECTOR_DB="$COLLECTOR_DB" CHACHA_NAS_ADAPTER="/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter" CHACHA_NAS_HOST="chachanas" CHACHA_NAS_ROOT="$NAS_ROOT" "$RELEASE/storage-governor-adapter" < "$WORK/master.json" > "$WORK/master-result.json"

python3 - "$WORK/master-result.json" "$WORK/master-meta.env" <<'PY'
import json,sys
src,out=sys.argv[1:3]
x=json.load(open(src))
assert x["schema"]=="chacha.dev/task-result/v1",x
assert x["status"]=="OK",x
assert x["summary"]=="COLLECTOR_MASTER_SNAPSHOT_CREATED",x
assert x["verification"]["status"]=="UNVERIFIED",x
e=x["evidence"][0]
source=e["source"]
assert source.startswith("nas://chachanas/"),source
rel=source[len("nas://chachanas/"):]
digest=e["digest"]
assert digest.startswith("sha256:"),digest
with open(out,"w",encoding="utf-8") as f:
    f.write("ARCHIVE_REL="+rel+"\n")
    f.write("ARCHIVE_SHA="+digest.split(":",1)[1]+"\n")
print("STORAGE_GOVERNOR_MASTER_CREATE=PASS")
print("COLLECTOR_MASTER_ARCHIVE="+rel)
print("COLLECTOR_MASTER_DIGEST="+digest)
PY

. "$WORK/master-meta.env"

REMOTE_SHA="$(ssh -n chachanas sha256sum "$NAS_ROOT/$ARCHIVE_REL" | awk '{print $1}')"
test -n "$REMOTE_SHA"
test "$REMOTE_SHA" = "$ARCHIVE_SHA"
echo "COLLECTOR_MASTER_INDEPENDENT_SHA256=PASS"

ssh -n chachanas gzip -t "$NAS_ROOT/$ARCHIVE_REL"
echo "COLLECTOR_MASTER_GZIP_INTEGRITY=PASS"

ssh -n chachanas gzip -dc "$NAS_ROOT/$ARCHIVE_REL" | python3 -c '
import sys
first=None
last=None
count=0
for raw in sys.stdin.buffer:
    line=raw.decode("utf-8","strict").strip()
    if not line:
        continue
    if first is None:
        first=line
    last=line
    count+=1
assert first == "BEGIN TRANSACTION;", first
assert last == "COMMIT;", last
assert count > 10, count
print("COLLECTOR_MASTER_LOGICAL_DUMP_STRUCTURE=PASS")
print("COLLECTOR_MASTER_LOGICAL_LINES="+str(count))
'

COLLECTOR_AFTER="$(systemctl is-active wfgg-collector || true)"
PID_AFTER="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
echo "COLLECTOR_SERVICE_AFTER=$COLLECTOR_AFTER"
echo "COLLECTOR_PID_AFTER=$PID_AFTER"
test "$COLLECTOR_AFTER" = "active"
test "$PID_AFTER" = "$PID_BEFORE"
echo "COLLECTOR_SERVICE_INTERRUPTION=NO"

FREE_AFTER="$(df -Pk / | awk 'NR==2{print $4}')"
echo "VPS_FREE_KB_AFTER=$FREE_AFTER"
DELTA_KB=$(( FREE_BEFORE - FREE_AFTER ))
if [ "$DELTA_KB" -lt 0 ]; then DELTA_KB=0; fi
echo "VPS_LOCAL_SNAPSHOT_DELTA_KB=$DELTA_KB"
test "$DELTA_KB" -lt 131072
echo "VPS_FULL_LOCAL_SNAPSHOT=NO"

ln -sfn "$RELEASE" "$BASE/current"

python3 - "$EVIDENCE_DIR/storage-governor-collector-master-pilot-$STAMP.json"   "$STAMP" "$ARCHIVE_REL" "$ARCHIVE_SHA" "$PID_BEFORE" "$PID_AFTER" "$DELTA_KB" "$RELEASE" <<'PY'
import json,sys
path,stamp,archive,digest,pid_before,pid_after,delta,release=sys.argv[1:9]
e={
  "schema":"chacha.dev/storage-governor-collector-master-pilot/v1",
  "observed_at":stamp,
  "status":"PASS",
  "adapter":"storage-governor-adapter",
  "runtime_path":release+"/storage-governor-adapter",
  "snapshot_kind":"MASTER",
  "archive":archive,
  "archive_sha256":"sha256:"+digest,
  "independent_sha256":"PASS",
  "collector_service_before":"active",
  "collector_service_after":"active",
  "collector_pid_before":pid_before,
  "collector_pid_after":pid_after,
  "service_interruption":False,
  "local_full_snapshot":False,
  "local_disk_delta_kb":int(delta),
  "production_data_mutation":False,
  "incremental_chain_started":False
}
open(path,"w",encoding="utf-8").write(json.dumps(e,indent=2)+"\n")
PY

echo "STORAGE_GOVERNOR_CURRENT=$BASE/current/storage-governor-adapter"
echo "STORAGE_GOVERNOR_MASTER_PILOT=PASS"
echo "COLLECTOR_PRODUCTION_DATA_MUTATION=NO"
echo "COLLECTOR_INCREMENTAL_CHAIN_STARTED=NO"
