#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V639_REV:-}"
APPROVAL_ID="${CHACHA_DEV_V639_ENABLEMENT_APPROVAL_ID:-}"
HUMAN_ACTOR="${CHACHA_DEV_V639_HUMAN_ACTOR:-}"
REPO="chachasan090375/WfGg"
ADAPTER="cloudflare-pages-production-adapter"
PROVIDER="cloudflare-pages-production"
LIVE_REGISTRY="/opt/chacha-dev/platform/current/dev-hub/config/provider-adapters.v1.json"
RUNTIME_POLICY_DIR="/opt/chacha-dev/runtime/adapter-policies"
RUNTIME_POLICY="$RUNTIME_POLICY_DIR/cloudflare-pages-production-adapter.v1.json"
PROVISION_ROOT="/opt/chacha-dev/adapters"
PROMOTION_ROOT="/opt/chacha-dev/runtime/adapter-promotions"
PROVISION_RECEIPT_ROOT="/opt/chacha-dev/runtime/adapter-provisioning"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/chacha-dev-v639-cf-pages-enable-$STAMP"
EVIDENCE="$PROMOTION_ROOT/${ADAPTER}-pilot-to-enabled-${REV}.evidence.json"
PROMOTION_RECEIPT="$PROMOTION_ROOT/${ADAPTER}-pilot-to-enabled-${REV}.receipt.json"
PROMOTION_REPORT="$PROMOTION_ROOT/${ADAPTER}-pilot-to-enabled-${REV}.report.json"
PROVISION_RECEIPT="$PROVISION_RECEIPT_ROOT/${ADAPTER}-v1.0.1-${REV}.json"
BACKUP="$PROMOTION_ROOT/provider-adapters.pre-v639-enable-${STAMP}.json"

cleanup(){ rm -rf -- "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

fail(){ echo "CHACHA_DEV_V639_CF_PAGES_ENABLEMENT=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || fail root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || fail pinned_revision_required
[ -n "$APPROVAL_ID" ] || fail explicit_enablement_approval_id_required
[ -n "$HUMAN_ACTOR" ] || fail human_actor_required
case "$HUMAN_ACTOR" in
  central-orchestrator|guardian|sentinel|curator|bastion|intendant|logician|ergonomist)
    fail human_actor_cannot_be_agent ;;
esac

for cmd in curl tar python3 grep sha256sum; do
  command -v "$cmd" >/dev/null || fail "missing_command:$cmd"
done

mkdir -p "$WORK/src" "$RUNTIME_POLICY_DIR" "$PROMOTION_ROOT" "$PROVISION_RECEIPT_ROOT"
echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=fetch-pinned-source"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REV" -o "$WORK/source.tar.gz"
tar -xzf "$WORK/source.tar.gz" -C "$WORK/src" --strip-components=1
SRC="$WORK/src"

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=source-preflight"
python3 - "$SRC/dev-hub/config/provider-adapters.v1.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
p=r["providers"]["cloudflare-pages-production"]
a=r["adapters"]["cloudflare-pages-production-adapter"]
assert p["adapter"]=="cloudflare-pages-production-adapter",p
assert p["execution"]=="vps",p
assert a["status"]=="PILOT",a
assert a["executable"]=="/opt/chacha-dev/adapters/cloudflare-pages-production/current/cloudflare-pages-production-adapter",a
assert "production-deploy" in a["supports"],a
print("CHACHA_DEV_V639_CF_PAGES_SOURCE_PILOT=PASS")
PY

python3 -m py_compile \
  "$SRC/dev-hub/adapters/cloudflare-pages-production-adapter.py" \
  "$SRC/dev-hub/bin/adapter-provision.py" \
  "$SRC/dev-hub/bin/adapter-promotion.py" \
  "$SRC/dev-hub/bin/qualify-cloudflare-pages-provider-health.py"

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=runtime-policy"
python3 - "$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json" "$RUNTIME_POLICY" <<'PY'
import json,os,pathlib,sys,tempfile
src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2])
x=json.load(open(src,encoding="utf-8"))
assert x["schema"]=="chacha.dev/cloudflare-pages-production-adapter/v1",x
assert x["mutation_guard"]["required_value"]=="ENABLED",x
assert x["mutation_guard"]["protected_approval_id"]=="production-deployment",x
assert x["qualification"]["real_production_execution"] is False,x
dst.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix=dst.name+".",dir=str(dst.parent))
try:
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(x,f,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o644); os.replace(tmp,dst)
    dfd=os.open(str(dst.parent),os.O_DIRECTORY); os.fsync(dfd); os.close(dfd)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
print("CHACHA_DEV_V639_CF_PAGES_RUNTIME_POLICY=PASS")
PY

unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION || true
unset CLOUDFLARE_API_TOKEN || true
unset CLOUDFLARE_ACCOUNT_ID || true
export CHACHA_CF_PAGES_PROD_POLICY="$RUNTIME_POLICY"
export CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS="v639-enablement-guard-test"

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=provision-1.0.1"
python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  apply --adapter "$ADAPTER" --actor "$HUMAN_ACTOR" \
  --receipt "$PROVISION_RECEIPT" --apply \
  | tee "$WORK/provision.out"

python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  verify --adapter "$ADAPTER" --receipt "$PROVISION_RECEIPT" \
  | tee "$WORK/provision-verify.out"
grep -Fq "PROVISIONING_VERIFY=PASS" "$WORK/provision-verify.out"

EXE="$(python3 - "$PROVISION_RECEIPT" <<'PY'
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
[ -x "$EXE" ] || fail provisioned_executable_missing
echo "CHACHA_DEV_V639_CF_PAGES_PROVISION_1_0_1=PASS"

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=runtime-readiness-evidence"
mkdir -p "$WORK/build"
printf '%s\n' '<!doctype html><title>V6.39 enablement guard</title>' > "$WORK/build/index.html"

python3 - "$EXE" "$WORK" <<'PY'
import json,os,pathlib,subprocess,sys
exe=sys.argv[1]; root=pathlib.Path(sys.argv[2])
env=os.environ.copy()
for k in ("CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION","CLOUDFLARE_API_TOKEN","CLOUDFLARE_ACCOUNT_ID"):
    env.pop(k,None)

def run(payload):
    p=subprocess.run([exe],input=json.dumps(payload),text=True,stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,env=env,check=False,timeout=30)
    try:o=json.loads(p.stdout)
    except Exception as e: raise SystemExit("ADAPTER_OUTPUT_INVALID:"+p.stdout[-1000:]+p.stderr[-1000:]) from e
    return p.returncode,o

def base(i):
    return {
      "schema":"chacha.dev/dispatch-envelope/v1","project":"v639-enablement-guard-test",
      "transition":"RELEASE->OPERATE","run_id":f"v639-enable-{i}","wave":1,
      "task":{"id":f"contract-{i}","permission":"read"},
      "bindings":[{"capability":"cloud-deploy-static","provider":"cloudflare-pages-production",
                   "adapter":"cloudflare-pages-production-adapter","fallback_used":False,"health_state":"HEALTHY"}],
      "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                        "human_approval_required":False,"approval_id":None,"timeout_seconds":20},
      "workspace":str(root),"metadata":{"cloudflare_pages_production":{"action":"contract-status"}}
    }

for i in range(1,4):
    b=base(i); rc,o=run(b); assert rc==0 and o["status"]=="OK",o
    p=json.loads(json.dumps(b))
    p["task"]={"id":f"plan-{i}","permission":"read"}
    p["metadata"]["cloudflare_pages_production"]={
      "action":"deployment-plan","project_name":"v639-enablement-guard-test",
      "production_branch":"main","revision":"a"*40,"build_directory":str((root/"build").resolve())
    }
    rc,o=run(p); assert rc==0 and o["status"]=="OK",o
    d=o["evidence"][0]["details"]
    assert d["production_mutation"] is False and d["execution_switch_enabled"] is False,d

    deploy=json.loads(json.dumps(p))
    deploy["task"]={"id":f"deploy-{i}","permission":"production-deploy"}
    deploy["policy_context"]={"resource_class":"light","requires_storage_preflight":False,
                              "human_approval_required":True,"approval_id":"production-deployment","timeout_seconds":20}
    deploy["metadata"]["cloudflare_pages_production"]["action"]="production-deploy"
    deploy["metadata"]["cloudflare_pages_production"]["approval_receipt"]=str(root/"missing.json")
    rc,o=run(deploy)
    assert rc==2 and o["status"]=="BLOCKED",o
    assert o["summary"]=="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",o

print("CHACHA_DEV_V639_CF_PAGES_REPEATABLE_RUNTIME=PASS")
print("CHACHA_DEV_V639_CF_PAGES_REPEATABILITY_RUNS=3")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO")
PY

python3 "$SRC/dev-hub/bin/qualify-cloudflare-pages-provider-health.py" \
  --report "$WORK/provider-health.json" --evidence "$WORK/provider-health-evidence.json" \
  | tee "$WORK/provider-health.out"
grep -Fq "CHACHA_DEV_V639_CF_PAGES_PROVIDER_HEALTH=PASS" "$WORK/provider-health.out"

python3 - "$SRC/dev-hub/config/adapter-rollbacks.v1.json" "$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))["adapters"]["cloudflare-pages-production-adapter"]
p=json.load(open(sys.argv[2],encoding="utf-8"))["rollback"]
assert r["enabled"] is True and r["target_status"]=="DISABLED",r
assert p["capture_current_production_before_deploy"] is True,p
assert p["previous_successful_production_deployment_required"] is True,p
assert p["verify_restored_deployment"] is True,p
print("CHACHA_DEV_V639_CF_PAGES_ROLLBACK_DEFINED=PASS")
PY

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=live-registry-candidate"
[ -f "$LIVE_REGISTRY" ] || fail live_provider_registry_missing
cp -a "$LIVE_REGISTRY" "$BACKUP"

python3 - "$LIVE_REGISTRY" "$SRC/dev-hub/config/provider-adapters.v1.json" "$WORK/live-candidate.json" "$EXE" <<'PY'
import json,sys,pathlib
live=json.load(open(sys.argv[1],encoding="utf-8"))
src=json.load(open(sys.argv[2],encoding="utf-8"))
out=pathlib.Path(sys.argv[3]); exe=sys.argv[4]
assert live["schema"]=="chacha.dev/provider-adapters/v1",live
assert src["schema"]==live["schema"],src
sp=src["providers"]["cloudflare-pages-production"]
sa=src["adapters"]["cloudflare-pages-production-adapter"]
assert sa["status"]=="PILOT",sa
assert sa["executable"]==exe,(sa,exe)

lp=live.setdefault("providers",{}).get("cloudflare-pages-production")
la=live.setdefault("adapters",{}).get("cloudflare-pages-production-adapter")
if lp is not None and lp!=sp:
    raise SystemExit("LIVE_PROVIDER_CONFLICT")
if la is not None:
    if la.get("status")=="ENABLED" and la.get("executable")==exe:
        print("ALREADY_ENABLED=YES")
    elif la.get("status")!="PILOT" or la.get("executable")!=exe:
        raise SystemExit("LIVE_ADAPTER_CONFLICT:"+json.dumps(la,separators=(",",":")))
live["providers"]["cloudflare-pages-production"]=sp
live["adapters"]["cloudflare-pages-production-adapter"]=sa
out.write_text(json.dumps(live,indent=2)+"\n",encoding="utf-8")
print("CHACHA_DEV_V639_CF_PAGES_LIVE_REGISTRY_CANDIDATE=PASS")
PY

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=promotion-evidence"
python3 - "$WORK/provider-health-evidence.json" "$EVIDENCE" "$APPROVAL_ID" "$HUMAN_ACTOR" "$REV" <<'PY'
import datetime,json,sys
provider_path,out,approval_id,actor,rev=sys.argv[1:]
provider=json.load(open(provider_path,encoding="utf-8"))
ts=datetime.datetime.now(datetime.timezone.utc).isoformat()
e={
 "schema":"chacha.dev/adapter-promotion-evidence/v1",
 "adapter":"cloudflare-pages-production-adapter",
 "observed_at":ts,
 "evidence":{
   "repeatable-pass":{"status":"PASS","source":"vps://ChaChaVPS/v639/cloudflare-pages-production/enablement-3x",
                      "observed_at":ts,"details":{"runs":3,"production_execution":"BLOCKED","production_mutation":False}},
   "provider-health-pass":provider["evidence"]["provider-health-pass"],
   "rollback-defined":{"status":"PASS","source":"repo://dev-hub/config/adapter-rollbacks.v1.json",
                       "observed_at":ts,"details":{"target_status":"DISABLED","provider_rollback_api":True}}
 },
 "approvals":[{
   "id":approval_id,"type":"adapter-production-enable",
   "adapter":"cloudflare-pages-production-adapter","target_status":"ENABLED",
   "actor":actor,"approved_at":ts,
   "scope":"ENABLE_ADAPTER_ONLY_NO_REAL_PRODUCTION_DEPLOYMENT",
   "source_revision":rev
 }]
}
json.dump(e,open(out,"w",encoding="utf-8"),indent=2)
PY

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=promotion-apply"
python3 "$SRC/dev-hub/bin/adapter-promotion.py" \
  --registry "$WORK/live-candidate.json" \
  --contract "$SRC/dev-hub/config/adapter-contract.v1.json" \
  --policy "$SRC/dev-hub/config/adapter-promotion.v1.json" \
  --evidence "$EVIDENCE" \
  --report "$PROMOTION_REPORT" --json \
  apply --adapter "$ADAPTER" --target ENABLED --executable "$EXE" \
  --approval-id "$APPROVAL_ID" --actor "$HUMAN_ACTOR" \
  --receipt "$PROMOTION_RECEIPT" --apply \
  > "$WORK/promotion.out"

python3 - "$WORK/promotion.out" "$WORK/live-candidate.json" "$PROMOTION_RECEIPT" <<'PY'
import json,sys
report=json.load(open(sys.argv[1],encoding="utf-8"))
registry=json.load(open(sys.argv[2],encoding="utf-8"))
receipt=json.load(open(sys.argv[3],encoding="utf-8"))
assert report["eligible"] is True and report["applied"] is True,report
assert report["current_status"]=="PILOT" and report["target_status"]=="ENABLED",report
assert report["approval_required"] is True and report["approval_id"],report
a=registry["adapters"]["cloudflare-pages-production-adapter"]
assert a["status"]=="ENABLED",a
assert receipt["receipt_schema"]=="chacha.dev/adapter-promotion-receipt/v1",receipt
assert receipt["applied"] is True,receipt
print("CHACHA_DEV_V639_CF_PAGES_PILOT_TO_ENABLED=PASS")
print("CHACHA_DEV_V639_CF_PAGES_HUMAN_ENABLEMENT_APPROVAL=PASS")
PY

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=commit-live-registry"
python3 - "$WORK/live-candidate.json" "$LIVE_REGISTRY" <<'PY'
import json,os,pathlib,sys,tempfile
src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2])
x=json.load(open(src,encoding="utf-8"))
a=x["adapters"]["cloudflare-pages-production-adapter"]
assert a["status"]=="ENABLED",a
fd,tmp=tempfile.mkstemp(prefix=dst.name+".",dir=str(dst.parent))
try:
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(x,f,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o644); os.replace(tmp,dst)
    dfd=os.open(str(dst.parent),os.O_DIRECTORY); os.fsync(dfd); os.close(dfd)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
print("CHACHA_DEV_V639_CF_PAGES_LIVE_REGISTRY_ENABLED=PASS")
PY

echo "CHACHA_DEV_V639_CF_PAGES_ENABLE_STAGE=post-enable-guard"
unset CHACHA_CF_PAGES_PROD_POLICY || true
unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION || true
unset CLOUDFLARE_API_TOKEN || true
unset CLOUDFLARE_ACCOUNT_ID || true
export CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS="v639-enablement-guard-test"

python3 - "$EXE" "$WORK" <<'PY'
import json,os,pathlib,subprocess,sys
exe=sys.argv[1]; root=pathlib.Path(sys.argv[2]); build=root/"build"
env=os.environ.copy()
for k in ("CHACHA_CF_PAGES_PROD_POLICY","CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION",
          "CLOUDFLARE_API_TOKEN","CLOUDFLARE_ACCOUNT_ID"):
    env.pop(k,None)
env["CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS"]="v639-enablement-guard-test"
base={
 "schema":"chacha.dev/dispatch-envelope/v1","project":"v639-enablement-guard-test",
 "transition":"RELEASE->OPERATE","run_id":"v639-post-enable","wave":1,
 "task":{"id":"contract","permission":"read"},
 "bindings":[{"capability":"cloud-deploy-static","provider":"cloudflare-pages-production",
              "adapter":"cloudflare-pages-production-adapter","fallback_used":False,"health_state":"HEALTHY"}],
 "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                   "human_approval_required":False,"approval_id":None,"timeout_seconds":20},
 "workspace":str(root),"metadata":{"cloudflare_pages_production":{"action":"contract-status"}}
}
def run(v):
 p=subprocess.run([exe],input=json.dumps(v),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                  env=env,check=False,timeout=30)
 return p.returncode,json.loads(p.stdout)
rc,o=run(base); assert rc==0 and o["status"]=="OK",o

d=json.loads(json.dumps(base))
d["task"]={"id":"deploy","permission":"production-deploy"}
d["policy_context"]={"resource_class":"light","requires_storage_preflight":False,
                     "human_approval_required":True,"approval_id":"production-deployment","timeout_seconds":20}
d["metadata"]["cloudflare_pages_production"]={
 "action":"production-deploy","project_name":"v639-enablement-guard-test",
 "production_branch":"main","revision":"b"*40,"build_directory":str(build.resolve()),
 "approval_receipt":str(root/"missing-production-approval.json")
}
rc,o=run(d)
assert rc==2 and o["status"]=="BLOCKED",o
assert o["summary"]=="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",o
print("CHACHA_DEV_V639_CF_PAGES_POST_ENABLE_RUNTIME=PASS")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO")
print("CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_TARGET=NO")
PY

echo "CHACHA_DEV_V639_CF_PAGES_ENABLED=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_DEPLOYMENT_AUTHORIZED=NO"
echo "CHACHA_DEV_V639_OPERATE_ADVANCED=NO"
echo "CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V639_CF_PAGES_ENABLEMENT_RECEIPT=$PROMOTION_RECEIPT"
echo "CHACHA_DEV_V639_CF_PAGES_REGISTRY_BACKUP=$BACKUP"
