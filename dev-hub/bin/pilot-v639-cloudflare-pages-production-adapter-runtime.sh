#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V639_REV:-}"
REPO="chachasan090375/WfGg"
ADAPTER="cloudflare-pages-production-adapter"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/chacha-dev-v639-cf-pages-runtime-$STAMP"
RUNTIME_ROOT="/opt/chacha-dev/runtime"
PROVISION_ROOT="/opt/chacha-dev/adapters"
RECEIPT_DIR="$RUNTIME_ROOT/adapter-provisioning"
PROMOTION_DIR="$RUNTIME_ROOT/adapter-promotions"
RECEIPT="$RECEIPT_DIR/${ADAPTER}-v1.0.0-${REV}.json"
EVIDENCE="$PROMOTION_DIR/${ADAPTER}-contract-ok-to-pilot-${REV}.evidence.json"
PLAN="$PROMOTION_DIR/${ADAPTER}-contract-ok-to-pilot-${REV}.plan.json"

cleanup(){ rm -rf -- "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || {
  echo "CHACHA_DEV_V639_CF_PAGES_RUNTIME_PILOT=BLOCKED reason=root_required"
  exit 2
}

printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "CHACHA_DEV_V639_CF_PAGES_RUNTIME_PILOT=BLOCKED reason=pinned_revision_required"
  exit 2
}

for cmd in curl tar python3 grep; do
  command -v "$cmd" >/dev/null || {
    echo "CHACHA_DEV_V639_CF_PAGES_RUNTIME_PILOT=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$WORK/src" "$RECEIPT_DIR" "$PROMOTION_DIR"
echo "CHACHA_DEV_V639_CF_PAGES_STAGE=fetch-pinned-source"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REV" -o "$WORK/source.tar.gz"
tar -xzf "$WORK/source.tar.gz" -C "$WORK/src" --strip-components=1
SRC="$WORK/src"

echo "CHACHA_DEV_V639_CF_PAGES_STAGE=preflight"
python3 - "$SRC/dev-hub/config/provider-adapters.v1.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
e=r["adapters"]["cloudflare-pages-production-adapter"]
assert e["status"]=="CONTRACT_OK",e
assert e["executable"] is None,e
p=r["providers"]["cloudflare-pages-production"]
assert p["adapter"]=="cloudflare-pages-production-adapter",p
assert p["execution"]=="vps",p
print("CHACHA_DEV_V639_CF_PAGES_CONTRACT_OK=PASS")
PY

python3 -m py_compile \
  "$SRC/dev-hub/adapters/cloudflare-pages-production-adapter.py" \
  "$SRC/dev-hub/bin/adapter-provision.py" \
  "$SRC/dev-hub/bin/adapter-promotion.py"

for f in \
  "$SRC/dev-hub/config/provider-adapters.v1.json" \
  "$SRC/dev-hub/config/adapter-contract.v1.json" \
  "$SRC/dev-hub/config/adapter-promotion.v1.json" \
  "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  "$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json"; do
  python3 -m json.tool "$f" >/dev/null
done

unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION || true
unset CLOUDFLARE_API_TOKEN || true
unset CLOUDFLARE_ACCOUNT_ID || true
export CHACHA_CF_PAGES_PROD_POLICY="$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json"
export CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS="v639-runtime-contract-test"

echo "CHACHA_DEV_V639_CF_PAGES_STAGE=real-vps-provisioning"
python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  plan --adapter "$ADAPTER" \
  > "$WORK/provisioning-plan.json"

python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  apply \
  --adapter "$ADAPTER" \
  --actor v639-runtime-pilot \
  --receipt "$RECEIPT" \
  --apply \
  | tee "$WORK/provisioning.out"

python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  verify \
  --adapter "$ADAPTER" \
  --receipt "$RECEIPT" \
  | tee "$WORK/provisioning-verify.out"

grep -Fq "PROVISIONING_VERIFY=PASS" "$WORK/provisioning-verify.out"

EXE="$(python3 - "$RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
assert r["schema"]=="chacha.dev/adapter-provisioning-receipt/v1",r
assert r["adapter"]=="cloudflare-pages-production-adapter",r
assert r["applied"] is True,r
assert r["probe"]["status"]=="PASS",r
assert r["source_digest"]==r["installed_digest"]==r["executable_digest"],r
print(r["executable_path"])
PY
)"

[ -x "$EXE" ] || {
  echo "CHACHA_DEV_V639_CF_PAGES_RUNTIME_PILOT=FAILED reason=provisioned_executable_missing"
  exit 20
}

echo "CHACHA_DEV_V639_CF_PAGES_REAL_VPS_PROVISIONING=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_PROVISIONING_VERIFY=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_PROVISIONING_DIGEST_CHAIN=PASS"

echo "CHACHA_DEV_V639_CF_PAGES_STAGE=runtime-contract"
mkdir -p "$WORK/build"
printf '%s\n' '<!doctype html><title>V6.39 runtime contract</title>' > "$WORK/build/index.html"

python3 - "$EXE" "$WORK" <<'PY'
import json,os,pathlib,subprocess,sys
exe=sys.argv[1]
root=pathlib.Path(sys.argv[2])
env=os.environ.copy()
env.pop("CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION",None)
env.pop("CLOUDFLARE_API_TOKEN",None)
env.pop("CLOUDFLARE_ACCOUNT_ID",None)

def run(payload):
    p=subprocess.run([exe],input=json.dumps(payload),text=True,
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     env=env,check=False,timeout=30)
    try: out=json.loads(p.stdout)
    except Exception as e: raise SystemExit("ADAPTER_OUTPUT_INVALID:"+p.stdout[-1000:]+p.stderr[-1000:]) from e
    return p.returncode,out

base={
 "schema":"chacha.dev/dispatch-envelope/v1",
 "project":"v639-runtime-contract-test",
 "transition":"RELEASE->OPERATE",
 "run_id":"v639-runtime-contract",
 "wave":1,
 "task":{"id":"contract-status","permission":"read"},
 "bindings":[{
   "capability":"cloud-deploy-static",
   "provider":"cloudflare-pages-production",
   "adapter":"cloudflare-pages-production-adapter",
   "fallback_used":False,
   "health_state":"UNKNOWN"
 }],
 "policy_context":{
   "resource_class":"light","requires_storage_preflight":False,
   "human_approval_required":False,"approval_id":None,"timeout_seconds":20
 },
 "workspace":str(root),
 "metadata":{"cloudflare_pages_production":{"action":"contract-status"}}
}
rc,out=run(base)
assert rc==0 and out["status"]=="OK",out
assert out["producer"]=="cloudflare-pages-production-adapter",out

plan=json.loads(json.dumps(base))
plan["task"]={"id":"deployment-plan","permission":"read"}
plan["metadata"]["cloudflare_pages_production"]={
 "action":"deployment-plan",
 "project_name":"v639-runtime-contract-test",
 "production_branch":"main",
 "revision":"e"*40,
 "build_directory":str((root/"build").resolve())
}
rc,out=run(plan)
assert rc==0 and out["status"]=="OK",out
d=out["evidence"][0]["details"]
assert d["production_mutation"] is False,d
assert d["execution_switch_enabled"] is False,d
assert d["rollback_capture_required"] is True,d

deploy=json.loads(json.dumps(plan))
deploy["task"]={"id":"production-deploy","permission":"production-deploy"}
deploy["policy_context"]={
 "resource_class":"light","requires_storage_preflight":False,
 "human_approval_required":True,"approval_id":"production-deployment","timeout_seconds":20
}
deploy["metadata"]["cloudflare_pages_production"]["action"]="production-deploy"
deploy["metadata"]["cloudflare_pages_production"]["approval_receipt"]=str(root/"missing-approval.json")
rc,out=run(deploy)
assert rc==2 and out["status"]=="BLOCKED",out
assert out["summary"]=="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",out

rollback=json.loads(json.dumps(deploy))
rollback["task"]={"id":"production-rollback","permission":"production-deploy"}
rollback["metadata"]["cloudflare_pages_production"]["action"]="production-rollback"
rollback["metadata"]["cloudflare_pages_production"]["previous_deployment_id"]="not-used"
rc,out=run(rollback)
assert rc==2 and out["status"]=="BLOCKED",out
assert out["summary"]=="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",out

print("CHACHA_DEV_V639_CF_PAGES_RUNTIME_CONTRACT=PASS")
print("CHACHA_DEV_V639_CF_PAGES_RUNTIME_SANDBOX_ONLY=PASS")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED")
print("CHACHA_DEV_V639_CF_PAGES_NETWORK_WRITE=NO")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO")
print("CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_TARGET=NO")
PY

echo "CHACHA_DEV_V639_CF_PAGES_STAGE=pilot-promotion-evidence"
python3 - "$RECEIPT" "$EVIDENCE" "$REV" <<'PY'
import datetime,json,sys,pathlib
receipt_path=pathlib.Path(sys.argv[1])
out=pathlib.Path(sys.argv[2])
rev=sys.argv[3]
r=json.load(open(receipt_path,encoding="utf-8"))
ts=datetime.datetime.now(datetime.timezone.utc).isoformat()
e={
 "schema":"chacha.dev/adapter-promotion-evidence/v1",
 "adapter":"cloudflare-pages-production-adapter",
 "observed_at":ts,
 "evidence":{
   "runtime-contract-pass":{
     "status":"PASS",
     "source":"vps://ChaChaVPS/v639/cloudflare-pages-production/runtime-contract",
     "observed_at":ts,
     "details":{
       "source_revision":rev,
       "production_execution":"BLOCKED",
       "network_write":False,
       "production_mutation":False,
       "real_production_target":False
     }
   },
   "sandbox-only":{
     "status":"PASS",
     "source":"vps://ChaChaVPS/v639/cloudflare-pages-production/sandbox-only",
     "observed_at":ts,
     "details":{
       "production_execution_switch":False,
       "cloudflare_credentials_loaded":False,
       "network_write":False,
       "production_mutation":False,
       "real_production_target":False
     }
   },
   "provisioning-pass":{
     "status":"PASS",
     "source":str(receipt_path),
     "observed_at":ts,
     "details":{
       "provisioning_receipt":str(receipt_path),
       "executable_path":r["executable_path"],
       "executable_digest":r["executable_digest"],
       "source_digest":r["source_digest"],
       "installed_digest":r["installed_digest"],
       "probe_status":r["probe"]["status"]
     }
   }
 },
 "approvals":[]
}
out.write_text(json.dumps(e,indent=2)+"\n",encoding="utf-8")
PY

echo "CHACHA_DEV_V639_CF_PAGES_STAGE=pilot-promotion-plan"
python3 "$SRC/dev-hub/bin/adapter-promotion.py" \
  --registry "$SRC/dev-hub/config/provider-adapters.v1.json" \
  --contract "$SRC/dev-hub/config/adapter-contract.v1.json" \
  --policy "$SRC/dev-hub/config/adapter-promotion.v1.json" \
  --evidence "$EVIDENCE" \
  --report "$PLAN" \
  --json \
  plan \
  --adapter "$ADAPTER" \
  --target PILOT \
  --executable "$EXE" \
  > "$WORK/pilot-promotion-plan.out"

python3 - "$WORK/pilot-promotion-plan.out" "$SRC/dev-hub/config/provider-adapters.v1.json" "$EXE" <<'PY'
import json,sys
plan=json.load(open(sys.argv[1],encoding="utf-8"))
registry=json.load(open(sys.argv[2],encoding="utf-8"))
exe=sys.argv[3]
assert plan["adapter"]=="cloudflare-pages-production-adapter",plan
assert plan["current_status"]=="CONTRACT_OK",plan
assert plan["target_status"]=="PILOT",plan
assert plan["eligible"] is True,plan
assert plan["applied"] is False,plan
assert plan["approval_required"] is False,plan
assert plan["executable_after"]==exe,plan
assert plan["provisioned_executable_digest"].startswith("sha256:"),plan
entry=registry["adapters"]["cloudflare-pages-production-adapter"]
assert entry["status"]=="CONTRACT_OK",entry
assert entry["executable"] is None,entry
print("CHACHA_DEV_V639_CF_PAGES_PILOT_ELIGIBLE=PASS")
print("CHACHA_DEV_V639_CF_PAGES_REGISTRY_MUTATION=NO")
PY

echo "CHACHA_DEV_V639_PLATFORM_CURRENT_MUTATION=NO"
echo "CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED"
echo "CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO"
echo "CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_TARGET=NO"
echo "CHACHA_DEV_V639_OPERATE_ADVANCED=NO"
echo "CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V639_CF_PAGES_RUNTIME_PILOT=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_EXECUTABLE=$EXE"
echo "CHACHA_DEV_V639_CF_PAGES_PROVISIONING_RECEIPT=$RECEIPT"
echo "CHACHA_DEV_V639_CF_PAGES_PROMOTION_EVIDENCE=$EVIDENCE"
echo "CHACHA_DEV_V639_CF_PAGES_PROMOTION_PLAN=$PLAN"
