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
STATE="/opt/chacha-dev/runtime/state/$PROJECT/state.json"
LEDGER="/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json"
EVIDENCE_DIR="/opt/chacha-dev/runtime/evidence/$PROJECT"
TRUST_DIR="$EVIDENCE_DIR/post-release-trust"
PUBLIC_KEY="$TRUST_DIR/v639-post-release-public-key.pem"
SIGNED_CHECKPOINT="$TRUST_DIR/post-release-checkpoint.signed.json"
ANCHOR_QUORUM="$TRUST_DIR/post-release-anchor-quorum.json"
WORK="/tmp/chacha-dev-v639-resume-$(date -u +%Y%m%dT%H%M%SZ)"

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

fail(){
  echo "CHACHA_DEV_V639_RESUME=FAILED reason=$1"
  exit 20
}

[ "$(id -u)" -eq 0 ] || fail root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || fail pinned_revision_required
for cmd in python3 curl grep sha256sum; do
  command -v "$cmd" >/dev/null || fail "missing_command:$cmd"
done
for f in "$PC" "$PC_POLICY" "$CRYPTO" "$CRYPTO_POLICY" "$STATE" "$LEDGER" "$PUBLIC_KEY" "$SIGNED_CHECKPOINT" "$ANCHOR_QUORUM"; do
  [ -f "$f" ] || fail "missing_file:$f"
done
mkdir -p "$WORK"

BUNDLE="$(find "$EVIDENCE_DIR" -maxdepth 1 -type f -name 'v639-real-production-pilot-*.json' | sort | tail -1)"
[ -n "$BUNDLE" ] && [ -f "$BUNDLE" ] || fail real_production_evidence_bundle_missing

echo "CHACHA_DEV_V639_RESUME_STAGE=verify-existing-post-release-state"
python3 - "$STATE" "$LEDGER" "$ANCHOR_QUORUM" <<'PY'
import json,sys
state=json.load(open(sys.argv[1],encoding="utf-8"))
ledger=json.load(open(sys.argv[2],encoding="utf-8"))
quorum=json.load(open(sys.argv[3],encoding="utf-8"))
assert state["state"]["lifecycle"]["stage"]=="RELEASE",state
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
assert approval.get("actor")=="cedric",approval
assert quorum.get("schema")=="chacha.dev/trust-anchor-quorum/v1",quorum
assert quorum.get("status")=="PASS" and quorum.get("present")>=2 and quorum.get("required")==2,quorum
print("CHACHA_DEV_V639_EXISTING_POST_RELEASE_EVIDENCE=PASS")
print("CHACHA_DEV_V639_EXISTING_POST_RELEASE_ANCHOR_QUORUM=PASS")
print("CHACHA_DEV_V639_EXISTING_PRODUCTION_APPROVAL=PASS")
PY

python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   verify-state --project "$PROJECT" >"$WORK/verify-state-pre.json"
python3 - "$WORK/verify-state-pre.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
print("CHACHA_DEV_V639_RESUME_CONTROL_PLANE_INTEGRITY=PASS")
PY

python3 "$CRYPTO" --policy "$CRYPTO_POLICY" verify   --checkpoint "$SIGNED_CHECKPOINT" --public-key "$PUBLIC_KEY"   | grep -Fq "SIGNATURE_VERIFY=OK"
python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   crypto-verify --project "$PROJECT"   --checkpoint "$SIGNED_CHECKPOINT" --public-key "$PUBLIC_KEY"   >"$WORK/crypto-verify.json"
python3 - "$WORK/crypto-verify.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
print("CHACHA_DEV_V639_EXISTING_POST_RELEASE_CHECKPOINT_VERIFY=PASS")
PY

echo "CHACHA_DEV_V639_RESUME_STAGE=final-production-read"
curl -fsSL "$TARGET_URL" -o "$WORK/site-final.bin"
python3 - "$BUNDLE" "$WORK/site-final.bin" <<'PY'
import hashlib,json,pathlib,sys
b=json.load(open(sys.argv[1],encoding="utf-8"))
digest="sha256:"+hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest()
assert b["target"]["project"]=="wfgg",b
assert b["target"]["branch"]=="main",b
assert b["target"]["url"]=="https://wfgg.pages.dev",b
assert b["content_noop_verified"] is True,b
assert digest==b["site_after"]["sha256"],(digest,b["site_after"]["sha256"])
print("CHACHA_DEV_V639_FINAL_PRODUCTION_CONTENT_STABLE=PASS")
PY

echo "CHACHA_DEV_V639_RESUME_STAGE=release-to-operate-plan"
python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   plan-transition --project "$PROJECT" --target OPERATE   >"$WORK/operate-plan.json"
python3 - "$WORK/operate-plan.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"] in {"OK","READY"},x
assert not (x.get("blockers") or []),x
assert (x.get("details") or {}).get("transition")=="RELEASE->OPERATE",x
print("CHACHA_DEV_V639_RELEASE_TO_OPERATE_READY=PASS")
PY

echo "CHACHA_DEV_V639_RESUME_STAGE=release-to-operate-advance"
python3 "$PC" --policy "$PC_POLICY" --repo-root "$ROOT" --json   advance --project "$PROJECT" --target OPERATE --actor central-orchestrator   >"$WORK/operate-advance.json"
python3 - "$WORK/operate-advance.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x["status"]=="OK",x
assert (x.get("details") or {}).get("transition")=="RELEASE->OPERATE",x
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

echo "CHACHA_DEV_V639_RESUME_WITHOUT_REPLAY=PASS"
echo "CHACHA_DEV_V639_REAL_PRODUCTION_REDEPLOYMENT=NO"
echo "CHACHA_DEV_V639_DIRECT_LEDGER_MUTATION=NO"
echo "CHACHA_DEV_V639_DIRECT_LIFECYCLE_MUTATION=NO"
echo "CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V639_INSTALL=PASS"
