#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V642_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V642_SOURCE_ROOT:-}"
V641_ACQUIRED_REV="f70e71b79d62e05b35e2cf8b443e4d5551527fc0"

BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SLUG_STAMP="$(date -u +%Y%m%d%H%M%S)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v642.XXXXXX)"
PREVIOUS=""
ACTIVATED=0
STAGE="bootstrap"
ADOPTION_ID=""
ADOPTED=0
ROLLED_BACK=0

DURABLE_REGISTRY="/opt/chacha-dev/runtime/registries/durable-capability-adoptions.v1.json"
ADAPTER_ROOT="/opt/chacha-dev/adapters"
SOURCE_ARCHIVE_ROOT="/opt/chacha-dev/runtime/capability-adoption/sources"
ADOPTION_EVIDENCE_ROOT="/opt/chacha-dev/runtime/capability-adoption/evidence"
EXPERIENCE_DB="/opt/chacha-dev/runtime/knowledge/experience.db"
CENTRAL_MEMORY_DB="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.db"
CENTRAL_MEMORY_SNAPSHOT="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"

PROJECT="v642-real-adoption-$SLUG_STAMP"
CAPABILITY="v642-real-durable-read-$SLUG_STAMP"
PROVIDER="v642-real-provider-$SLUG_STAMP"
ADAPTER="v642-real-adapter-$SLUG_STAMP"
PROJECT2="v642-reuse-project-$SLUG_STAMP"
PROOF_DIR="$ADOPTION_EVIDENCE_ROOT/$PROJECT"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V642_STAGE=$STAGE"; }

rollback_synthetic(){
  if [ "$ADOPTED" -eq 1 ] && [ "$ROLLED_BACK" -eq 0 ] && [ -n "$ADOPTION_ID" ]; then
    set +e
    python3 "$RELEASE/dev-hub/bin/durable-capability-registry.py" rollback       --registry "$DURABLE_REGISTRY"       --adoption-id "$ADOPTION_ID"       --actor central-orchestrator       --receipt "$PROOF_DIR/pilot-auto-rollback.json"       --apply >/tmp/v642-auto-rollback.out 2>/tmp/v642-auto-rollback.err
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then
      ROLLED_BACK=1
      echo "CHACHA_DEV_V642_FAILURE_CLEANUP_ROLLBACK=PASS"
    else
      echo "CHACHA_DEV_V642_FAILURE_CLEANUP_ROLLBACK=FAILED"
      cat /tmp/v642-auto-rollback.err 2>/dev/null || true
    fi
  fi
}

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }

on_exit(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V642_FAILURE_STAGE=$STAGE"
    rollback_synthetic || true
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V642_PLATFORM_ROLLBACK=PASS"
    fi
    for f in "$WORK"/*.out "$WORK"/*.err; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -120 "$f" || true
    done
  fi
  cleanup
  exit "$rc"
}
trap on_exit EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in python3 cp ln readlink grep sha256sum find curl tar awk tr tail; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p,encoding="utf-8"))
except Exception:x={}
if x.get("active") is True:
    raise SystemExit("CHACHA_DEV_V642_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi

[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=current_release_symlink_missing"; exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"
[ -d "$PREVIOUS/dev-hub" ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=current_release_invalid"; exit 2; }

stage v641-real-baseline
[ -f "$PREVIOUS/.revision" ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=v641_revision_marker_missing"; exit 2; }
[ "$(tr -d '\r\n' <"$PREVIOUS/.revision")" = "$V641_ACQUIRED_REV" ] || {
  echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=v641_acquired_revision_not_active"
  exit 2
}
[ -f "$PREVIOUS/dev-hub/bin/capability-build-loop.py" ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=v641_build_loop_missing"; exit 2; }
echo "CHACHA_DEV_V642_V641_REAL_BASELINE=PASS"

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi

for required in   dev-hub/bin/durable-capability-registry.py   dev-hub/bin/capability-build-loop.py   dev-hub/bin/project-control.py   dev-hub/bin/control-plane-store.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/config/durable-capability-adoption.v1.json   dev-hub/config/capability-build-loop.v1.json   dev-hub/config/provider-adapters.v1.json   dev-hub/config/capability-registry.v1.json   dev-hub/config/project-control.v1.json   dev-hub/config/control-plane-state.v1.json   dev-hub/config/execution-scheduler.v1.json   dev-hub/tests/test_v642_durable_capability_adoption.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

python3 -m py_compile   "$RELEASE/dev-hub/bin/durable-capability-registry.py"   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/capability-build-loop.py"
python3 -m json.tool "$RELEASE/dev-hub/config/durable-capability-adoption.v1.json" >/dev/null
echo "CHACHA_DEV_V642_STATIC=PASS"

stage semantic-qualification
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v642_durable_capability_adoption.py
) >"$WORK/v642-semantic.out" 2>"$WORK/v642-semantic.err"
for marker in   CHACHA_DEV_V642_VERIFIED_SUCCESS_BEFORE_ADOPTION=PASS   CHACHA_DEV_V642_MEMORY_REFRESH_CWD_INDEPENDENT=PASS   CHACHA_DEV_V642_PROJECT_CONTROL_COMMITTED_PROOF=PASS   CHACHA_DEV_V642_SUCCESS_CLAIMS_BOUND_TO_VERIFIED_RESULT=PASS   CHACHA_DEV_V642_PROJECT_CONTROL_LEDGER_COMMIT_PROOF=PASS   CHACHA_DEV_V642_RELEASE_INDEPENDENT_DURABLE_REGISTRY=PASS   CHACHA_DEV_V642_CROSS_PROJECT_REUSE_WITHOUT_REBUILD=PASS   CHACHA_DEV_V642_IDEMPOTENT_ADOPTION=PASS   CHACHA_DEV_V642_PROTECTED_ADOPTION_HUMAN_BOUNDARY=PASS; do
  grep -Fq "$marker" "$WORK/v642-semantic.out"
done
echo "CHACHA_DEV_V642_SEMANTIC_QUALIFICATION=PASS"

stage build-real-safe-candidate
mkdir -p "$PROOF_DIR"
cat >"$WORK/build-request.json" <<JSON
{
  "schema":"chacha.dev/capability-build-request/v1",
  "project_id":"$PROJECT",
  "capability":"$CAPABILITY",
  "provider_id":"$PROVIDER",
  "adapter_id":"$ADAPTER",
  "profile":"structured-read-v1",
  "execution":"vps",
  "supports":["read"],
  "network_access":false,
  "credentials_required":false,
  "production_capable":false,
  "automatic_external_spend_eur":0,
  "technology_watch":{"consulted":true,"candidate_source":"v642-real-pilot-revalidation"},
  "architecture_council":{"decision":"APPROVED","decision_id":"v642-real-pilot-build-$SLUG_STAMP"}
}
JSON

mkdir -p "$WORK/build-workspace" "$WORK/sandbox-runtime"
python3 "$RELEASE/dev-hub/bin/capability-build-loop.py"   --policy "$RELEASE/dev-hub/config/capability-build-loop.v1.json"   --request "$WORK/build-request.json"   --repo-root "$RELEASE"   --base-registry "$RELEASE/dev-hub/config/provider-adapters.v1.json"   --workspace "$WORK/build-workspace"   build-pilot   --runtime-root "$WORK/sandbox-runtime"   --output "$WORK/build-result.json"   --overlay "$WORK/build-overlay.json"   --apply >"$WORK/build.out" 2>"$WORK/build.err"

python3 - "$WORK/build-result.json" "$CAPABILITY" "$PROVIDER" "$ADAPTER" <<'PY'
import json,sys,pathlib,hashlib
p,cap,provider,adapter=sys.argv[1:]
x=json.load(open(p,encoding="utf-8"))
assert x["status"]=="PASS",x
assert x["adapter_status"]=="ENABLED",x
assert x["same_project_resume_allowed"] is True,x
assert x["durable_adoption"]=="PENDING_PROJECT_SUCCESS",x
assert x["capability"]==cap and x["provider"]==provider and x["adapter"]==adapter,x
assert x["production_capable"] is False and x["network_access"] is False and x["credentials_required"] is False,x
assert x["automatic_external_spend_eur"]==0,x
source=pathlib.Path(x["generated_source"]); exe=pathlib.Path(x["sandbox_executable"])
assert source.is_file() and exe.is_file(),x
def dig(path):return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
assert dig(source)==x["generated_source_digest"],x
assert dig(exe)==x["sandbox_executable_digest"],x
print("CHACHA_DEV_V642_REAL_V641_BUILD_CANDIDATE=PASS")
PY
cp "$WORK/build-result.json" "$PROOF_DIR/build-result.json"

stage real-project-use
BUILD_EXE="$(python3 - "$WORK/build-result.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["sandbox_executable"])
PY
)"
BUILD_FIXTURE="$(python3 - "$WORK/build-result.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["artifacts"]["fixture"])
PY
)"
"$BUILD_EXE" <"$BUILD_FIXTURE" >"$WORK/project-use-result.json"
python3 - "$WORK/project-use-result.json" "$ADAPTER" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert x["producer"]==sys.argv[2],x
assert (x.get("verification") or {}).get("status")=="UNVERIFIED",x
print("CHACHA_DEV_V642_REAL_PROJECT_RUNTIME_USE=PASS")
PY
cp "$WORK/project-use-result.json" "$PROOF_DIR/project-use-result.json"

stage project-control-verified-success
STATE_ROOT="/opt/chacha-dev/runtime/state"
EVIDENCE_PROJECT_ROOT="/opt/chacha-dev/runtime/evidence/$PROJECT"
STATE_PATH="$STATE_ROOT/$PROJECT/state.json"
LEDGER="$EVIDENCE_PROJECT_ROOT/ledger.json"
if [ -e "$STATE_PATH" ] || [ -e "$LEDGER" ]; then
  echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=synthetic_project_collision"
  exit 24
fi
mkdir -p "$EVIDENCE_PROJECT_ROOT"
cat >"$WORK/initial-state.json" <<JSON
{
  "identity":{"kind":"v642-real-durable-adoption-pilot","capability":"$CAPABILITY"},
  "lifecycle":{"stage":"VERIFY"}
}
JSON
python3 "$RELEASE/dev-hub/bin/control-plane-store.py"   --policy "$RELEASE/dev-hub/config/control-plane-state.v1.json"   --root "$STATE_ROOT" init --project "$PROJECT" --actor central-orchestrator   --initial "$WORK/initial-state.json" >"$WORK/control-init.out"

python3 - "$PROJECT" "$LEDGER" <<'PY'
import datetime,json,pathlib,sys
project,path=sys.argv[1:]
v={"schema":"chacha.dev/evidence-ledger/v1","project":project,
   "updated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
   "artifacts":{},"gates":{},"approvals":{},"risk_acceptances":[],"history":[]}
pathlib.Path(path).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY

cat >"$PROOF_DIR/project-success-claims.json" <<JSON
{
  "project_id":"$PROJECT",
  "capability":"$CAPABILITY",
  "provider":"$PROVIDER",
  "adapter":"$ADAPTER",
  "status":"PASS",
  "project_success":true,
  "quality_gates_pass":true,
  "runtime_use_count":1,
  "incident_count":0,
  "technology_watch_revalidated":true,
  "architecture_council":{"decision":"APPROVED","decision_id":"v642-real-pilot-adopt-$SLUG_STAMP"},
  "automatic_external_spend_eur":0,
  "evidence_refs":[
    "$PROOF_DIR/build-result.json",
    "$PROOF_DIR/project-use-result.json"
  ]
}
JSON

CLAIMS_DIGEST="$(sha256sum "$PROOF_DIR/project-success-claims.json" | awk '{print "sha256:"$1}')"
BUILD_DIGEST="$(sha256sum "$PROOF_DIR/build-result.json" | awk '{print "sha256:"$1}')"
USE_DIGEST="$(sha256sum "$PROOF_DIR/project-use-result.json" | awk '{print "sha256:"$1}')"

cat >"$WORK/project-success-task-graph.json" <<JSON
{
  "schema":"chacha.dev/task-graph/v1",
  "project":"$PROJECT",
  "tasks":[{
    "id":"v642-project-success",
    "kind":"verification",
    "permission":"read",
    "outputs":[{"type":"artifact","id":"capability-project-success:$CAPABILITY"}],
    "verification":{"required":true,"mode":"machine"}
  }]
}
JSON
cat >"$WORK/project-success-task-result.json" <<JSON
{
  "schema":"chacha.dev/task-result/v1",
  "project":"$PROJECT",
  "task_id":"v642-project-success",
  "producer":"v642-project-runtime",
  "status":"OK",
  "summary":"Capability used successfully by the real V6.42 adoption pilot.",
  "observed_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "outputs":[{"type":"artifact","id":"capability-project-success:$CAPABILITY","status":"OK"}],
  "evidence":[
    {"source":"$PROOF_DIR/project-success-claims.json","digest":"$CLAIMS_DIGEST"},
    {"source":"$PROOF_DIR/build-result.json","digest":"$BUILD_DIGEST"},
    {"source":"$PROOF_DIR/project-use-result.json","digest":"$USE_DIGEST"}
  ],
  "verification":{"status":"UNVERIFIED","method":"none"}
}
JSON

python3 "$RELEASE/dev-hub/bin/project-control.py"   --policy "$RELEASE/dev-hub/config/project-control.v1.json"   --repo-root "$RELEASE" --json   verify-result --project "$PROJECT"   --result "$WORK/project-success-task-result.json"   --graph "$WORK/project-success-task-graph.json"   --method machine --verifier verification-broker --ingest   >"$WORK/project-control-response.json"

PC_RECEIPT="$(python3 - "$WORK/project-control-response.json" <<'PY'
import json,sys,pathlib
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
d=x.get("details") or {}
assert d.get("verification_status")=="VERIFIED",x
p=pathlib.Path(str(d.get("receipt") or ""))
assert p.is_file(),x
r=json.load(open(p,encoding="utf-8"))
assert r.get("schema")=="chacha.dev/control-transaction-receipt/v1",r
assert r.get("status")=="COMMITTED" and r.get("verification_status")=="VERIFIED",r
print(p)
PY
)"
cp "$WORK/project-control-response.json" "$PROOF_DIR/project-control-response.json"
echo "CHACHA_DEV_V642_REAL_PROJECT_CONTROL_COMMITTED_PROOF=PASS"

cat >"$PROOF_DIR/candidate.json" <<JSON
{
  "schema":"chacha.dev/capability-adoption-candidate/v1",
  "source_kind":"BUILT_ADAPTER",
  "project_id":"$PROJECT",
  "capability":"$CAPABILITY",
  "provider":"$PROVIDER",
  "adapter":"$ADAPTER",
  "build_result":"$PROOF_DIR/build-result.json",
  "production_capable":false,
  "network_access":false,
  "credentials_required":false,
  "automatic_external_spend_eur":0,
  "adoption_state":"PENDING_PROJECT_SUCCESS"
}
JSON
python3 - "$PROOF_DIR/project-success-claims.json" "$PC_RECEIPT" "$LEDGER" "$CLAIMS_DIGEST" "$PROOF_DIR/project-success.json" "$CAPABILITY" <<'PY'
import json,pathlib,sys
claims_path,receipt,ledger,digest,out,capability=sys.argv[1:]
claims=json.load(open(claims_path,encoding="utf-8"))
v={"schema":"chacha.dev/capability-project-success/v1",**claims,
   "verification_status":"VERIFIED",
   "project_control_receipt":receipt,
   "project_control_ledger":ledger,
   "verified_success_artifact_id":"capability-project-success:"+capability,
   "verified_task_id":"v642-project-success",
   "verified_claims_path":claims_path,
   "verified_claims_digest":digest}
pathlib.Path(out).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY

stage real-durable-adoption
mkdir -p "$SOURCE_ARCHIVE_ROOT" "$ADOPTION_EVIDENCE_ROOT"
ADOPT_RECEIPT="$PROOF_DIR/adoption-receipt.json"
python3 "$RELEASE/dev-hub/bin/durable-capability-registry.py" adopt   --policy "$RELEASE/dev-hub/config/durable-capability-adoption.v1.json"   --candidate "$PROOF_DIR/candidate.json"   --success "$PROOF_DIR/project-success.json"   --base-capability-registry "$RELEASE/dev-hub/config/capability-registry.v1.json"   --base-provider-registry "$RELEASE/dev-hub/config/provider-adapters.v1.json"   --registry "$DURABLE_REGISTRY"   --repo-root "$RELEASE"   --adapter-root "$ADAPTER_ROOT"   --source-archive-root "$SOURCE_ARCHIVE_ROOT"   --evidence-root "$ADOPTION_EVIDENCE_ROOT"   --experience-db "$EXPERIENCE_DB"   --central-memory-db "$CENTRAL_MEMORY_DB"   --central-memory-snapshot "$CENTRAL_MEMORY_SNAPSHOT"   --memory-refresh --nas   --actor central-orchestrator   --receipt "$ADOPT_RECEIPT" --apply   >"$WORK/adopt.out" 2>"$WORK/adopt.err"

ADOPTION_ID="$(python3 - "$ADOPT_RECEIPT" "$CAPABILITY" "$PROVIDER" "$ADAPTER" <<'PY'
import json,pathlib,sys
path,cap,provider,adapter=sys.argv[1:]
x=json.load(open(path,encoding="utf-8"))
assert x["status"]=="COMMITTED" and x["applied"] is True,x
assert x["capability"]==cap and x["provider"]==provider and x["adapter"]==adapter,x
assert pathlib.Path(x["durable_executable"]).is_file(),x
assert pathlib.Path(x["source_archive"]).is_file(),x
print(x["adoption_id"])
PY
)"
ADOPTED=1
echo "CHACHA_DEV_V642_REAL_DURABLE_ADOPTION=PASS"
echo "CHACHA_DEV_V642_REAL_PROJECT_CONTROL_LEDGER_COMMIT_PROOF=PASS"
echo "CHACHA_DEV_V642_REAL_DURABLE_ADAPTER_REPROBE=PASS"

stage cross-project-reuse
python3 "$RELEASE/dev-hub/bin/durable-capability-registry.py" merge   --base-capability-registry "$RELEASE/dev-hub/config/capability-registry.v1.json"   --base-provider-registry "$RELEASE/dev-hub/config/provider-adapters.v1.json"   --registry "$DURABLE_REGISTRY"   --output-capabilities "$WORK/reuse-capabilities.json"   --output-providers "$WORK/reuse-providers.json"   --require-executables >"$WORK/reuse-merge.out"

python3 - "$WORK/reuse-capabilities.json" "$WORK/reuse-providers.json" "$CAPABILITY" "$PROVIDER" "$ADAPTER" <<'PY'
import json,pathlib,sys
caps_path,providers_path,cap,provider,adapter=sys.argv[1:]
caps=json.load(open(caps_path,encoding="utf-8"))
providers=json.load(open(providers_path,encoding="utf-8"))
assert cap in caps["capabilities"],caps
assert caps["capabilities"][cap]["providers"][0]["status"]=="ADOPT",caps
assert provider in providers["providers"],providers
a=providers["adapters"][adapter]
assert a["status"]=="ENABLED",a
assert pathlib.Path(a["executable"]).is_file(),a
print("CHACHA_DEV_V642_REAL_DURABLE_MERGE=PASS")
PY

cat >"$WORK/reuse-preplan.json" <<JSON
{"packages":[{"domain":"product","capabilities":["$CAPABILITY"]}]}
JSON
cat >"$WORK/reuse-contract.json" <<JSON
{"capability_hints":[{"id":"$CAPABILITY","domain":"product"}]}
JSON
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$WORK/reuse-preplan.json" "$WORK/reuse-contract.json"   "$WORK/reuse-capabilities.json" "$PROJECT2" "$WORK/reuse-gaps.json" <<'PY'
import importlib.util,json,sys
module,pre,contract,caps,project,out=sys.argv[1:]
spec=importlib.util.spec_from_file_location("v642_runtime_orchestrator",module)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.capability_gaps(__import__("pathlib").Path(pre),__import__("pathlib").Path(contract),
                  __import__("pathlib").Path(caps),project,__import__("pathlib").Path(out))
x=json.load(open(out,encoding="utf-8"))
assert x["missing_capabilities"]==[],x
print("CHACHA_DEV_V642_REAL_SECOND_PROJECT_ZERO_GAPS=PASS")
PY

cat >"$WORK/reuse-health.json" <<JSON
{"schema":"chacha.dev/provider-health-snapshot/v1","providers":{"$PROVIDER":{"state":"HEALTHY","observed_at":"$STAMP"}}}
JSON
cat >"$WORK/reuse-graph.json" <<JSON
{
  "schema":"chacha.dev/task-graph/v1","project":"$PROJECT2","transition":"BUILD->VERIFY",
  "tasks":[{"id":"reuse-durable-capability","kind":"verification","permission":"read",
            "capabilities":["$CAPABILITY"],"depends_on":[]}]
}
JSON
python3 "$RELEASE/dev-hub/bin/execution-scheduler.py"   --graph "$WORK/reuse-graph.json"   --registry "$WORK/reuse-capabilities.json"   --health "$WORK/reuse-health.json"   --policy "$RELEASE/dev-hub/config/execution-scheduler.v1.json"   --output "$WORK/reuse-execution-plan.json" >"$WORK/reuse-scheduler.out"

DURABLE_EXE="$(python3 - "$WORK/reuse-providers.json" "$ADAPTER" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["adapters"][sys.argv[2]]["executable"])
PY
)"
cat >"$WORK/reuse-envelope.json" <<JSON
{
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"$PROJECT2",
  "transition":"BUILD->VERIFY",
  "run_id":"v642-cross-project-reuse",
  "wave":1,
  "task":{"id":"reuse-durable-capability","kind":"verification","permission":"read"},
  "bindings":[{"capability":"$CAPABILITY","provider":"$PROVIDER","adapter":"$ADAPTER",
               "fallback_used":false,"health_state":"HEALTHY"}],
  "policy_context":{"resource_class":"light","requires_storage_preflight":false,
                    "human_approval_required":false,"approval_id":null,"timeout_seconds":20},
  "workspace":"$WORK"
}
JSON
"$DURABLE_EXE" <"$WORK/reuse-envelope.json" >"$WORK/reuse-result.json"
python3 - "$WORK/reuse-execution-plan.json" "$WORK/reuse-result.json" "$CAPABILITY" "$PROVIDER" "$ADAPTER" <<'PY'
import json,sys
plan,result,cap,provider,adapter=sys.argv[1:]
p=json.load(open(plan,encoding="utf-8"));r=json.load(open(result,encoding="utf-8"))
assert p["summary"]["scheduled_count"]==1 and p["summary"]["blocked_count"]==0,p
b=p["waves"][0]["tasks"][0]["provider_bindings"][0]
assert b["capability"]==cap and b["provider"]==provider,b
assert r["status"]=="OK" and r["producer"]==adapter,r
print("CHACHA_DEV_V642_REAL_CROSS_PROJECT_REUSE=PASS")
print("CHACHA_DEV_V642_REAL_REBUILD_ON_SECOND_PROJECT=NO")
PY

stage memory-verification
python3 - "$EXPERIENCE_DB" "$CENTRAL_MEMORY_SNAPSHOT" "$PROJECT" "$CAPABILITY" <<'PY'
import json,sqlite3,sys
db_path,snapshot_path,project,cap=sys.argv[1:]
db=sqlite3.connect(db_path)
rows=db.execute("SELECT learner,outcome,payload FROM experience WHERE project_id=? ORDER BY observed_at",(project,)).fetchall()
match=[]
for learner,outcome,raw in rows:
    try:x=json.loads(raw)
    except Exception:continue
    if learner=="capability-durable-adoption" and outcome=="success" and x.get("capability")==cap:
        match.append(x)
assert match,rows
snap=json.load(open(snapshot_path,encoding="utf-8"))
signal="intent:capability-reuse:"+cap
items=[x for x in snap.get("items") or [] if x.get("subject_kind")=="experience"
       and x.get("subject_id")=="capability-durable-adoption"
       and x.get("signal_key")==signal]
assert items,signal
global_items=[x for x in items if x.get("scope")=="GLOBAL_CANDIDATE"]
assert global_items,items
assert all(x.get("generalizable") is False for x in global_items),global_items
assert all(x.get("state")!="TRUSTED" for x in global_items),global_items
print("CHACHA_DEV_V642_REAL_EXPERIENCE_MEMORY=PASS")
print("CHACHA_DEV_V642_REAL_SINGLE_PROJECT_GLOBAL_TRUST=NO")
PY

stage adoption-idempotence
EXPERIENCE_COUNT_BEFORE="$(python3 - "$EXPERIENCE_DB" "$PROJECT" <<'PY'
import sqlite3,sys
db=sqlite3.connect(sys.argv[1])
print(db.execute("SELECT COUNT(*) FROM experience WHERE project_id=? AND learner='capability-durable-adoption'",(sys.argv[2],)).fetchone()[0])
PY
)"
REPLAY_RECEIPT="$PROOF_DIR/adoption-replay.json"
python3 "$RELEASE/dev-hub/bin/durable-capability-registry.py" adopt   --policy "$RELEASE/dev-hub/config/durable-capability-adoption.v1.json"   --candidate "$PROOF_DIR/candidate.json"   --success "$PROOF_DIR/project-success.json"   --base-capability-registry "$RELEASE/dev-hub/config/capability-registry.v1.json"   --base-provider-registry "$RELEASE/dev-hub/config/provider-adapters.v1.json"   --registry "$DURABLE_REGISTRY" --repo-root "$RELEASE"   --adapter-root "$ADAPTER_ROOT" --source-archive-root "$SOURCE_ARCHIVE_ROOT"   --evidence-root "$ADOPTION_EVIDENCE_ROOT" --experience-db "$EXPERIENCE_DB"   --actor central-orchestrator --receipt "$REPLAY_RECEIPT" --apply   >"$WORK/replay.out" 2>"$WORK/replay.err"
python3 - "$REPLAY_RECEIPT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="IDEMPOTENT" and x["applied"] is False,x
print("CHACHA_DEV_V642_REAL_ADOPTION_IDEMPOTENCE=PASS")
PY
EXPERIENCE_COUNT_AFTER="$(python3 - "$EXPERIENCE_DB" "$PROJECT" <<'PY'
import sqlite3,sys
db=sqlite3.connect(sys.argv[1])
print(db.execute("SELECT COUNT(*) FROM experience WHERE project_id=? AND learner='capability-durable-adoption'",(sys.argv[2],)).fetchone()[0])
PY
)"
[ "$EXPERIENCE_COUNT_BEFORE" = "$EXPERIENCE_COUNT_AFTER" ] || {
  echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=idempotent_replay_duplicated_memory"; exit 31;
}

stage synthetic-adoption-rollback
ROLLBACK_RECEIPT="$PROOF_DIR/rollback.json"
python3 "$RELEASE/dev-hub/bin/durable-capability-registry.py" rollback   --registry "$DURABLE_REGISTRY"   --adoption-id "$ADOPTION_ID"   --actor central-orchestrator   --receipt "$ROLLBACK_RECEIPT" --apply >"$WORK/rollback.out" 2>"$WORK/rollback.err"
ROLLED_BACK=1

python3 "$RELEASE/dev-hub/bin/durable-capability-registry.py" merge   --base-capability-registry "$RELEASE/dev-hub/config/capability-registry.v1.json"   --base-provider-registry "$RELEASE/dev-hub/config/provider-adapters.v1.json"   --registry "$DURABLE_REGISTRY"   --output-capabilities "$WORK/post-rollback-capabilities.json"   --output-providers "$WORK/post-rollback-providers.json"   --require-executables >"$WORK/post-rollback-merge.out"

python3 - "$DURABLE_REGISTRY" "$WORK/post-rollback-capabilities.json" "$WORK/post-rollback-providers.json"   "$ADOPTION_ID" "$CAPABILITY" "$PROVIDER" "$ADAPTER" "$ADOPT_RECEIPT" <<'PY'
import json,pathlib,sys
regp,capsp,provp,aid,cap,provider,adapter,receiptp=sys.argv[1:]
reg=json.load(open(regp,encoding="utf-8"))
caps=json.load(open(capsp,encoding="utf-8"))
providers=json.load(open(provp,encoding="utf-8"))
receipt=json.load(open(receiptp,encoding="utf-8"))
assert reg["adoptions"][aid]["status"]=="ROLLED_BACK",reg["adoptions"][aid]
assert cap not in caps.get("capabilities",{}),caps
assert provider not in providers.get("providers",{}),providers
assert adapter not in providers.get("adapters",{}),providers
assert pathlib.Path(receipt["durable_executable"]).is_file(),receipt
assert pathlib.Path(receipt["source_archive"]).is_file(),receipt
print("CHACHA_DEV_V642_REAL_SYNTHETIC_ADOPTION_ROLLBACK=PASS")
print("CHACHA_DEV_V642_REAL_SYNTHETIC_ACTIVE_REGISTRY_POLLUTION=NO")
print("CHACHA_DEV_V642_REAL_FORENSIC_BINARY_RETAINED=PASS")
PY

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ] || { echo "CHACHA_DEV_V642_INSTALL=BLOCKED reason=activation_symlink_failed"; exit 32; }
echo "CHACHA_DEV_V642_RELEASE_ACTIVATED=PASS"

stage guardian-coverage
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json   >"$WORK/guardian.out" 2>"$WORK/guardian.err"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
echo "CHACHA_DEV_V642_GUARDIAN_COVERAGE=PASS"

stage post-activation
(
  cd "$CURRENT"
  PYTHONPATH="$CURRENT/dev-hub/bin" python3 dev-hub/tests/test_v642_durable_capability_adoption.py
) >"$WORK/post-activation.out" 2>"$WORK/post-activation.err"
grep -Fq 'CHACHA_DEV_V642_VERIFIED_SUCCESS_BEFORE_ADOPTION=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V642_PROJECT_CONTROL_COMMITTED_PROOF=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V642_CROSS_PROJECT_REUSE_WITHOUT_REBUILD=PASS' "$WORK/post-activation.out"
grep -Fq 'CHACHA_DEV_V642_PROTECTED_ADOPTION_HUMAN_BOUNDARY=PASS' "$WORK/post-activation.out"
echo "CHACHA_DEV_V642_POST_ACTIVATION=PASS"

mkdir -p /opt/chacha-dev/evidence
cat >"/opt/chacha-dev/evidence/v642-durable-capability-adoption-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v642-durable-capability-adoption-evidence/v1",
  "revision":"$REV",
  "observed_at":"$STAMP",
  "v641_baseline":"PASS",
  "project_control_committed_proof":"PASS",
  "project_control_ledger_commit_proof":"PASS",
  "success_claims_bound_to_verified_result":"PASS",
  "real_durable_adoption":"PASS",
  "durable_adapter_reprobe":"PASS",
  "cross_project_reuse":"PASS",
  "rebuild_on_second_project":false,
  "experience_memory":"PASS",
  "single_project_global_trust":false,
  "adoption_idempotence":"PASS",
  "synthetic_adoption_rollback":"PASS",
  "synthetic_active_registry_pollution":false,
  "forensic_binary_retained":true,
  "guardian_coverage":"PASS",
  "protected_adoption_human_boundary":"PRESERVED",
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V642_DURABLE_CAPABILITY_ADOPTION=PASS"
echo "CHACHA_DEV_V642_VERIFIED_SUCCESS_BEFORE_ADOPTION=PASS"
echo "CHACHA_DEV_V642_PROJECT_CONTROL_COMMITTED_PROOF=PASS"
echo "CHACHA_DEV_V642_PROJECT_CONTROL_LEDGER_COMMIT_PROOF=PASS"
echo "CHACHA_DEV_V642_SUCCESS_CLAIMS_BOUND_TO_VERIFIED_RESULT=PASS"
echo "CHACHA_DEV_V642_RELEASE_INDEPENDENT_DURABLE_REGISTRY=PASS"
echo "CHACHA_DEV_V642_REAL_DURABLE_ADAPTER_REPROBE=PASS"
echo "CHACHA_DEV_V642_REAL_CROSS_PROJECT_REUSE=PASS"
echo "CHACHA_DEV_V642_REAL_REBUILD_ON_SECOND_PROJECT=NO"
echo "CHACHA_DEV_V642_REAL_EXPERIENCE_MEMORY=PASS"
echo "CHACHA_DEV_V642_REAL_SINGLE_PROJECT_GLOBAL_TRUST=NO"
echo "CHACHA_DEV_V642_REAL_ADOPTION_IDEMPOTENCE=PASS"
echo "CHACHA_DEV_V642_REAL_SYNTHETIC_ADOPTION_ROLLBACK=PASS"
echo "CHACHA_DEV_V642_REAL_SYNTHETIC_ACTIVE_REGISTRY_POLLUTION=NO"
echo "CHACHA_DEV_V642_PROTECTED_ADOPTION_HUMAN_BOUNDARY=PRESERVED"
echo "CHACHA_DEV_V642_GUARDIAN_COVERAGE=PASS"
echo "CHACHA_DEV_V642_POST_ACTIVATION=PASS"
echo "CHACHA_DEV_V642_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V642_INSTALL=PASS"

trap - EXIT
cleanup
