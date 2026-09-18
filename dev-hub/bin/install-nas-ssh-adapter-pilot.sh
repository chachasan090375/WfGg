#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="dev-hub-v5-nas-ssh-adapter-pilot-prep"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${BRANCH}"
BASE="/opt/chacha-dev/adapters/nas-ssh"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
NAS_HOST="chachanas"
NAS_ROOT="/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
WORK="/tmp/chacha-nas-pilot-$STAMP"
REMOTE_REL="artifacts/adapter-pilot/nas-ssh-pilot-$STAMP.txt"
REMOTE_ABS="$NAS_ROOT/$REMOTE_REL"

cleanup() {
  rm -rf -- "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "NAS_PILOT=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 ssh scp sha256sum install ln; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "NAS_PILOT=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$RELEASE" "$EVIDENCE_DIR" "$WORK"

echo "=== NAS SSH ADAPTER PILOT PREP ==="

curl -fsSL "$RAW/dev-hub/adapters/nas-ssh-adapter.py" -o "$RELEASE/nas-ssh-adapter"
chmod 0755 "$RELEASE/nas-ssh-adapter"
python3 -m py_compile "$RELEASE/nas-ssh-adapter"
echo "NAS_ADAPTER_INSTALL=STAGED"

ssh -o BatchMode=yes -o ConnectTimeout=12 "$NAS_HOST" 'echo NAS_RUNTIME_LINK=OK; hostname' >"$WORK/nas-link.txt"
grep -Fq 'NAS_RUNTIME_LINK=OK' "$WORK/nas-link.txt"
echo "NAS_RUNTIME_LINK=PASS"

ssh "$NAS_HOST" mkdir -p "$NAS_ROOT/artifacts/adapter-pilot"

cat > "$WORK/payload.txt" <<EOF
ChaCha DEV NAS adapter sandbox pilot
stamp=$STAMP
EOF

python3 - "$WORK/preflight.json" "$WORK" <<'PY'
import json,sys
out,workspace=sys.argv[1:3]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"chacha-dev",
  "transition":"nas-adapter-pilot-preflight",
  "run_id":"nas-pilot-preflight",
  "wave":1,
  "task":{
    "id":"nas-pilot-preflight",
    "kind":"storage-preflight",
    "description":"Real NAS pilot preflight.",
    "owner_role":"storage-governor",
    "permission":"read",
    "outputs":[{"type":"gate","id":"storage-preflight"}],
    "verification":{"required":True,"mode":"machine"}
  },
  "bindings":[{
    "capability":"artifact-store",
    "provider":"nas",
    "adapter":"nas-ssh-adapter",
    "fallback_used":False,
    "health_state":"pilot"
  }],
  "policy_context":{
    "resource_class":"small",
    "requires_storage_preflight":True,
    "human_approval_required":False,
    "approval_id":None,
    "timeout_seconds":20
  },
  "workspace":workspace,
  "metadata":{"nas_storage":{"action":"preflight","need_mb":1,"reserve_mb":1024}}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

CHACHA_NAS_HOST="$NAS_HOST" CHACHA_NAS_ROOT="$NAS_ROOT" "$RELEASE/nas-ssh-adapter" < "$WORK/preflight.json" > "$WORK/preflight-result.json"

python3 - "$WORK/preflight-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["schema"]=="chacha.dev/task-result/v1",x
assert x["status"]=="OK",x
assert x["summary"]=="NAS_PREFLIGHT_OK",x
assert x["verification"]["status"]=="UNVERIFIED",x
print("NAS_ADAPTER_PREFLIGHT=PASS")
PY

python3 - "$WORK/put.json" "$WORK" "$REMOTE_REL" <<'PY'
import json,sys
out,workspace,remote=sys.argv[1:4]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"chacha-dev",
  "transition":"nas-adapter-pilot-write",
  "run_id":"nas-pilot-write",
  "wave":1,
  "task":{
    "id":"nas-pilot-write",
    "kind":"artifact-store",
    "description":"Sandbox create-only NAS pilot artifact.",
    "owner_role":"storage-governor",
    "permission":"workspace-write",
    "outputs":[{"type":"artifact","id":remote}],
    "verification":{"required":True,"mode":"machine"}
  },
  "bindings":[{
    "capability":"artifact-store",
    "provider":"nas",
    "adapter":"nas-ssh-adapter",
    "fallback_used":False,
    "health_state":"pilot"
  }],
  "policy_context":{
    "resource_class":"small",
    "requires_storage_preflight":True,
    "human_approval_required":False,
    "approval_id":None,
    "timeout_seconds":30
  },
  "workspace":workspace,
  "metadata":{"nas_storage":{
    "action":"put-file",
    "local_path":"payload.txt",
    "remote_path":remote,
    "reserve_mb":1024
  }}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

CHACHA_NAS_HOST="$NAS_HOST" CHACHA_NAS_ROOT="$NAS_ROOT" "$RELEASE/nas-ssh-adapter" < "$WORK/put.json" > "$WORK/put-result.json"

python3 - "$WORK/put-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["schema"]=="chacha.dev/task-result/v1",x
assert x["status"]=="OK",x
assert x["summary"]=="NAS_PUT_FILE_OK",x
assert x["verification"]["status"]=="UNVERIFIED",x
print("NAS_ADAPTER_PUT_FILE=PASS")
PY

LOCAL_SHA="$(sha256sum "$WORK/payload.txt" | awk '{print $1}')"
REMOTE_SHA="$(ssh "$NAS_HOST" sha256sum "$REMOTE_ABS" | awk '{print $1}')"
test -n "$LOCAL_SHA"
test "$LOCAL_SHA" = "$REMOTE_SHA"
echo "NAS_ADAPTER_INDEPENDENT_SHA256=PASS"

ln -sfn "$RELEASE" "$BASE/current"

python3 - "$EVIDENCE_DIR/nas-ssh-adapter-pilot-$STAMP.json" "$STAMP" "$REMOTE_REL" "$LOCAL_SHA" "$RELEASE" <<'PY'
import json,sys
path,stamp,remote,digest,release=sys.argv[1:6]
e={
  "schema":"chacha.dev/nas-ssh-adapter-pilot-evidence/v1",
  "observed_at":stamp,
  "status":"PASS",
  "adapter":"nas-ssh-adapter",
  "provider":"nas",
  "runtime_path":release+"/nas-ssh-adapter",
  "preflight":"PASS",
  "sandbox_put_file":"PASS",
  "independent_sha256":"PASS",
  "remote_artifact":remote,
  "digest":"sha256:"+digest,
  "production_mutation":False,
  "persistent_delete":False
}
open(path,"w",encoding="utf-8").write(json.dumps(e,indent=2)+"\n")
PY

echo "NAS_ADAPTER_CURRENT=$BASE/current/nas-ssh-adapter"
echo "NAS_ADAPTER_PILOT_RUNTIME=PASS"
echo "NAS_ADAPTER_PRODUCTION_MUTATION=NO"
echo "NAS_ADAPTER_PERSISTENT_DELETE=NO"
