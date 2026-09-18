#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_REVISION="4118c5b36a99d76d29d8fc96c8485499425951d7"
ARTIFACT_REVISION="f36b2e8b35622aad24731b99c85ed1f3ab32b6ec"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${SOURCE_REVISION}"
ARTIFACT_RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${ARTIFACT_REVISION}"
PORTABLE_SHA="3121f9a11bcc250b671ee899ac8dd97e50ba22c86e6f76a7c608a6eceaf83623"
BASE="/opt/chacha-dev/adapters/storage-restore-verifier"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
NAS_ROOT="/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="collector-restore-verify-$STAMP"
RELEASE="$BASE/releases/$STAMP"
WORK="/tmp/chacha-restore-verifier-$STAMP"

cleanup() {
  rm -rf -- "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "STORAGE_RESTORE_VERIFIER_PILOT=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 ssh scp sha256sum systemctl ln df; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "STORAGE_RESTORE_VERIFIER_PILOT=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$RELEASE" "$EVIDENCE_DIR" "$WORK"

curl -fsSL "$RAW/dev-hub/adapters/storage-restore-verifier-adapter.py"   -o "$RELEASE/storage-restore-verifier-adapter"
chmod 0755 "$RELEASE/storage-restore-verifier-adapter"
python3 -m py_compile "$RELEASE/storage-restore-verifier-adapter"

curl -fsSL "$ARTIFACT_RAW/dev-hub/release/storage-restore-verifier-nas-linux-amd64"   -o "$WORK/storage-restore-verifier-nas-linux-amd64"
chmod 0700 "$WORK/storage-restore-verifier-nas-linux-amd64"
LOCAL_PORTABLE_SHA="$(sha256sum "$WORK/storage-restore-verifier-nas-linux-amd64" | awk '{print $1}')"
test "$LOCAL_PORTABLE_SHA" = "$PORTABLE_SHA"

echo "STORAGE_RESTORE_VERIFIER_INSTALL=STAGED"
echo "PORTABLE_RESTORE_VERIFIER_SHA256=sha256:$LOCAL_PORTABLE_SHA"

echo "=== NAS RESTORE CAPABILITIES ==="
NAS_ARCH="$(ssh -n chachanas uname -m)"
echo "NAS_ARCH=$NAS_ARCH"
case "$NAS_ARCH" in
  x86_64|amd64) ;;
  *)
    echo "NAS_RESTORE_RUNTIME=BLOCKED reason=unsupported_arch"
    exit 3
    ;;
esac
echo "NAS_SQLITE3=NOT_REQUIRED"
echo "NAS_RESTORE_RUNTIME=PASS"

COLLECTOR_BEFORE="$(systemctl is-active wfgg-collector || true)"
PID_BEFORE="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
FREE_BEFORE="$(df -Pk / | awk 'NR==2{print $4}')"
echo "COLLECTOR_SERVICE_BEFORE=$COLLECTOR_BEFORE"
echo "COLLECTOR_PID_BEFORE=$PID_BEFORE"
echo "VPS_FREE_KB_BEFORE=$FREE_BEFORE"
test "$COLLECTOR_BEFORE" = "active"

python3 - "$WORK/request.json" "$RUN_ID" <<'PY'
import json,sys
out,run_id=sys.argv[1:3]
payload={
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"wfgg-radar",
  "transition":"collector-master-restore-verification",
  "run_id":run_id,
  "wave":1,
  "task":{
    "id":"collector-master-restore-verification",
    "kind":"verification",
    "description":"Independently restore and verify Collector MASTER plus chain anchor.",
    "owner_role":"storage-restore-verifier",
    "permission":"workspace-write",
    "outputs":[{"type":"gate","id":"collector-restore-proof"}],
    "verification":{"required":True,"mode":"machine"}
  },
  "bindings":[{
    "capability":"storage-governance",
    "provider":"storage-restore-verifier",
    "adapter":"storage-restore-verifier-adapter",
    "fallback_used":False,
    "health_state":"contract-ok"
  }],
  "policy_context":{
    "resource_class":"heavy",
    "requires_storage_preflight":False,
    "human_approval_required":False,
    "approval_id":None,
    "timeout_seconds":1800
  },
  "workspace":"/opt/chacha-dev",
  "metadata":{"storage_restore_verifier":{
    "action":"verify-master-anchor",
    "master_archive":"projects/wfgg/backups/collector-master-20260918T085757Z.sql.gz",
    "master_sha256":"sha256:4fd82f1ecab892372998dd4ef6e0df085474876a914409f70c6502d97929f730",
    "anchor_path":"projects/wfgg/backups/collector-chain/collector-chain-state-000000.json",
    "anchor_sha256":"sha256:9f83a76d63d4bb161244ed2e1f6abe2bc4eda943f8f2ad1479de5b1c983e1010",
    "portable_verifier_sha256":"sha256:3121f9a11bcc250b671ee899ac8dd97e50ba22c86e6f76a7c608a6eceaf83623",
    "baseline_cycle":35,
    "observations_watermark":{
      "observed_at":"2026-09-18T05:18:47.18986397Z",
      "id":126611
    },
    "masters_watermark":{
      "created_at":"2026-09-11T22:23:30.164682Z",
      "id":1
    },
    "expected_rows":{
      "cycle_baseline":1171660,
      "cycle_changes":96024,
      "cycle_seen":470620,
      "cycles":35,
      "identity_coverage":0,
      "master_players":27753,
      "masters":1,
      "observations":126611,
      "player_aliases":56695,
      "player_identity":56645,
      "players":56645
    }
  }}
}
open(out,"w",encoding="utf-8").write(json.dumps(payload))
PY

CHACHA_NAS_HOST="chachanas" CHACHA_NAS_ROOT="$NAS_ROOT" CHACHA_PORTABLE_RESTORE_VERIFIER="$WORK/storage-restore-verifier-nas-linux-amd64" "$RELEASE/storage-restore-verifier-adapter"   < "$WORK/request.json"   > "$WORK/result.json"

python3 - "$WORK/result.json" "$EVIDENCE_DIR/storage-restore-verifier-pilot-$STAMP.json" <<'PY'
import json,sys
src,evidence_path=sys.argv[1:3]
x=json.load(open(src))
assert x["schema"]=="chacha.dev/task-result/v1",x
assert x["status"]=="OK",x
assert x["summary"]=="COLLECTOR_MASTER_RESTORE_VERIFIED",x
assert x["verification"]["status"]=="VERIFIED",x
details=x["evidence"][0]["details"]
assert details["integrity"]=="ok",details
assert details["table_count"]==11,details
assert details["baseline_cycle"]==35,details
assert details["sandbox_deleted_after_verification"] is True,details
assert details["production_data_mutation"] is False,details
print("COLLECTOR_MASTER_RESTORE_VERIFIED=PASS")
print("COLLECTOR_RESTORE_SQLITE_INTEGRITY=PASS")
print("COLLECTOR_RESTORE_TABLE_COUNT="+str(details["table_count"]))
print("COLLECTOR_RESTORE_BASELINE_CYCLE="+str(details["baseline_cycle"]))
print("COLLECTOR_RESTORE_PORTABLE_SHA256="+details["portable_verifier_sha256"])
print("COLLECTOR_RESTORE_PORTABLE_ARCH="+details["portable_verifier_arch"])
for table,count in sorted(details["row_counts"].items()):
    print("COLLECTOR_RESTORE_ROWS|table="+table+"|rows="+str(count))
ev={
  "schema":"chacha.dev/storage-restore-verifier-pilot/v1",
  "status":"PASS",
  "observed_at":x["observed_at"],
  "verification":x["verification"],
  "details":details,
  "raw_row_data_exposed":False,
  "production_data_mutation":False
}
open(evidence_path,"w",encoding="utf-8").write(json.dumps(ev,indent=2)+"\n")
PY

SANDBOX="$NAS_ROOT/artifacts/restore-verification/$RUN_ID"
if ssh -n chachanas test -e "$SANDBOX"; then
  echo "COLLECTOR_RESTORE_SANDBOX_CLEANUP=FAILED"
  exit 7
fi
echo "COLLECTOR_RESTORE_SANDBOX_CLEANUP=PASS"

COLLECTOR_AFTER="$(systemctl is-active wfgg-collector || true)"
PID_AFTER="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
FREE_AFTER="$(df -Pk / | awk 'NR==2{print $4}')"
echo "COLLECTOR_SERVICE_AFTER=$COLLECTOR_AFTER"
echo "COLLECTOR_PID_AFTER=$PID_AFTER"
echo "VPS_FREE_KB_AFTER=$FREE_AFTER"
test "$COLLECTOR_AFTER" = "active"
test "$PID_AFTER" = "$PID_BEFORE"
echo "COLLECTOR_SERVICE_INTERRUPTION=NO"

DELTA=$(( FREE_BEFORE > FREE_AFTER ? FREE_BEFORE - FREE_AFTER : FREE_AFTER - FREE_BEFORE ))
echo "VPS_RESTORE_LOCAL_DELTA_KB=$DELTA"
if [ "$DELTA" -gt 20480 ]; then
  echo "VPS_RESTORE_LOCAL_FOOTPRINT=BLOCKED"
  exit 8
fi
echo "VPS_FULL_LOCAL_RESTORE=NO"

ln -sfn "$RELEASE" "$BASE/current"

echo "STORAGE_RESTORE_VERIFIER_CURRENT=$BASE/current/storage-restore-verifier-adapter"
echo "STORAGE_RESTORE_VERIFIER_PILOT=PASS"
echo "STORAGE_RESTORE_VERIFIER_INDEPENDENT=YES"
echo "STORAGE_RESTORE_VERIFIER_NAS_SQLITE_INSTALL=NO"
echo "STORAGE_RESTORE_VERIFIER_PRODUCTION_MUTATION=NO"
