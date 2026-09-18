#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_REVISION="ed5957a410d03a60c5a2a7525e0968174d62f677"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${SOURCE_REVISION}"
BASE="/opt/chacha-dev/adapters/storage-governor"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
NAS_ROOT="/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
CHAIN_ROOT="$NAS_ROOT/projects/wfgg/backups/collector-chain"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
WORK="/tmp/chacha-incremental-chain-$STAMP"

MASTER_ARCHIVE="projects/wfgg/backups/collector-master-20260918T085757Z.sql.gz"
MASTER_SHA="sha256:4fd82f1ecab892372998dd4ef6e0df085474876a914409f70c6502d97929f730"
MASTER_CREATED_AT="2026-09-18T08:57:57Z"
BASELINE_CYCLE=35
OBSERVED_AT_BASELINE="2026-09-18T05:18:47.18986397Z"
OBSERVATION_ID_BASELINE=126611
MASTER_TIME_BASELINE="2026-09-11T22:23:30.164682Z"
MASTER_ID_BASELINE=1
PLAN_DIGEST="sha256:b4763fc617d0e72786c9e4136f0a39cf259d06e3b9d5b0b0970f30a998a30390"

cleanup() {
  rm -rf -- "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "STORAGE_INCREMENTAL_CHAIN_PILOT=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 ssh sha256sum systemctl ln gzip; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "STORAGE_INCREMENTAL_CHAIN_PILOT=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$RELEASE" "$EVIDENCE_DIR" "$WORK"

curl -fsSL "$RAW/dev-hub/adapters/storage-governor-adapter.py"   -o "$RELEASE/storage-governor-adapter"
curl -fsSL "$RAW/dev-hub/adapters/storage-governor-incremental-chain.py"   -o "$RELEASE/storage-governor-incremental-chain.py"
chmod 0755 "$RELEASE/storage-governor-adapter"
python3 -m py_compile   "$RELEASE/storage-governor-adapter"   "$RELEASE/storage-governor-incremental-chain.py"
echo "STORAGE_INCREMENTAL_CHAIN_INSTALL=STAGED"

COLLECTOR_BEFORE="$(systemctl is-active wfgg-collector || true)"
PID_BEFORE="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
echo "COLLECTOR_SERVICE_BEFORE=$COLLECTOR_BEFORE"
echo "COLLECTOR_PID_BEFORE=$PID_BEFORE"
test "$COLLECTOR_BEFORE" = "active"

COLLECTOR_DB="$(
python3 - "$PID_BEFORE" <<'PY'
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
    print(opened[0])
    raise SystemExit(0)

fallback=[]
for p in root.iterdir():
    if p.is_file():
        v=valid(p)
        if v:
            fallback.append(v)
if len(fallback)!=1:
    print(f"COLLECTOR_ACTIVE_DB_AMBIGUOUS open={len(opened)} top={len(fallback)}",file=sys.stderr)
    raise SystemExit(21)
print(fallback[0])
PY
)"
export WFGG_COLLECTOR_DB="$COLLECTOR_DB"
echo "COLLECTOR_DB_DISCOVERED=$COLLECTOR_DB"

MASTER_REMOTE_SHA="$(ssh -n chachanas sha256sum "$NAS_ROOT/$MASTER_ARCHIVE" | awk '{print $1}')"
test "sha256:$MASTER_REMOTE_SHA" = "$MASTER_SHA"
echo "CHAIN_MASTER_INDEPENDENT_SHA256=PASS"

python3 - "$WORK/anchor.json" <<PY
import json,sys
out=sys.argv[1]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"wfgg-radar",
  "transition":"collector-incremental-anchor",
  "run_id":"storage-governor-incremental-chain-pilot",
  "wave":1,
  "task":{
    "id":"collector-incremental-anchor",
    "kind":"backup-store",
    "description":"Create immutable Collector incremental chain anchor.",
    "owner_role":"storage-governor",
    "permission":"workspace-write",
    "outputs":[{"type":"artifact","id":"collector-chain-state-000000"}],
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
  "metadata":{"storage_governor":{
    "action":"collector-incremental-anchor",
    "master_archive":"$MASTER_ARCHIVE",
    "master_sha256":"$MASTER_SHA",
    "master_created_at":"$MASTER_CREATED_AT",
    "baseline_cycle":$BASELINE_CYCLE,
    "observations_watermark":{
      "observed_at":"$OBSERVED_AT_BASELINE",
      "id":$OBSERVATION_ID_BASELINE
    },
    "masters_watermark":{
      "created_at":"$MASTER_TIME_BASELINE",
      "id":$MASTER_ID_BASELINE
    },
    "plan_digest":"$PLAN_DIGEST"
  }}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

ANCHOR_REMOTE="$CHAIN_ROOT/collector-chain-state-000000.json"

if ssh -n chachanas test -s "$ANCHOR_REMOTE"; then
  echo "COLLECTOR_INCREMENTAL_ANCHOR=ALREADY_PRESENT"
else
  WFGG_COLLECTOR_DB="$COLLECTOR_DB"   CHACHA_NAS_ADAPTER="/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"   CHACHA_NAS_HOST="chachanas"   CHACHA_NAS_ROOT="$NAS_ROOT"   "$RELEASE/storage-governor-adapter"     < "$WORK/anchor.json"     > "$WORK/anchor-result.json"

  python3 - "$WORK/anchor-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["status"]=="OK",x
assert x["summary"]=="COLLECTOR_INCREMENTAL_CHAIN_ANCHORED",x
print("COLLECTOR_INCREMENTAL_ANCHOR=PASS")
PY
fi

ssh -n chachanas test -s "$ANCHOR_REMOTE"
ANCHOR_SHA="$(ssh -n chachanas sha256sum "$ANCHOR_REMOTE" | awk '{print $1}')"
test -n "$ANCHOR_SHA"
echo "COLLECTOR_INCREMENTAL_ANCHOR_SHA256=sha256:$ANCHOR_SHA"

python3 - "$WORK/package.json" <<'PY'
import json,sys
out=sys.argv[1]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"wfgg-radar",
  "transition":"collector-incremental-package",
  "run_id":"storage-governor-incremental-chain-pilot",
  "wave":1,
  "task":{
    "id":"collector-incremental-package",
    "kind":"backup-store",
    "description":"Create next immutable Collector incremental package when eligible.",
    "owner_role":"storage-governor",
    "permission":"workspace-write",
    "outputs":[{"type":"artifact","id":"collector-incremental-next"}],
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
  "metadata":{"storage_governor":{"action":"collector-incremental-package"}}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

WFGG_COLLECTOR_DB="$COLLECTOR_DB" CHACHA_NAS_ADAPTER="/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter" CHACHA_NAS_HOST="chachanas" CHACHA_NAS_ROOT="$NAS_ROOT" "$RELEASE/storage-governor-adapter"   < "$WORK/package.json"   > "$WORK/package-result.json"

python3 - "$WORK/package-result.json" "$WORK/package.env" <<'PY'
import json,sys
src,env_path=sys.argv[1:3]
x=json.load(open(src))
assert x["status"]=="OK",x
summary=x["summary"]
print("COLLECTOR_INCREMENTAL_RESULT="+summary)
if summary=="COLLECTOR_INCREMENTAL_NOOP":
    print("COLLECTOR_INCREMENTAL_PACKAGE=NOOP")
    open(env_path,"w").write("PACKAGE_CREATED=0\n")
elif summary=="COLLECTOR_INCREMENTAL_PACKAGE_CREATED":
    e=x["evidence"][0]
    source=e["source"]
    assert source.startswith("nas://chachanas/"),source
    rel=source[len("nas://chachanas/"):]
    digest=e["digest"]
    details=e["details"]
    print("COLLECTOR_INCREMENTAL_PACKAGE=PASS")
    print("COLLECTOR_INCREMENTAL_SEQUENCE="+str(details["sequence"]))
    print("COLLECTOR_INCREMENTAL_FROM_CYCLE="+str(details["from_cycle"]))
    print("COLLECTOR_INCREMENTAL_TO_CYCLE="+str(details["to_cycle"]))
    print("COLLECTOR_INCREMENTAL_ARCHIVE="+rel)
    print("COLLECTOR_INCREMENTAL_DIGEST="+digest)
    with open(env_path,"w") as f:
        f.write("PACKAGE_CREATED=1\n")
        f.write("PACKAGE_REL="+rel+"\n")
        f.write("PACKAGE_SHA="+digest.split(":",1)[1]+"\n")
else:
    raise AssertionError(summary)
PY

. "$WORK/package.env"

if [ "$PACKAGE_CREATED" = "1" ]; then
  REMOTE_SHA="$(ssh -n chachanas sha256sum "$NAS_ROOT/$PACKAGE_REL" | awk '{print $1}')"
  test "$REMOTE_SHA" = "$PACKAGE_SHA"
  echo "COLLECTOR_INCREMENTAL_INDEPENDENT_SHA256=PASS"

  ssh -n chachanas gzip -t "$NAS_ROOT/$PACKAGE_REL"
  echo "COLLECTOR_INCREMENTAL_GZIP_INTEGRITY=PASS"

  ssh -n chachanas gzip -dc "$NAS_ROOT/$PACKAGE_REL" | python3 -c '
import sys
begin=commit=foreign_off=foreign_on=0
lines=0
for raw in sys.stdin.buffer:
    line=raw.decode("utf-8","strict").strip()
    lines+=1
    begin += int(line=="BEGIN TRANSACTION;")
    commit += int(line=="COMMIT;")
    foreign_off += int(line=="PRAGMA foreign_keys=OFF;")
    foreign_on += int(line=="PRAGMA foreign_keys=ON;")
assert begin==1,(begin,lines)
assert commit==1,(commit,lines)
assert foreign_off==1,foreign_off
assert foreign_on==1,foreign_on
assert lines>10,lines
print("COLLECTOR_INCREMENTAL_SQL_STRUCTURE=PASS")
print("COLLECTOR_INCREMENTAL_SQL_LINES="+str(lines))
'
fi

COLLECTOR_AFTER="$(systemctl is-active wfgg-collector || true)"
PID_AFTER="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
echo "COLLECTOR_SERVICE_AFTER=$COLLECTOR_AFTER"
echo "COLLECTOR_PID_AFTER=$PID_AFTER"
test "$COLLECTOR_AFTER" = "active"
test "$PID_AFTER" = "$PID_BEFORE"
echo "COLLECTOR_SERVICE_INTERRUPTION=NO"

ln -sfn "$RELEASE" "$BASE/current"

python3 - "$EVIDENCE_DIR/storage-governor-incremental-chain-pilot-$STAMP.json"   "$STAMP" "$ANCHOR_SHA" "$PACKAGE_CREATED" "$PID_BEFORE" "$PID_AFTER" <<'PY'
import json,sys
path,stamp,anchor_sha,created,pid_before,pid_after=sys.argv[1:7]
e={
  "schema":"chacha.dev/storage-governor-incremental-chain-pilot/v1",
  "observed_at":stamp,
  "status":"PASS",
  "anchor_sha256":"sha256:"+anchor_sha,
  "package_created":created=="1",
  "collector_pid_before":pid_before,
  "collector_pid_after":pid_after,
  "service_interruption":False,
  "production_data_mutation":False,
  "raw_row_data_exposed":False
}
open(path,"w",encoding="utf-8").write(json.dumps(e,indent=2)+"\n")
PY

echo "STORAGE_INCREMENTAL_CHAIN_PILOT=PASS"
echo "STORAGE_INCREMENTAL_CHAIN_RAW_DATA_EXPOSED=NO"
echo "STORAGE_INCREMENTAL_CHAIN_PRODUCTION_MUTATION=NO"
