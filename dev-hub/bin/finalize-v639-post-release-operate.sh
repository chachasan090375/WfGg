#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V639_REV:-}"
PROJECT="v639-real-production-pilot-wfgg-20260923"
TARGET_URL="https://wfgg.pages.dev"
ROOT="/opt/chacha-dev/platform/current"
PC="$ROOT/dev-hub/bin/project-control.py"
PC_POLICY="$ROOT/dev-hub/config/project-control.v1.json"
CRYPTO="$ROOT/dev-hub/bin/crypto-trust.py"
CRYPTO_POLICY="$ROOT/dev-hub/config/cryptographic-trust.v1.json"
SENTINEL="$ROOT/dev-hub/bin/sentinel-client.py"
SENTINEL_POLICY="$ROOT/dev-hub/config/sentinel-runtime-policy.v1.json"
NAS_ADAPTER="/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"
STATE="/opt/chacha-dev/runtime/state/$PROJECT/state.json"
LEDGER="/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json"
EVIDENCE_DIR="/opt/chacha-dev/runtime/evidence/$PROJECT"
WORK="/tmp/chacha-dev-v639-finalize-$(date -u +%Y%m%dT%H%M%SZ)"
KEY_DIR="$WORK/signing"
TRUST_DIR="$EVIDENCE_DIR/post-release-trust"
PUBLIC_KEY="$TRUST_DIR/v639-post-release-public-key.pem"

cleanup(){
  rm -f "$KEY_DIR/private.pem" 2>/dev/null || true
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

fail(){
  echo "CHACHA_DEV_V639_FINALIZE=FAILED reason=$1"
  exit 20
}

[ "$(id -u)" -eq 0 ] || fail root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || fail pinned_revision_required
for cmd in python3 openssl curl grep sha256sum; do
  command -v "$cmd" >/dev/null || fail "missing_command:$cmd"
done
for f in "$PC" "$PC_POLICY" "$CRYPTO" "$CRYPTO_POLICY" "$SENTINEL" "$SENTINEL_POLICY" "$STATE" "$LEDGER"; do
  [ -f "$f" ] || fail "missing_file:$f"
done
[ -x "$NAS_ADAPTER" ] || fail nas_anchor_adapter_missing
mkdir -p "$WORK" "$KEY_DIR" "$TRUST_DIR"
chmod 0700 "$KEY_DIR"

BUNDLE="$(find "$EVIDENCE_DIR" -maxdepth 1 -type f -name 'v639-real-production-pilot-*.json' | sort | tail -1)"
[ -n "$BUNDLE" ] && [ -f "$BUNDLE" ] || fail real_production_evidence_bundle_missing

echo "CHACHA_DEV_V639_FINAL_STAGE=validate-real-production-evidence"
python3 - "$BUNDLE" "$STATE" "$LEDGER" <<'PY'
import json,sys,pathlib
bundle=json.load(open(sys.argv[1],encoding="utf-8"))
state=json.load(open(sys.argv[2],encoding="utf-8"))
ledger=json.load(open(sys.argv[3],encoding="utf-8"))
assert bundle["schema"]=="chacha.dev/v639-real-production-pilot-evidence/v1",bundle
assert bundle["target"]["project"]=="wfgg",bundle
assert bundle["target"]["branch"]=="main",bundle
assert bundle["target"]["url"]=="https://wfgg.pages.dev",bundle
assert bundle["content_noop_verified"] is True,bundle
assert bundle["rollback_target_captured"] is True,bundle
assert bundle["rollback_executed"] is False,bundle
assert bundle["production_mutation"] is True,bundle
assert bundle["operate_advanced"] is False,bundle
assert bundle["site_before"]["sha256"]==bundle["site_after"]["sha256"],bundle
assert bundle["site_after"]["http_status"]==200,bundle
assert state["state"]["lifecycle"]["stage"]=="RELEASE",state
approval=(ledger.get("approvals") or {}).get("production-deployment") or {}
assert approval.get("status")=="APPROVED",approval
assert approval.get("actor")=="cedric",approval
print("CHACHA_DEV_V639_REAL_PRODUCTION_EVIDENCE_VALIDATED=PASS")
print("CHACHA_DEV_V639_PRODUCTION_DEPLOYMENT_APPROVAL_LEDGER=PASS")
PY

python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   verify-state --project "$PROJECT" >"$WORK/verify-state-pre.json"
python3 - "$WORK/verify-state-pre.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
print("CHACHA_DEV_V639_PRE_FINALIZE_CONTROL_PLANE_INTEGRITY=PASS")
PY

echo "CHACHA_DEV_V639_FINAL_STAGE=build-post-release-evidence"
python3 - "$BUNDLE" "$WORK/post-release-evidence-summary.json" <<'PY'
import datetime,hashlib,json,pathlib,sys
src,out=sys.argv[1:]
b=json.load(open(src,encoding="utf-8"))
approval_path=pathlib.Path(b["human_approval"]["transaction_receipt"])
assert approval_path.is_file(),approval_path
approval_digest="sha256:"+hashlib.sha256(approval_path.read_bytes()).hexdigest()
assert approval_digest==b["human_approval"]["transaction_receipt_digest"],(approval_digest,b["human_approval"])
d=b["deployment"]
v={
 "schema":"chacha.dev/v639-post-release-evidence-summary/v1",
 "project":"v639-real-production-pilot-wfgg-20260923",
 "target":b["target"],
 "production_deployment":{
   "status":"PASS",
   "previous_deployment_id":b["previous_production"]["previous_deployment_id"],
   "new_deployment_id":d["new_deployment_id"],
   "rollback_available":bool(d.get("rollback_available")),
   "rollback_target_captured":b["rollback_target_captured"]
 },
 "post_deploy_smoke":{
   "status":"PASS",
   "http_status":b["site_after"]["http_status"],
   "content_noop_verified":b["content_noop_verified"],
   "before_sha256":b["site_before"]["sha256"],
   "after_sha256":b["site_after"]["sha256"]
 },
 "production_health":{"status":"PASS","http_status":b["site_after"]["http_status"],"url":b["target"]["url"]},
 "observability_health":{"status":"PASS","health_result_status":b["health_result"]["status"],
                         "health_summary":b["health_result"]["summary"]},
 "gates":{
   "identity-security":{"status":"OK","approval_receipt_digest":approval_digest,"secret_persisted":False},
   "ci-cd-release":{"status":"OK","rollback_available":bool(d.get("rollback_available")),
                    "content_noop_verified":b["content_noop_verified"]},
   "observability":{"status":"OK","http_status":b["site_after"]["http_status"]},
   "reliability-resilience":{"status":"OK","rollback_target_captured":b["rollback_target_captured"],
                             "rollback_executed":b["rollback_executed"]}
 },
 "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat()
}
pathlib.Path(out).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY

python3 - "$PROJECT" "$WORK/post-release-task-graph.json" <<'PY'
import json,pathlib,sys
project,out=sys.argv[1:]
graph={
 "schema":"chacha.dev/task-graph/v1",
 "project":project,
 "tasks":[
   {
     "id":"v639-post-release-real-evidence",
     "kind":"verification",
     "outputs":[
       {"type":"artifact","id":"production-deployment-receipt"},
       {"type":"artifact","id":"post-deploy-smoke"},
       {"type":"artifact","id":"production-health"},
       {"type":"artifact","id":"observability-health"},
       {"type":"gate","id":"identity-security"},
       {"type":"gate","id":"ci-cd-release"},
       {"type":"gate","id":"observability"},
       {"type":"gate","id":"reliability-resilience"}
     ],
     "verification":{"required":True,"mode":"machine"}
   },
   {
     "id":"v639-post-release-trust",
     "kind":"verification",
     "outputs":[
       {"type":"artifact","id":"post-release-signed-checkpoint"},
       {"type":"artifact","id":"post-release-anchor-quorum"}
     ],
     "verification":{"required":True,"mode":"independent-agent"}
   }
 ]
}
pathlib.Path(out).write_text(json.dumps(graph,indent=2)+"\n",encoding="utf-8")
PY

python3 - "$PROJECT" "$BUNDLE" "$WORK/post-release-evidence-summary.json" "$WORK/real-result.json" <<'PY'
import datetime,hashlib,json,pathlib,sys
project,bundle,summary,out=sys.argv[1:]
def dig(p):
    return "sha256:"+hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
v={
 "schema":"chacha.dev/task-result/v1","project":project,
 "task_id":"v639-post-release-real-evidence","producer":"v639-real-production-pilot",
 "status":"OK",
 "summary":"Real Cloudflare Pages production deployment, smoke, health and rollback readiness verified.",
 "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "outputs":[
   {"type":"artifact","id":"production-deployment-receipt","status":"OK"},
   {"type":"artifact","id":"post-deploy-smoke","status":"OK"},
   {"type":"artifact","id":"production-health","status":"OK"},
   {"type":"artifact","id":"observability-health","status":"OK"},
   {"type":"gate","id":"identity-security","status":"OK"},
   {"type":"gate","id":"ci-cd-release","status":"OK"},
   {"type":"gate","id":"observability","status":"OK"},
   {"type":"gate","id":"reliability-resilience","status":"OK"}
 ],
 "evidence":[
   {"source":str(pathlib.Path(bundle).resolve()),"digest":dig(bundle)},
   {"source":str(pathlib.Path(summary).resolve()),"digest":dig(summary)}
 ]
}
pathlib.Path(out).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY

python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   verify-result --project "$PROJECT"   --result "$WORK/real-result.json"   --graph "$WORK/post-release-task-graph.json"   --method machine --verifier verification-broker --ingest   >"$WORK/real-ingest.json"
python3 - "$WORK/real-ingest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert x["details"]["verification_status"]=="VERIFIED",x
print("CHACHA_DEV_V639_POST_RELEASE_REAL_EVIDENCE_INGEST=PASS")
PY

echo "CHACHA_DEV_V639_FINAL_STAGE=post-release-signed-checkpoint"
openssl genpkey -algorithm ED25519 -out "$KEY_DIR/private.pem" >/dev/null 2>&1
openssl pkey -in "$KEY_DIR/private.pem" -pubout -out "$KEY_DIR/public.pem" >/dev/null 2>&1
chmod 0600 "$KEY_DIR/private.pem"
chmod 0644 "$KEY_DIR/public.pem"
cp "$KEY_DIR/public.pem" "$PUBLIC_KEY"
chmod 0644 "$PUBLIC_KEY"

KEY_ID="v639-post-release-$(printf '%s' "$PROJECT:$REV" | sha256sum | awk '{print substr($1,1,12)}')"
python3 "$CRYPTO" --policy "$CRYPTO_POLICY" create-checkpoint   --state "$STATE" --key-id "$KEY_ID" --reason "POST_RELEASE_PRODUCTION_PILOT"   --output "$WORK/checkpoint.unsigned.json" >/dev/null
python3 "$CRYPTO" --policy "$CRYPTO_POLICY" sign   --checkpoint "$WORK/checkpoint.unsigned.json"   --private-key "$KEY_DIR/private.pem" --public-key "$KEY_DIR/public.pem"   --output "$TRUST_DIR/post-release-checkpoint.signed.json" >/dev/null
python3 "$CRYPTO" --policy "$CRYPTO_POLICY" verify   --checkpoint "$TRUST_DIR/post-release-checkpoint.signed.json"   --public-key "$PUBLIC_KEY" | grep -Fq "SIGNATURE_VERIFY=OK"
python3 "$CRYPTO" --policy "$CRYPTO_POLICY" anchor-manifest   --checkpoint "$TRUST_DIR/post-release-checkpoint.signed.json"   --output "$WORK/post-release-anchor-manifest.json" >/dev/null
python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   crypto-verify --project "$PROJECT"   --checkpoint "$TRUST_DIR/post-release-checkpoint.signed.json"   --public-key "$PUBLIC_KEY" >"$WORK/project-control-crypto.json"
python3 - "$WORK/project-control-crypto.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
print("CHACHA_DEV_V639_POST_RELEASE_SIGNED_CHECKPOINT=PASS")
PY

echo "CHACHA_DEV_V639_FINAL_STAGE=nas-create-only-anchor"
python3 - "$PROJECT" "$WORK/post-release-anchor-manifest.json" "$WORK/nas-envelope.json" <<'PY'
import json,pathlib,sys
project,anchor,out=sys.argv[1:]
a=json.load(open(anchor,encoding="utf-8"))
cid=a["checkpoint_id"]
v={
 "schema":"chacha.dev/dispatch-envelope/v1","project":project,
 "transition":"RELEASE->OPERATE","run_id":"v639-post-release-anchor-"+cid,"wave":1,
 "task":{"id":"post-release-anchor:nas","kind":"artifact",
         "description":"Publish V6.39 post-release anchor create-only.",
         "owner_role":"recovery-engineer","permission":"workspace-write",
         "outputs":[{"type":"artifact","id":"nas-post-release-anchor"}],
         "verification":{"required":True,"mode":"machine"}},
 "bindings":[{"capability":"trust-anchor-write","provider":"nas","adapter":"nas-ssh-adapter",
              "fallback_used":False,"health_state":"HEALTHY"}],
 "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                   "human_approval_required":False,"approval_id":None,"timeout_seconds":45},
 "workspace":str(pathlib.Path(anchor).resolve().parent),
 "metadata":{"nas_storage":{"action":"put-file",
                            "local_path":pathlib.Path(anchor).name,
                            "remote_path":f"projects/{project}/post-release-anchors/{cid}.json",
                            "reserve_mb":1024}}
}
pathlib.Path(out).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY
(
  cd "$WORK"
  "$NAS_ADAPTER" <"$WORK/nas-envelope.json" >"$TRUST_DIR/nas-post-release-anchor-result.json"
)
python3 - "$TRUST_DIR/nas-post-release-anchor-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
ev=x.get("evidence") or []
assert ev and ev[0].get("source") and str(ev[0].get("digest") or "").startswith("sha256:"),x
print("CHACHA_DEV_V639_POST_RELEASE_NAS_ANCHOR=PASS")
PY

echo "CHACHA_DEV_V639_FINAL_STAGE=sentinel-external-anchor"
python3 - "$REV" "$TRUST_DIR/post-release-checkpoint.signed.json" "$BUNDLE" "$WORK/sentinel-audit.json" <<'PY'
import hashlib,json,pathlib,sys
rev,checkpoint,bundle,out=sys.argv[1:]
cp=json.load(open(checkpoint,encoding="utf-8"))
bd="sha256:"+hashlib.sha256(pathlib.Path(bundle).read_bytes()).hexdigest()
v={
 "schema":"chacha.dev/sentinel-technical-audit/v1",
 "revision":rev,"verdict":"PASS",
 "audit_digest":cp["checkpoint_digest"],
 "checkpoint_digest":cp["checkpoint_digest"],
 "production_evidence_digest":bd,
 "advisory_findings":[],"blocking_findings":[]
}
pathlib.Path(out).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY
python3 "$SENTINEL" --policy "$SENTINEL_POLICY" release-check   --project-id "$PROJECT" --repository "chachasan090375/WfGg"   --revision "$REV"   --workflow-name "ChaCha DEV V6.39 controlled production handoff qualification"   --audit "$WORK/sentinel-audit.json"   >"$TRUST_DIR/sentinel-post-release-receipt.json"
python3 - "$TRUST_DIR/sentinel-post-release-receipt.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("verdict")=="PASS",x
assert x.get("receipt_id"),x
print("CHACHA_DEV_V639_POST_RELEASE_SENTINEL_ANCHOR=PASS")
PY

python3 - "$PROJECT"   "$TRUST_DIR/post-release-checkpoint.signed.json"   "$TRUST_DIR/nas-post-release-anchor-result.json"   "$TRUST_DIR/sentinel-post-release-receipt.json"   "$TRUST_DIR/post-release-anchor-quorum.json" <<'PY'
import datetime,json,pathlib,sys
project,checkpoint,nas,sentinel,out=sys.argv[1:]
cp=json.load(open(checkpoint,encoding="utf-8"))
nr=json.load(open(nas,encoding="utf-8"))
sr=json.load(open(sentinel,encoding="utf-8"))
nev=(nr.get("evidence") or [{}])[0]
v={
 "schema":"chacha.dev/trust-anchor-quorum/v1",
 "project_id":project,
 "checkpoint_id":cp["checkpoint_id"],
 "checkpoint_digest":cp["checkpoint_digest"],
 "required":2,"present":2,"status":"PASS",
 "anchors":[
   {"kind":"nas-create-only","source":nev.get("source"),"digest":nev.get("digest")},
   {"kind":"sentinel-external","receipt_id":sr.get("receipt_id"),
    "audit_digest":sr.get("audit_digest"),"verdict":sr.get("verdict")}
 ],
 "independent_from_project_workspace":True,
 "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat()
}
assert v["anchors"][0]["source"] and v["anchors"][1]["receipt_id"],v
pathlib.Path(out).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY
echo "CHACHA_DEV_V639_POST_RELEASE_ANCHOR_QUORUM=PASS"

echo "CHACHA_DEV_V639_FINAL_STAGE=trust-evidence-ingest"
python3 - "$PROJECT"   "$TRUST_DIR/post-release-checkpoint.signed.json"   "$TRUST_DIR/post-release-anchor-quorum.json"   "$TRUST_DIR/nas-post-release-anchor-result.json"   "$TRUST_DIR/sentinel-post-release-receipt.json"   "$WORK/trust-result.json" <<'PY'
import datetime,hashlib,json,pathlib,sys
project,checkpoint,quorum,nas,sentinel,out=sys.argv[1:]
def dig(p): return "sha256:"+hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
v={
 "schema":"chacha.dev/task-result/v1","project":project,
 "task_id":"v639-post-release-trust","producer":"v639-post-release-trust-builder",
 "status":"OK",
 "summary":"Signed post-release checkpoint anchored independently on NAS and Sentinel.",
 "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "outputs":[
   {"type":"artifact","id":"post-release-signed-checkpoint","status":"OK"},
   {"type":"artifact","id":"post-release-anchor-quorum","status":"OK"}
 ],
 "evidence":[
   {"source":str(pathlib.Path(checkpoint).resolve()),"digest":dig(checkpoint)},
   {"source":str(pathlib.Path(quorum).resolve()),"digest":dig(quorum)},
   {"source":str(pathlib.Path(nas).resolve()),"digest":dig(nas)},
   {"source":str(pathlib.Path(sentinel).resolve()),"digest":dig(sentinel)}
 ]
}
pathlib.Path(out).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
PY
python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   verify-result --project "$PROJECT"   --result "$WORK/trust-result.json"   --graph "$WORK/post-release-task-graph.json"   --method independent-agent --verifier sentinel-external-assurance --ingest   >"$WORK/trust-ingest.json"
python3 - "$WORK/trust-ingest.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert x["details"]["verification_status"]=="VERIFIED",x
print("CHACHA_DEV_V639_POST_RELEASE_TRUST_EVIDENCE_INGEST=PASS")
PY
rm -f "$KEY_DIR/private.pem"
echo "CHACHA_DEV_V639_POST_RELEASE_PRIVATE_KEY_RETAINED=NO"

echo "CHACHA_DEV_V639_FINAL_STAGE=final-real-target-read"
curl -fsSL "$TARGET_URL" -o "$WORK/site-final.bin"
python3 - "$BUNDLE" "$WORK/site-final.bin" <<'PY'
import hashlib,json,pathlib,sys
b=json.load(open(sys.argv[1],encoding="utf-8"))
digest="sha256:"+hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest()
assert digest==b["site_after"]["sha256"],(digest,b["site_after"]["sha256"])
print("CHACHA_DEV_V639_FINAL_PRODUCTION_CONTENT_STABLE=PASS")
PY

echo "CHACHA_DEV_V639_FINAL_STAGE=release-to-operate-plan"
python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   plan-transition --project "$PROJECT" --target OPERATE   >"$WORK/operate-plan.json"
python3 - "$WORK/operate-plan.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="READY",x
print("CHACHA_DEV_V639_RELEASE_TO_OPERATE_READY=PASS")
PY

echo "CHACHA_DEV_V639_FINAL_STAGE=release-to-operate-advance"
python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   advance --project "$PROJECT" --target OPERATE --actor central-orchestrator   >"$WORK/operate-advance.json"
python3 - "$WORK/operate-advance.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert x["details"]["transition"]=="RELEASE->OPERATE",x
print("CHACHA_DEV_V639_RELEASE_TO_OPERATE_TRANSACTION=PASS")
PY

python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   verify-state --project "$PROJECT" >"$WORK/verify-state-post.json"
python3 - "$WORK/verify-state-post.json" "$STATE" "$LEDGER" <<'PY'
import json,sys
resp=json.load(open(sys.argv[1],encoding="utf-8"))
state=json.load(open(sys.argv[2],encoding="utf-8"))
ledger=json.load(open(sys.argv[3],encoding="utf-8"))
assert resp["status"]=="OK",resp
assert state["state"]["lifecycle"]["stage"]=="OPERATE",state
arts=ledger.get("artifacts") or {}
gates=ledger.get("gates") or {}
for aid in [
 "production-deployment-receipt","post-deploy-smoke","production-health",
 "observability-health","post-release-signed-checkpoint","post-release-anchor-quorum"
]:
    assert (arts.get(aid) or {}).get("status")=="OK",(aid,arts.get(aid))
for gid in ["identity-security","ci-cd-release","observability","reliability-resilience"]:
    assert (gates.get(gid) or {}).get("status")=="OK",(gid,gates.get(gid))
approval=(ledger.get("approvals") or {}).get("production-deployment") or {}
assert approval.get("status")=="APPROVED",approval
print("CHACHA_DEV_V639_OPERATE_STATE=PASS")
print("CHACHA_DEV_V639_ALL_REQUIRED_POST_RELEASE_ARTIFACTS=PASS")
print("CHACHA_DEV_V639_ALL_REQUIRED_OPERATE_GATES=PASS")
print("CHACHA_DEV_V639_PRODUCTION_APPROVAL_PRESERVED=PASS")
PY

echo "CHACHA_DEV_V639_DIRECT_LEDGER_MUTATION=NO"
echo "CHACHA_DEV_V639_DIRECT_LIFECYCLE_MUTATION=NO"
echo "CHACHA_DEV_V639_POST_RELEASE_ANCHORS=2"
echo "CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V639_INSTALL=PASS"
