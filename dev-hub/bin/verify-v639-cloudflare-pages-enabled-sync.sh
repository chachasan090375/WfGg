#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V639_REV:-}"
REPO="chachasan090375/WfGg"
WORK="/tmp/chacha-dev-v639-enabled-sync-$(date -u +%Y%m%dT%H%M%SZ)"
LIVE_REGISTRY="/opt/chacha-dev/platform/current/dev-hub/config/provider-adapters.v1.json"
RUNTIME_POLICY="/opt/chacha-dev/runtime/adapter-policies/cloudflare-pages-production-adapter.v1.json"
EXE="/opt/chacha-dev/adapters/cloudflare-pages-production/current/cloudflare-pages-production-adapter"

cleanup(){ rm -rf -- "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "CHACHA_DEV_V639_ENABLED_SYNC=BLOCKED reason=pinned_revision_required"
  exit 2
}

for cmd in curl tar python3 sha256sum; do
  command -v "$cmd" >/dev/null || {
    echo "CHACHA_DEV_V639_ENABLED_SYNC=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$WORK/src" "$WORK/build"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REV" -o "$WORK/source.tar.gz"
tar -xzf "$WORK/source.tar.gz" -C "$WORK/src" --strip-components=1
SRC="$WORK/src"

echo "CHACHA_DEV_V639_SYNC_STAGE=repo-runtime-state"
python3 - \
  "$SRC/dev-hub/config/provider-adapters.v1.json" \
  "$SRC/dev-hub/evidence/v639/cloudflare-pages-production-enabled-promotion-receipt.json" \
  "$LIVE_REGISTRY" "$EXE" <<'PY'
import hashlib,json,pathlib,sys
source=json.load(open(sys.argv[1],encoding="utf-8"))
receipt=json.load(open(sys.argv[2],encoding="utf-8"))
live=json.load(open(sys.argv[3],encoding="utf-8"))
exe=pathlib.Path(sys.argv[4])
for label,r in (("source",source),("live",live)):
    a=r["adapters"]["cloudflare-pages-production-adapter"]
    p=r["providers"]["cloudflare-pages-production"]
    assert a["status"]=="ENABLED",(label,a)
    assert a["executable"]==str(exe),(label,a)
    assert p["adapter"]=="cloudflare-pages-production-adapter",(label,p)
    assert p["execution"]=="vps",(label,p)
assert receipt["transition"]=="PILOT->ENABLED",receipt
assert receipt["status"]=="COMMITTED",receipt
assert receipt["applied"] is True,receipt
assert receipt["approval_scope"]=="ENABLE_ADAPTER_ONLY_NO_REAL_PRODUCTION_DEPLOYMENT",receipt
assert receipt["production_execution_enabled"] is False,receipt
assert receipt["real_production_deployment_authorized"] is False,receipt
assert receipt["runtime_idempotent_second_run"] is True,receipt
assert exe.is_file() and exe.stat().st_mode & 0o111,exe
digest="sha256:"+hashlib.sha256(exe.read_bytes()).hexdigest()
assert digest==receipt["executable_digest"],(digest,receipt["executable_digest"])
print("CHACHA_DEV_V639_CF_PAGES_REPO_ENABLED=PASS")
print("CHACHA_DEV_V639_CF_PAGES_LIVE_ENABLED=PASS")
print("CHACHA_DEV_V639_CF_PAGES_ENABLED_DIGEST_BINDING=PASS")
print("CHACHA_DEV_V639_CF_PAGES_ENABLEMENT_IDEMPOTENCE=PASS")
PY

[ -f "$RUNTIME_POLICY" ] || {
  echo "CHACHA_DEV_V639_ENABLED_SYNC=FAILED reason=runtime_policy_missing"
  exit 20
}

unset CHACHA_CF_PAGES_PROD_POLICY || true
unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION || true
unset CLOUDFLARE_API_TOKEN || true
unset CLOUDFLARE_ACCOUNT_ID || true
export CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS="v639-enabled-sync-test"
printf '%s\n' '<!doctype html><title>V6.39 enabled sync</title>' > "$WORK/build/index.html"

echo "CHACHA_DEV_V639_SYNC_STAGE=post-enable-runtime-guard"
python3 - "$EXE" "$WORK" <<'PY'
import json,os,pathlib,subprocess,sys
exe=sys.argv[1]; root=pathlib.Path(sys.argv[2]); build=root/"build"
env=os.environ.copy()
for k in ("CHACHA_CF_PAGES_PROD_POLICY","CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION",
          "CLOUDFLARE_API_TOKEN","CLOUDFLARE_ACCOUNT_ID"):
    env.pop(k,None)
env["CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS"]="v639-enabled-sync-test"

def run(v):
    p=subprocess.run([exe],input=json.dumps(v),text=True,stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,env=env,check=False,timeout=30)
    return p.returncode,json.loads(p.stdout)

base={
 "schema":"chacha.dev/dispatch-envelope/v1","project":"v639-enabled-sync-test",
 "transition":"RELEASE->OPERATE","run_id":"v639-enabled-sync","wave":1,
 "task":{"id":"contract","permission":"read"},
 "bindings":[{"capability":"cloud-deploy-static","provider":"cloudflare-pages-production",
              "adapter":"cloudflare-pages-production-adapter","fallback_used":False,"health_state":"HEALTHY"}],
 "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                   "human_approval_required":False,"approval_id":None,"timeout_seconds":20},
 "workspace":str(root),"metadata":{"cloudflare_pages_production":{"action":"contract-status"}}
}
rc,o=run(base)
assert rc==0 and o["status"]=="OK",o

d=json.loads(json.dumps(base))
d["task"]={"id":"deploy","permission":"production-deploy"}
d["policy_context"]={"resource_class":"light","requires_storage_preflight":False,
                     "human_approval_required":True,"approval_id":"production-deployment","timeout_seconds":20}
d["metadata"]["cloudflare_pages_production"]={
 "action":"production-deploy","project_name":"v639-enabled-sync-test",
 "production_branch":"main","revision":"c"*40,
 "build_directory":str(build.resolve()),
 "approval_receipt":str(root/"missing-production-approval.json")
}
rc,o=run(d)
assert rc==2 and o["status"]=="BLOCKED",o
assert o["summary"]=="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",o

print("CHACHA_DEV_V639_CF_PAGES_POST_ENABLE_RUNTIME=PASS")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO")
print("CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_TARGET=NO")
print("CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_DEPLOYMENT_AUTHORIZED=NO")
PY

echo "CHACHA_DEV_V639_SYNC_STAGE=exact-head-ci"
API="https://api.github.com/repos/$REPO/actions/runs?head_sha=$REV&per_page=100"
READY=0
for i in $(seq 1 80); do
  curl -fsS -H "Accept: application/vnd.github+json" -H "User-Agent: ChaCha-DEV-V639" "$API" -o "$WORK/actions.json"
  set +e
  python3 - "$WORK/actions.json" "$REV" <<'PY'
import json,sys
runs=json.load(open(sys.argv[1],encoding="utf-8")).get("workflow_runs") or []
rev=sys.argv[2]
name="ChaCha DEV V6.39 controlled production handoff qualification"
x=[r for r in runs if r.get("name")==name and r.get("head_sha")==rev]
if not x: raise SystemExit(2)
x.sort(key=lambda r:r.get("run_number",0),reverse=True)
r=x[0]
if r.get("status")!="completed": raise SystemExit(2)
if r.get("conclusion")!="success":
    print("CHACHA_DEV_V639_EXACT_HEAD_CI=FAILED")
    raise SystemExit(10)
print("CHACHA_DEV_V639_EXACT_HEAD_CI=PASS")
PY
  RC=$?
  set -e
  if [ "$RC" -eq 0 ]; then READY=1; break; fi
  [ "$RC" -eq 2 ] || exit "$RC"
  sleep 15
done
[ "$READY" -eq 1 ] || {
  echo "CHACHA_DEV_V639_EXACT_HEAD_CI=TIMEOUT"
  exit 11
}

echo "CHACHA_DEV_V639_CF_PAGES_ENABLED_SYNC=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_ADAPTER_STATE=ENABLED"
echo "CHACHA_DEV_V639_REAL_PRODUCTION_DEPLOYMENT_AUTHORIZED=NO"
echo "CHACHA_DEV_V639_RELEASE_TO_OPERATE_REAL_PILOT=PENDING_HUMAN_APPROVAL"
echo "CHACHA_DEV_V639_INSTALL=NOT_YET_REAL_PRODUCTION_REQUIRED"
