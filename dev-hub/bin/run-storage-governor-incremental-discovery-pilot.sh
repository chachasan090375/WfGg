#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="dev-hub-v5-storage-governor-incremental-discovery"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${BRANCH}"
BASE="/opt/chacha-dev/adapters/storage-governor"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
WORK="/tmp/chacha-storage-incremental-discovery-$STAMP"

cleanup() {
  rm -rf -- "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "STORAGE_INCREMENTAL_DISCOVERY=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 systemctl install ln; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "STORAGE_INCREMENTAL_DISCOVERY=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$RELEASE" "$EVIDENCE_DIR" "$WORK"

curl -fsSL "$RAW/dev-hub/adapters/storage-governor-adapter.py" -o "$RELEASE/storage-governor-adapter"
chmod 0755 "$RELEASE/storage-governor-adapter"
python3 -m py_compile "$RELEASE/storage-governor-adapter"
echo "STORAGE_INCREMENTAL_DISCOVERY_INSTALL=STAGED"

STATE="$(systemctl is-active wfgg-collector || true)"
PID="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
echo "COLLECTOR_SERVICE=$STATE"
echo "COLLECTOR_PID=$PID"
test "$STATE" = "active"

COLLECTOR_DB="$(
python3 - "$PID" <<'PY'
from pathlib import Path
import os,sqlite3,sys

pid=sys.argv[1].strip()
root=Path("/opt/wfgg-collector/data")
if not root.is_dir():
    raise SystemExit("COLLECTOR_DATA_DIR_MISSING")

def sqlite_info(path):
    try:
        p=Path(path).resolve()
        if not p.is_file() or p.stat().st_size < 4096:
            return None
        conn=sqlite3.connect(f"file:{p}?mode=ro",uri=True,timeout=2)
        try:
            tables=int(conn.execute("select count(*) from sqlite_master where type='table'").fetchone()[0])
            return str(p) if tables > 0 else None
        finally:
            conn.close()
    except Exception:
        return None

opened=[]
fd_root=Path("/proc")/pid/"fd"
if pid.isdigit() and fd_root.is_dir():
    for fd in fd_root.iterdir():
        try:
            target=Path(os.readlink(fd))
            if not target.is_absolute():
                continue
            resolved=target.resolve()
            if str(resolved).startswith(str(root.resolve())+"/"):
                info=sqlite_info(resolved)
                if info and info not in opened:
                    opened.append(info)
        except Exception:
            pass

if len(opened)==1:
    print(opened[0])
    raise SystemExit(0)

fallback=[]
for p in root.iterdir():
    if p.is_file():
        info=sqlite_info(p)
        if info:
            fallback.append(info)
if len(fallback)!=1:
    print(f"COLLECTOR_ACTIVE_DB_AMBIGUOUS open={len(opened)} top={len(fallback)}",file=sys.stderr)
    raise SystemExit(21)
print(fallback[0])
PY
)"
export WFGG_COLLECTOR_DB="$COLLECTOR_DB"
echo "COLLECTOR_DB_DISCOVERED=$COLLECTOR_DB"

python3 - "$WORK/request.json" <<'PY'
import json,sys
out=sys.argv[1]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"wfgg-radar",
  "transition":"collector-incremental-discovery",
  "run_id":"storage-governor-incremental-discovery",
  "wave":1,
  "task":{
    "id":"collector-incremental-discovery",
    "kind":"storage-governance",
    "description":"Discover safe Collector incremental watermark candidates.",
    "owner_role":"storage-governor",
    "permission":"read",
    "outputs":[{"type":"report","id":"collector-incremental-schema"}],
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
    "resource_class":"light",
    "requires_storage_preflight":False,
    "human_approval_required":False,
    "approval_id":None,
    "timeout_seconds":60
  },
  "workspace":"/opt/chacha-dev",
  "metadata":{"storage_governor":{"action":"collector-incremental-discovery"}}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

WFGG_COLLECTOR_DB="$COLLECTOR_DB" "$RELEASE/storage-governor-adapter"   < "$WORK/request.json"   > "$WORK/result.json"

python3 - "$WORK/result.json" "$EVIDENCE_DIR/storage-governor-incremental-discovery-$STAMP.json" <<'PY'
import json,sys
src,evidence_path=sys.argv[1:3]
x=json.load(open(src))
assert x["schema"]=="chacha.dev/task-result/v1",x
assert x["status"]=="OK",x
assert x["summary"]=="COLLECTOR_INCREMENTAL_DISCOVERY_OK",x
assert x["verification"]["status"]=="UNVERIFIED",x
details=x["evidence"][0]["details"]
assert details["raw_row_data_exposed"] is False,details
print("STORAGE_INCREMENTAL_DISCOVERY=PASS")
print("COLLECTOR_SCHEMA_TABLES="+str(details["table_count"]))
print("COLLECTOR_INCREMENTAL_CANDIDATE_TABLES="+str(details["candidate_table_count"]))
for item in details["candidate_tables"]:
    table=item["table"]
    candidates=[]
    for c in item["watermark_candidates"]:
        label=c["column"]+":"+c["kind"]
        agg=c.get("aggregate") or {}
        if "max" in agg:
            label+=":max="+str(agg["max"])
        candidates.append(label)
    print("INCREMENTAL_CANDIDATE|table="+table+"|"+",".join(candidates))
ev={
  "schema":"chacha.dev/storage-governor-incremental-discovery-evidence/v1",
  "status":"PASS",
  "summary":x["summary"],
  "observed_at":x["observed_at"],
  "raw_row_data_exposed":False,
  "table_count":details["table_count"],
  "candidate_table_count":details["candidate_table_count"],
  "candidate_tables":details["candidate_tables"],
  "source_digest":x["evidence"][0]["digest"],
  "production_data_mutation":False
}
open(evidence_path,"w",encoding="utf-8").write(json.dumps(ev,indent=2)+"\n")
PY

ln -sfn "$RELEASE" "$BASE/current"

echo "STORAGE_GOVERNOR_CURRENT=$BASE/current/storage-governor-adapter"
echo "STORAGE_INCREMENTAL_DISCOVERY_RAW_DATA_EXPOSED=NO"
echo "STORAGE_INCREMENTAL_DISCOVERY_PRODUCTION_MUTATION=NO"
