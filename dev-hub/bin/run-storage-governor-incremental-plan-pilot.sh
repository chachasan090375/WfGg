#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_REVISION="a51bed6da147a99450d9795cb3129436abbcd634"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${SOURCE_REVISION}"
BASE="/opt/chacha-dev/adapters/storage-governor"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
WORK="/tmp/chacha-storage-incremental-plan-$STAMP"

cleanup() {
  rm -rf -- "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "STORAGE_INCREMENTAL_PLAN=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 systemctl ln; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "STORAGE_INCREMENTAL_PLAN=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$RELEASE" "$EVIDENCE_DIR" "$WORK"

curl -fsSL "$RAW/dev-hub/adapters/storage-governor-adapter.py" -o "$RELEASE/storage-governor-adapter"
chmod 0755 "$RELEASE/storage-governor-adapter"
python3 -m py_compile "$RELEASE/storage-governor-adapter"
echo "STORAGE_INCREMENTAL_PLAN_INSTALL=STAGED"

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

def valid(path):
    try:
        p=Path(path).resolve()
        if not p.is_file() or p.stat().st_size < 4096:
            return None
        conn=sqlite3.connect(f"file:{p}?mode=ro",uri=True,timeout=2)
        try:
            tables=int(conn.execute("select count(*) from sqlite_master where type='table'").fetchone()[0])
            return str(p) if tables>0 else None
        finally:
            conn.close()
    except Exception:
        return None

opened=[]
fdroot=Path("/proc")/pid/"fd"
if pid.isdigit() and fdroot.is_dir():
    for fd in fdroot.iterdir():
        try:
            target=Path(os.readlink(fd))
            if target.is_absolute():
                resolved=target.resolve()
                if str(resolved).startswith(str(root.resolve())+"/"):
                    v=valid(resolved)
                    if v and v not in opened:
                        opened.append(v)
        except Exception:
            pass
if len(opened)==1:
    print(opened[0]); raise SystemExit(0)

fallback=[]
for p in root.iterdir():
    if p.is_file():
        v=valid(p)
        if v: fallback.append(v)
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
  "transition":"collector-incremental-plan",
  "run_id":"storage-governor-incremental-plan",
  "wave":1,
  "task":{
    "id":"collector-incremental-plan",
    "kind":"storage-governance",
    "description":"Build deterministic Collector incremental backup plan.",
    "owner_role":"storage-governor",
    "permission":"read",
    "outputs":[{"type":"report","id":"collector-incremental-plan"}],
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
    "timeout_seconds":120
  },
  "workspace":"/opt/chacha-dev",
  "metadata":{"storage_governor":{"action":"collector-incremental-plan"}}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

WFGG_COLLECTOR_DB="$COLLECTOR_DB" "$RELEASE/storage-governor-adapter"   < "$WORK/request.json"   > "$WORK/result.json"

python3 - "$WORK/result.json" "$EVIDENCE_DIR/storage-governor-incremental-plan-$STAMP.json" <<'PY'
import json,sys
src,evidence_path=sys.argv[1:3]
x=json.load(open(src))
assert x["schema"]=="chacha.dev/task-result/v1",x
assert x["status"] in {"OK","BLOCKED"},x
assert x["verification"]["status"]=="UNVERIFIED",x
details=x["evidence"][0]["details"]
assert details["raw_row_data_exposed"] is False,details

print("STORAGE_INCREMENTAL_PLAN_STATUS="+x["status"])
print("STORAGE_INCREMENTAL_PLAN_SUMMARY="+x["summary"])
print("COLLECTOR_SCHEMA_TABLES="+str(details["table_count"]))
print("COLLECTOR_PLAN_BLOCKED_TABLES="+str(len(details["blocked_tables"])))

for p in details["plans"]:
    maxs=",".join(k+"="+str(v) for k,v in sorted(p.get("current_max",{}).items()))
    pks=",".join(p.get("pk") or [])
    marks=",".join(p.get("watermark_columns") or [])
    print(
        "INCREMENTAL_PLAN|table="+p["table"]+
        "|rows="+str(p["row_count"])+
        "|mode="+p["mode"]+
        "|pk="+pks+
        "|watermark="+marks+
        ("|max="+maxs if maxs else "")
    )

ev={
  "schema":"chacha.dev/storage-governor-incremental-plan-evidence/v1",
  "status":x["status"],
  "summary":x["summary"],
  "observed_at":x["observed_at"],
  "raw_row_data_exposed":False,
  "table_count":details["table_count"],
  "blocked_tables":details["blocked_tables"],
  "plans":details["plans"],
  "source_digest":x["evidence"][0]["digest"],
  "production_data_mutation":False
}
open(evidence_path,"w",encoding="utf-8").write(json.dumps(ev,indent=2)+"\n")

if x["status"]!="OK":
    raise SystemExit(3)
PY

ln -sfn "$RELEASE" "$BASE/current"

echo "STORAGE_INCREMENTAL_PLAN=PASS"
echo "STORAGE_INCREMENTAL_PLAN_RAW_DATA_EXPOSED=NO"
echo "STORAGE_INCREMENTAL_PLAN_PRODUCTION_MUTATION=NO"
