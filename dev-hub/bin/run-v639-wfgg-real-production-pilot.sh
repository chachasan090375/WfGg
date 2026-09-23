#!/usr/bin/env bash
set -Eeuo pipefail

# ChaCha DEV V6.39 — one-shot real production PILOT for the canonical wfgg Pages project.
# Scope approved by the human: wfgg/main, no-op frontend, pre-captured rollback,
# post-deploy health, immediate rollback on any failure. This runner does NOT
# advance the project lifecycle to OPERATE; post-release evidence/trust is a
# separate controlled transaction.

PROJECT_ID="v639-real-production-pilot-wfgg-20260923"
TARGET_PROJECT="wfgg"
TARGET_BRANCH="main"
TARGET_URL="https://wfgg.pages.dev"
SOURCE_REVISION="1aeb46b9d745ace185455a2e776eacf3eae9c21d"
EXPECTED_FRONTEND_TREE_SHA="497da306b47c4b2be8e10f40cbc0f99179f9f7d5"
HUMAN_ACTOR="cedric"
APPROVAL_EVIDENCE="chat-approval-v639-wfgg-release-operate-20260923"
APPROVAL_ID="production-deployment"

ROOT="/opt/chacha-dev/platform/current"
PC="$ROOT/dev-hub/bin/project-control.py"
PC_POLICY="$ROOT/dev-hub/config/project-control.v1.json"
STORE="$ROOT/dev-hub/bin/control-plane-store.py"
STATE_POLICY="$ROOT/dev-hub/config/control-plane-state.v1.json"
ADAPTER="/opt/chacha-dev/adapters/cloudflare-pages-production/current/cloudflare-pages-production-adapter"
ADAPTER_POLICY="/opt/chacha-dev/runtime/adapter-policies/cloudflare-pages-production-adapter.v1.json"
LIVE_REGISTRY="$ROOT/dev-hub/config/provider-adapters.v1.json"
BUILD_DIR="${CHACHA_DEV_V639_BUILD_DIR:-$PWD/frontend}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/chacha-dev-v639-real-production-$STAMP"
EVIDENCE_DIR="/opt/chacha-dev/runtime/evidence/$PROJECT_ID"
EVIDENCE_BUNDLE="$EVIDENCE_DIR/v639-real-production-pilot-$STAMP.json"

mkdir -p "$WORK" "$EVIDENCE_DIR"

cleanup(){
  unset CLOUDFLARE_PAGES_API_TOKEN CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID         CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS         CHACHA_CF_PAGES_PROD_POLICY || true
}
trap cleanup EXIT

fail(){
  echo "CHACHA_DEV_V639_REAL_PRODUCTION_PILOT=FAILED reason=$1"
  exit 20
}

[ "$(id -u)" -eq 0 ] || fail root_required
for cmd in python3 npx curl sha256sum; do
  command -v "$cmd" >/dev/null || fail "missing_command:$cmd"
done
for f in "$PC" "$PC_POLICY" "$STORE" "$STATE_POLICY" "$ADAPTER" "$ADAPTER_POLICY" "$LIVE_REGISTRY"; do
  [ -f "$f" ] || fail "missing_runtime_file:$f"
done
[ -x "$ADAPTER" ] || fail adapter_not_executable
[ -d "$BUILD_DIR" ] || fail build_directory_missing
[ -f "$BUILD_DIR/index.html" ] || fail frontend_index_missing

echo "CHACHA_DEV_V639_REAL_STAGE=human-secret-entry"
if [ -z "${CLOUDFLARE_PAGES_API_TOKEN:-}" ]; then
  read -rsp "Cloudflare Pages API token: " CLOUDFLARE_PAGES_API_TOKEN </dev/tty
  echo >/dev/tty
fi
if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  read -rp "Cloudflare Account ID: " CLOUDFLARE_ACCOUNT_ID </dev/tty
fi
[ -n "$CLOUDFLARE_PAGES_API_TOKEN" ] || fail pages_token_missing
[ -n "$CLOUDFLARE_ACCOUNT_ID" ] || fail account_id_missing
export CLOUDFLARE_PAGES_API_TOKEN
# Wrangler consumes CLOUDFLARE_API_TOKEN; use the dedicated Pages token only for this process.
export CLOUDFLARE_API_TOKEN="$CLOUDFLARE_PAGES_API_TOKEN"
export CLOUDFLARE_ACCOUNT_ID
export CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS="$TARGET_PROJECT"
export CHACHA_CF_PAGES_PROD_POLICY="$ADAPTER_POLICY"

echo "CHACHA_DEV_V639_REAL_STAGE=runtime-contract"
python3 - "$LIVE_REGISTRY" "$ADAPTER" "$ADAPTER_POLICY" <<'PY'
import json,pathlib,sys
reg=json.load(open(sys.argv[1],encoding="utf-8"))
exe=pathlib.Path(sys.argv[2])
policy=json.load(open(sys.argv[3],encoding="utf-8"))
a=reg["adapters"]["cloudflare-pages-production-adapter"]
p=reg["providers"]["cloudflare-pages-production"]
assert a["status"]=="ENABLED",a
assert pathlib.Path(a["executable"]).resolve()==exe.resolve(),(a,exe)
assert p["adapter"]=="cloudflare-pages-production-adapter",p
assert p["execution"]=="vps",p
assert policy["mutation_guard"]["environment_switch"]=="CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION",policy
assert policy["mutation_guard"]["required_value"]=="ENABLED",policy
assert policy["mutation_guard"]["protected_approval_id"]=="production-deployment",policy
print("CHACHA_DEV_V639_CF_PAGES_ENABLED_RUNTIME=PASS")
print("CHACHA_DEV_V639_EXECUTION_SURFACE=VPS")
PY

# No production mutation yet.
echo "CHACHA_DEV_V639_REAL_STAGE=provider-read-preflight"
python3 - "$TARGET_PROJECT" "$TARGET_BRANCH" "$TARGET_URL" "$WORK/provider-before.json" <<'PY'
import json,os,sys,urllib.parse,urllib.request
project,branch,url,out=sys.argv[1:]
aid=urllib.parse.quote(os.environ["CLOUDFLARE_ACCOUNT_ID"],safe="")
pname=urllib.parse.quote(project,safe="")
req=urllib.request.Request(
 f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects/{pname}",
 headers={"Authorization":"Bearer "+os.environ["CLOUDFLARE_PAGES_API_TOKEN"],
          "Accept":"application/json","User-Agent":"ChaCha-DEV-V639-RealPilot/1"},
 method="GET")
with urllib.request.urlopen(req,timeout=30) as r:
    payload=json.loads(r.read())
assert payload.get("success") is True,payload
row=payload.get("result") or {}
assert row.get("name")==project,row
assert row.get("production_branch")==branch,row
can=row.get("canonical_deployment") or {}
latest=can.get("latest_stage") or {}
assert can.get("id"),can
assert str(latest.get("status") or "").lower()=="success",can
value={
 "project":project,"branch":branch,"canonical_url":url,
 "previous_deployment_id":str(can["id"]),
 "previous_deployment_url":str(can.get("url") or ""),
 "previous_status":str(latest.get("status") or ""),
}
json.dump(value,open(out,"w",encoding="utf-8"),indent=2)
print("CHACHA_DEV_V639_PREVIOUS_DEPLOYMENT_CAPTURE=PASS")
PY

python3 - "$TARGET_URL" "$WORK/site-before.json" <<'PY'
import hashlib,json,sys,urllib.request
url,out=sys.argv[1:]
req=urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-V639-NoopProof/1"})
with urllib.request.urlopen(req,timeout=30) as r:
    body=r.read()
    status=int(r.status)
assert status==200,status
v={"url":url,"http_status":status,"sha256":"sha256:"+hashlib.sha256(body).hexdigest(),"bytes":len(body)}
json.dump(v,open(out,"w",encoding="utf-8"),indent=2)
print("CHACHA_DEV_V639_PREDEPLOY_SITE_HASH=PASS")
PY

# Validate the policy-pinned Wrangler before opening the mutation switch.
WRANGLER_VERSION="$(python3 - "$ADAPTER_POLICY" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
v=str((x.get("deployment") or {}).get("wrangler_version") or "")
assert v=="3.114.17",v
print(v)
PY
)"
NODE_VERSION="$(node --version)"
case "$NODE_VERSION" in
  v18.*) ;;
  *) fail "unexpected_node_version:$NODE_VERSION" ;;
esac
npx --yes "wrangler@$WRANGLER_VERSION" --version | tee "$WORK/wrangler-version.out"
grep -Fq "$WRANGLER_VERSION" "$WORK/wrangler-version.out"
echo "CHACHA_DEV_V639_NODE18_RUNTIME=PASS"
echo "CHACHA_DEV_V639_WRANGLER_VERSION=$WRANGLER_VERSION"
echo "CHACHA_DEV_V639_WRANGLER_PREFLIGHT=PASS"

echo "CHACHA_DEV_V639_REAL_STAGE=project-control-approval"
STATE="/opt/chacha-dev/runtime/state/$PROJECT_ID/state.json"
LEDGER="/opt/chacha-dev/runtime/evidence/$PROJECT_ID/ledger.json"
if [ ! -f "$STATE" ]; then
  cat >"$WORK/initial.json" <<JSON
{"lifecycle":{"stage":"RELEASE"},"identity":{"kind":"v639-real-production-pilot","target":"wfgg","source_revision":"$SOURCE_REVISION"}}
JSON
  python3 "$STORE" --policy "$STATE_POLICY" --root /opt/chacha-dev/runtime/state     init --project "$PROJECT_ID" --actor "$HUMAN_ACTOR" --initial "$WORK/initial.json" >/dev/null
fi
if [ ! -f "$LEDGER" ]; then
  mkdir -p "$(dirname "$LEDGER")"
  python3 - "$PROJECT_ID" "$LEDGER" <<'PY'
import json,sys,datetime,pathlib
project,path=sys.argv[1:]
v={"schema":"chacha.dev/evidence-ledger/v1","project":project,
   "updated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
   "artifacts":{},"gates":{},"approvals":{},"risk_acceptances":[],"history":[]}
pathlib.Path(path).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY
fi

python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   verify-state --project "$PROJECT_ID" >"$WORK/verify-state.json"
python3 - "$WORK/verify-state.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
print("CHACHA_DEV_V639_CONTROL_PLANE_INTEGRITY=PASS")
PY

python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   record-approval --project "$PROJECT_ID" --approval-id "$APPROVAL_ID"   --actor "$HUMAN_ACTOR" --evidence "$APPROVAL_EVIDENCE" >"$WORK/approval-response.json"

APPROVAL_RECEIPT="$(python3 - "$WORK/approval-response.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
d=x.get("details") or {}
p=str(d.get("receipt") or "")
assert p,p
print(p)
PY
)"
[ -f "$APPROVAL_RECEIPT" ] || fail approval_receipt_missing
echo "CHACHA_DEV_V639_PROTECTED_PRODUCTION_APPROVAL=PASS"

make_request(){
  local action="$1" permission="$2" outfile="$3" previous="${4:-}"
  python3 - "$action" "$permission" "$outfile" "$previous" "$APPROVAL_RECEIPT" "$BUILD_DIR" <<'PY'
import json,sys,pathlib
action,permission,out,previous,approval,build=sys.argv[1:]
project_id="v639-real-production-pilot-wfgg-20260923"
meta={
 "action":action,
 "project_name":"wfgg",
 "production_branch":"main",
 "revision":"1aeb46b9d745ace185455a2e776eacf3eae9c21d",
 "build_directory":str(pathlib.Path(build).resolve()),
 "approval_receipt":approval,
 "canonical_url":"https://wfgg.pages.dev"
}
if previous:
    meta["previous_deployment_id"]=previous
req={
 "schema":"chacha.dev/dispatch-envelope/v1",
 "project":project_id,
 "transition":"RELEASE->OPERATE",
 "run_id":"v639-real-production-pilot",
 "wave":1,
 "task":{"id":"v639-real-"+action,"permission":permission},
 "bindings":[{"capability":"cloud-deploy-static","provider":"cloudflare-pages-production",
              "adapter":"cloudflare-pages-production-adapter","fallback_used":False,"health_state":"HEALTHY"}],
 "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                   "human_approval_required":True,"approval_id":"production-deployment",
                   "timeout_seconds":600},
 "workspace":str(pathlib.Path(build).resolve().parent),
 "metadata":{"cloudflare_pages_production":meta}
}
pathlib.Path(out).write_text(json.dumps(req,indent=2)+"\n",encoding="utf-8")
PY
}

PREVIOUS_ID="$(python3 - "$WORK/provider-before.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["previous_deployment_id"])
PY
)"

rollback_now(){
  local reason="$1"
  echo "CHACHA_DEV_V639_ROLLBACK_TRIGGERED=YES reason=$reason"
  make_request production-rollback production-deploy "$WORK/rollback-request.json" "$PREVIOUS_ID"
  set +e
  "$ADAPTER" <"$WORK/rollback-request.json" >"$WORK/rollback-result.json"
  local rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V639_ROLLBACK_EXECUTED=FAILED"
    return 1
  fi
  python3 - "$WORK/rollback-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert x["summary"]=="CLOUDFLARE_PAGES_PRODUCTION_ROLLBACK_OK",x
print("CHACHA_DEV_V639_ROLLBACK_EXECUTED=PASS")
PY
  return 0
}

echo "CHACHA_DEV_V639_REAL_STAGE=deployment-plan"
unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION || true
make_request deployment-plan read "$WORK/plan-request.json"
"$ADAPTER" <"$WORK/plan-request.json" >"$WORK/plan-result.json"
python3 - "$WORK/plan-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
d=x["evidence"][0]["details"]
assert d["project_name"]=="wfgg",d
assert d["production_branch"]=="main",d
assert d["production_mutation"] is False,d
assert d["rollback_capture_required"] is True,d
assert d["execution_switch_enabled"] is False,d
print("CHACHA_DEV_V639_REAL_DEPLOYMENT_PLAN=PASS")
print("CHACHA_DEV_V639_PREAPPROVAL_PRODUCTION_MUTATION=NO")
PY

# The only point where real production execution is opened.
export CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION=ENABLED
echo "CHACHA_DEV_V639_REAL_STAGE=production-deploy"
make_request production-deploy production-deploy "$WORK/deploy-request.json"

set +e
"$ADAPTER" <"$WORK/deploy-request.json" >"$WORK/deploy-result.json"
DEPLOY_RC=$?
set -e

if [ "$DEPLOY_RC" -ne 0 ]; then
  # A command may have reached Cloudflare before the adapter reported failure.
  python3 - "$TARGET_PROJECT" "$PREVIOUS_ID" "$WORK/provider-after-failed-deploy.json" <<'PY'
import json,os,sys,urllib.parse,urllib.request
project,previous,out=sys.argv[1:]
aid=urllib.parse.quote(os.environ["CLOUDFLARE_ACCOUNT_ID"],safe="")
pname=urllib.parse.quote(project,safe="")
req=urllib.request.Request(
 f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects/{pname}",
 headers={"Authorization":"Bearer "+os.environ["CLOUDFLARE_PAGES_API_TOKEN"],
          "Accept":"application/json","User-Agent":"ChaCha-DEV-V639-RealPilot/1"})
with urllib.request.urlopen(req,timeout=30) as r: p=json.loads(r.read())
can=(p.get("result") or {}).get("canonical_deployment") or {}
json.dump({"canonical_deployment_id":str(can.get("id") or ""),
           "changed":str(can.get("id") or "")!=previous},open(out,"w",encoding="utf-8"),indent=2)
print("CHACHA_DEV_V639_FAILED_DEPLOY_CANONICAL_CHECK=PASS")
PY
  CHANGED="$(python3 - "$WORK/provider-after-failed-deploy.json" <<'PY'
import json,sys
print("YES" if json.load(open(sys.argv[1],encoding="utf-8"))["changed"] else "NO")
PY
)"
  if [ "$CHANGED" = "YES" ]; then rollback_now deploy_adapter_failure || true; fi
  fail production_deploy_failed
fi

python3 - "$WORK/deploy-result.json" "$PREVIOUS_ID" >"$WORK/deploy-summary.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert x["summary"]=="CLOUDFLARE_PAGES_PRODUCTION_DEPLOY_OK",x
d=x["evidence"][0]["details"]
assert d["project_name"]=="wfgg",d
assert d["previous_deployment_id"]==sys.argv[2],d
assert d["new_deployment_id"] and d["new_deployment_id"]!=sys.argv[2],d
assert d["rollback_available"] is True,d
json.dump(d,sys.stdout,indent=2)
PY
echo "CHACHA_DEV_V639_REAL_PRODUCTION_DEPLOY=PASS"

echo "CHACHA_DEV_V639_REAL_STAGE=post-deploy-health"
make_request production-health read "$WORK/health-request.json"
set +e
"$ADAPTER" <"$WORK/health-request.json" >"$WORK/health-result.json"
HEALTH_RC=$?
set -e
if [ "$HEALTH_RC" -ne 0 ]; then
  rollback_now health_check_failure || true
  fail post_deploy_health_failed
fi
python3 - "$WORK/health-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert x["summary"]=="PRODUCTION_HEALTH_OK",x
assert x["evidence"][0]["details"]["http_status"]==200,x
print("CHACHA_DEV_V639_POST_DEPLOY_HEALTH=PASS")
PY

python3 - "$TARGET_URL" "$WORK/site-after.json" <<'PY'
import hashlib,json,sys,urllib.request
url,out=sys.argv[1:]
req=urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-V639-NoopProof/1"})
with urllib.request.urlopen(req,timeout=30) as r:
    body=r.read(); status=int(r.status)
assert status==200,status
json.dump({"url":url,"http_status":status,
           "sha256":"sha256:"+hashlib.sha256(body).hexdigest(),
           "bytes":len(body)},open(out,"w",encoding="utf-8"),indent=2)
PY

if ! python3 - "$WORK/site-before.json" "$WORK/site-after.json" <<'PY'
import json,sys
before=json.load(open(sys.argv[1],encoding="utf-8"))
after=json.load(open(sys.argv[2],encoding="utf-8"))
assert before["http_status"]==after["http_status"]==200,(before,after)
assert before["sha256"]==after["sha256"],(before,after)
assert before["bytes"]==after["bytes"],(before,after)
print("CHACHA_DEV_V639_REAL_CONTENT_NOOP=PASS")
PY
then
  rollback_now content_noop_mismatch || true
  fail production_content_changed
fi

echo "CHACHA_DEV_V639_REAL_STAGE=evidence-bundle"
python3 - "$WORK/provider-before.json" "$WORK/deploy-summary.json"   "$WORK/site-before.json" "$WORK/site-after.json" "$WORK/health-result.json"   "$APPROVAL_RECEIPT" "$EVIDENCE_BUNDLE" <<'PY'
import datetime,hashlib,json,pathlib,sys
before_p,deploy,site_b,site_a,health,approval,out=sys.argv[1:]
def load(p): return json.load(open(p,encoding="utf-8"))
def digest(p):
    return "sha256:"+hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
value={
 "schema":"chacha.dev/v639-real-production-pilot-evidence/v1",
 "project":"v639-real-production-pilot-wfgg-20260923",
 "target":{"provider":"cloudflare-pages","project":"wfgg","branch":"main","url":"https://wfgg.pages.dev"},
 "source_revision":"1aeb46b9d745ace185455a2e776eacf3eae9c21d",
 "approved_frontend_tree_sha":"497da306b47c4b2be8e10f40cbc0f99179f9f7d5",
 "human_approval":{"id":"production-deployment","actor":"cedric",
                    "evidence":"chat-approval-v639-wfgg-release-operate-20260923",
                    "transaction_receipt":approval,
                    "transaction_receipt_digest":digest(approval)},
 "previous_production":load(before_p),
 "deployment":load(deploy),
 "site_before":load(site_b),
 "site_after":load(site_a),
 "health_result":load(health),
 "content_noop_verified":load(site_b)["sha256"]==load(site_a)["sha256"],
 "rollback_target_captured":True,
 "rollback_executed":False,
 "production_mutation":True,
 "operate_advanced":False,
 "automatic_external_spend_eur":0,
 "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat()
}
pathlib.Path(out).write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")
print("CHACHA_DEV_V639_REAL_PRODUCTION_EVIDENCE_BUNDLE=PASS")
PY

unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION
echo "CHACHA_DEV_V639_REAL_PRODUCTION_TARGET=PASS"
echo "CHACHA_DEV_V639_REAL_PRODUCTION_MUTATION=PASS"
echo "CHACHA_DEV_V639_REAL_ROLLBACK_TARGET_CAPTURED=PASS"
echo "CHACHA_DEV_V639_REAL_PRODUCTION_PILOT=PASS"
echo "CHACHA_DEV_V639_OPERATE_ADVANCED=NO"
echo "CHACHA_DEV_V639_POST_RELEASE_EVIDENCE_INGEST=PENDING"
echo "CHACHA_DEV_V639_INSTALL=NOT_YET_POST_RELEASE_TRUST_REQUIRED"
echo "CHACHA_DEV_V639_EVIDENCE_BUNDLE=$EVIDENCE_BUNDLE"
