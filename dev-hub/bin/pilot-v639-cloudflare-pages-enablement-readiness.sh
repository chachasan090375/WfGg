#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V639_REV:-}"
REPO="chachasan090375/WfGg"
WORK="/tmp/chacha-dev-v639-cf-pages-enablement-$(date -u +%Y%m%dT%H%M%SZ)"
EXE="/opt/chacha-dev/adapters/cloudflare-pages-production/current/cloudflare-pages-production-adapter"
PROMO_RECEIPT="/opt/chacha-dev/runtime/adapter-provisioning/cloudflare-pages-production-adapter-v1.0.0-9dea6ec9aa58e4f7d469fcec2a1d601eb1ccea6a.json"

cleanup(){ rm -rf -- "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "CHACHA_DEV_V639_ENABLEMENT_READINESS=BLOCKED reason=pinned_revision_required"
  exit 2
}
for cmd in curl tar python3 grep sha256sum; do
  command -v "$cmd" >/dev/null || {
    echo "CHACHA_DEV_V639_ENABLEMENT_READINESS=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$WORK/src" "$WORK/build"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REV" -o "$WORK/source.tar.gz"
tar -xzf "$WORK/source.tar.gz" -C "$WORK/src" --strip-components=1
SRC="$WORK/src"

echo "CHACHA_DEV_V639_ENABLEMENT_STAGE=preflight"
python3 - "$SRC/dev-hub/config/provider-adapters.v1.json" "$SRC/dev-hub/evidence/v639/cloudflare-pages-production-pilot-promotion-receipt.json" "$EXE" <<'PY'
import json,sys,pathlib
registry=json.load(open(sys.argv[1],encoding="utf-8"))
receipt=json.load(open(sys.argv[2],encoding="utf-8"))
exe=sys.argv[3]
entry=registry["adapters"]["cloudflare-pages-production-adapter"]
assert entry["status"]=="PILOT",entry
assert entry["executable"]==exe,entry
assert receipt["transition"]=="CONTRACT_OK->PILOT",receipt
assert receipt["status"]=="COMMITTED",receipt
assert receipt["applied"] is True,receipt
assert receipt["production_execution_enabled"] is False,receipt
assert receipt["executable_after"]==exe,receipt
assert pathlib.Path(exe).is_file(),exe
print("CHACHA_DEV_V639_CF_PAGES_PILOT_STATE=PASS")
PY

python3 - "$PROMO_RECEIPT" "$SRC/dev-hub/evidence/v639/cloudflare-pages-production-pilot-promotion-receipt.json" "$EXE" <<'PY'
import hashlib,json,pathlib,sys
prov=json.load(open(sys.argv[1],encoding="utf-8"))
promotion=json.load(open(sys.argv[2],encoding="utf-8"))
exe=pathlib.Path(sys.argv[3])
h="sha256:"+hashlib.sha256(exe.read_bytes()).hexdigest()
assert prov["adapter"]=="cloudflare-pages-production-adapter",prov
assert prov["probe"]["status"]=="PASS",prov
assert prov["source_digest"]==prov["installed_digest"]==prov["executable_digest"]==h,prov
assert promotion["executable_digest"]==h,promotion
print("CHACHA_DEV_V639_CF_PAGES_RUNTIME_DIGEST_BINDING=PASS")
PY

unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION || true
unset CLOUDFLARE_API_TOKEN || true
unset CLOUDFLARE_ACCOUNT_ID || true
export CHACHA_CF_PAGES_PROD_POLICY="$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json"
export CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS="v639-enablement-readiness"
printf '%s\n' '<!doctype html><title>V6.39 enablement readiness</title>' > "$WORK/build/index.html"

echo "CHACHA_DEV_V639_ENABLEMENT_STAGE=repeatability"
python3 - "$EXE" "$WORK" <<'PY'
import json,os,pathlib,subprocess,sys
exe=sys.argv[1]
root=pathlib.Path(sys.argv[2])
env=os.environ.copy()
for k in ("CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION","CLOUDFLARE_API_TOKEN","CLOUDFLARE_ACCOUNT_ID"):
    env.pop(k,None)

def run(payload):
    p=subprocess.run([exe],input=json.dumps(payload),text=True,
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     env=env,check=False,timeout=30)
    try:o=json.loads(p.stdout)
    except Exception as e: raise SystemExit("ADAPTER_OUTPUT_INVALID:"+p.stdout[-1200:]+p.stderr[-1200:]) from e
    return p.returncode,o

def base(i):
    return {
      "schema":"chacha.dev/dispatch-envelope/v1",
      "project":"v639-enablement-readiness",
      "transition":"RELEASE->OPERATE",
      "run_id":f"v639-enablement-readiness-{i}",
      "wave":1,
      "task":{"id":f"contract-{i}","permission":"read"},
      "bindings":[{
        "capability":"cloud-deploy-static",
        "provider":"cloudflare-pages-production",
        "adapter":"cloudflare-pages-production-adapter",
        "fallback_used":False,"health_state":"UNKNOWN"
      }],
      "policy_context":{
        "resource_class":"light","requires_storage_preflight":False,
        "human_approval_required":False,"approval_id":None,"timeout_seconds":20
      },
      "workspace":str(root),
      "metadata":{"cloudflare_pages_production":{"action":"contract-status"}}
    }

for i in range(1,4):
    b=base(i)
    rc,o=run(b)
    assert rc==0 and o["status"]=="OK",o

    p=json.loads(json.dumps(b))
    p["task"]={"id":f"plan-{i}","permission":"read"}
    p["metadata"]["cloudflare_pages_production"]={
      "action":"deployment-plan","project_name":"v639-enablement-readiness",
      "production_branch":"main","revision":"f"*40,
      "build_directory":str((root/"build").resolve())
    }
    rc,o=run(p)
    assert rc==0 and o["status"]=="OK",o
    d=o["evidence"][0]["details"]
    assert d["production_mutation"] is False,d
    assert d["execution_switch_enabled"] is False,d
    assert d["rollback_capture_required"] is True,d

    deploy=json.loads(json.dumps(p))
    deploy["task"]={"id":f"deploy-{i}","permission":"production-deploy"}
    deploy["policy_context"]={
      "resource_class":"light","requires_storage_preflight":False,
      "human_approval_required":True,"approval_id":"production-deployment","timeout_seconds":20
    }
    deploy["metadata"]["cloudflare_pages_production"]["action"]="production-deploy"
    deploy["metadata"]["cloudflare_pages_production"]["approval_receipt"]=str(root/"missing-approval.json")
    rc,o=run(deploy)
    assert rc==2 and o["status"]=="BLOCKED",o
    assert o["summary"]=="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",o

    rb=json.loads(json.dumps(deploy))
    rb["task"]={"id":f"rollback-{i}","permission":"production-deploy"}
    rb["metadata"]["cloudflare_pages_production"]["action"]="production-rollback"
    rb["metadata"]["cloudflare_pages_production"]["previous_deployment_id"]="never-used"
    rc,o=run(rb)
    assert rc==2 and o["status"]=="BLOCKED",o
    assert o["summary"]=="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",o

print("CHACHA_DEV_V639_CF_PAGES_REPEATABLE_RUNTIME=PASS")
print("CHACHA_DEV_V639_CF_PAGES_REPEATABILITY_RUNS=3")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED")
print("CHACHA_DEV_V639_CF_PAGES_NETWORK_WRITE=NO")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO")
PY

echo "CHACHA_DEV_V639_ENABLEMENT_STAGE=rollback-contract"
python3 - "$SRC/dev-hub/config/adapter-rollbacks.v1.json" "$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json" "$SRC/dev-hub/adapters/cloudflare-pages-production-adapter.py" <<'PY'
import json,sys
roll=json.load(open(sys.argv[1],encoding="utf-8"))
policy=json.load(open(sys.argv[2],encoding="utf-8"))
source=open(sys.argv[3],encoding="utf-8").read()
rb=roll["adapters"]["cloudflare-pages-production-adapter"]
assert rb["enabled"] is True,rb
assert rb["from_status"]=="ENABLED",rb
assert rb["target_status"]=="DISABLED",rb
assert "production-rollback-failure" in rb["triggers"],rb
p=policy["rollback"]
assert p["capture_current_production_before_deploy"] is True,p
assert p["previous_successful_production_deployment_required"] is True,p
assert p["verify_restored_deployment"] is True,p
assert "/rollback" in source
assert "canonical_production(" in source
print("CHACHA_DEV_V639_CF_PAGES_ROLLBACK_DEFINED=PASS")
PY

echo "CHACHA_DEV_V639_ENABLEMENT_STAGE=exact-head-ci-provider-health"
API="https://api.github.com/repos/$REPO/actions/runs?head_sha=$REV&per_page=100"
READY=0
for i in $(seq 1 80); do
  curl -fsS -H "Accept: application/vnd.github+json" -H "User-Agent: ChaCha-DEV-V639" "$API" -o "$WORK/actions.json"
  set +e
  python3 - "$WORK/actions.json" "$REV" "$WORK/provider-health-run.json" <<'PY'
import json,sys
src,rev,out=sys.argv[1:]
runs=json.load(open(src,encoding="utf-8")).get("workflow_runs") or []
name="ChaCha DEV V6.39 controlled production handoff qualification"
x=[r for r in runs if r.get("name")==name and r.get("head_sha")==rev]
if not x:
    raise SystemExit(2)
x.sort(key=lambda r:r.get("run_number",0),reverse=True)
r=x[0]
if r.get("status")!="completed":
    raise SystemExit(2)
if r.get("conclusion")!="success":
    print("CHACHA_DEV_V639_EXACT_HEAD_CI=FAILED")
    raise SystemExit(10)
json.dump({
  "run_id":r.get("id"),
  "html_url":r.get("html_url"),
  "name":r.get("name"),
  "head_sha":r.get("head_sha"),
  "conclusion":r.get("conclusion"),
  "updated_at":r.get("updated_at")
},open(out,"w",encoding="utf-8"),indent=2)
print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_HEALTH_CI=PASS")
PY
  RC=$?
  set -e
  if [ "$RC" -eq 0 ]; then READY=1; break; fi
  [ "$RC" -eq 2 ] || exit "$RC"
  sleep 15
done
[ "$READY" -eq 1 ] || { echo "CHACHA_DEV_V639_CF_PAGES_PROVIDER_HEALTH_CI=TIMEOUT"; exit 11; }

echo "CHACHA_DEV_V639_ENABLEMENT_STAGE=promotion-readiness"
python3 - "$WORK/provider-health-run.json" "$WORK/enablement-evidence.json" <<'PY'
import datetime,json,sys
run=json.load(open(sys.argv[1],encoding="utf-8"))
ts=datetime.datetime.now(datetime.timezone.utc).isoformat()
e={
 "schema":"chacha.dev/adapter-promotion-evidence/v1",
 "adapter":"cloudflare-pages-production-adapter",
 "observed_at":ts,
 "evidence":{
   "repeatable-pass":{
     "status":"PASS",
     "source":"vps://ChaChaVPS/v639/cloudflare-pages-production/repeatability-3x",
     "observed_at":ts,
     "details":{"runs":3,"production_execution":"BLOCKED","network_write":False,"production_mutation":False}
   },
   "provider-health-pass":{
     "status":"PASS",
     "source":run.get("html_url") or ("github-actions://"+str(run.get("run_id"))),
     "observed_at":ts,
     "details":{"workflow_run_id":run.get("run_id"),"head_sha":run.get("head_sha"),
                "provider_health_mode":"READ_ONLY","production_mutation":False}
   },
   "rollback-defined":{
     "status":"PASS",
     "source":"repo://dev-hub/config/adapter-rollbacks.v1.json",
     "observed_at":ts,
     "details":{"provider_rollback_api":True,"canonical_deployment_restore_verification":True}
   }
 },
 "approvals":[]
}
json.dump(e,open(sys.argv[2],"w",encoding="utf-8"),indent=2)
PY

python3 "$SRC/dev-hub/bin/adapter-promotion.py"   --registry "$SRC/dev-hub/config/provider-adapters.v1.json"   --contract "$SRC/dev-hub/config/adapter-contract.v1.json"   --policy "$SRC/dev-hub/config/adapter-promotion.v1.json"   --evidence "$WORK/enablement-evidence.json"   --report "$WORK/enablement-plan.json"   --json   plan   --adapter cloudflare-pages-production-adapter   --target ENABLED   --executable "$EXE"   > "$WORK/enablement-plan.out" || true

python3 - "$WORK/enablement-plan.out" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"))
assert p["adapter"]=="cloudflare-pages-production-adapter",p
assert p["current_status"]=="PILOT",p
assert p["target_status"]=="ENABLED",p
assert p["production_capable"] is True,p
assert p["approval_required"] is True,p
assert p["applied"] is False,p
blockers=set(p.get("blockers") or [])
assert blockers=={"EXPLICIT_PRODUCTION_APPROVAL_ID_REQUIRED"},p
print("CHACHA_DEV_V639_CF_PAGES_ENABLEMENT_EVIDENCE=PASS")
print("CHACHA_DEV_V639_CF_PAGES_ENABLEMENT_BLOCKED_ONLY_BY_HUMAN_APPROVAL=PASS")
PY

echo "CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED"
echo "CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO"
echo "CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_TARGET=NO"
echo "CHACHA_DEV_V639_OPERATE_ADVANCED=NO"
echo "CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V639_ENABLEMENT_READINESS=PASS"
echo "CHACHA_DEV_V639_ENABLEMENT_EVIDENCE=$WORK/enablement-evidence.json"
echo "CHACHA_DEV_V639_ENABLEMENT_PLAN=$WORK/enablement-plan.json"
