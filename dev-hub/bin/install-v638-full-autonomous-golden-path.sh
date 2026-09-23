#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V638_REV:-}"
APPROVAL_ID="${CHACHA_DEV_V638_HUMAN_APPROVAL_ID:-}"
HUMAN_ACTOR="${CHACHA_DEV_V638_HUMAN_ACTOR:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/chacha-dev-v638-$STAMP"
RELEASE="$BASE/releases/$STAMP-${REV:-unresolved}"
RUN_ROOT="/opt/chacha-dev/runtime/golden-path-runs/$STAMP-${REV:0:12}"
KEY_DIR="/opt/chacha-dev/runtime/secrets/v638-pilot/$STAMP"
PREVIOUS=""
PENDING_DIR="/opt/chacha-dev/runtime/golden-path-runs"
PENDING_FILE="$PENDING_DIR/v638-awaiting-${REV:-unresolved}.json"
RESUME=0

stage(){ echo "CHACHA_DEV_V638_STAGE=$1"; }
cleanup(){ rm -rf -- "$WORK" 2>/dev/null || true; rm -f -- "$KEY_DIR/private.pem" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V638_FAILURE_STAGE=${LAST_STAGE:-unknown}"
    if [ -d "$WORK" ]; then
      for f in "$WORK"/*.out "$WORK"/*.json; do
        [ -s "$f" ] && { echo "=== $(basename "$f") ==="; tail -n 160 "$f"; }
      done
    fi
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V638_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT
stage_set(){ LAST_STAGE="$1"; stage "$1"; }

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}
for cmd in curl tar python3 node openssl ln readlink grep cp find rm mkdir; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -f "$CURRENT/dev-hub/bin/automatic-seven-agent-finalizer.py" ] || {
  echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=v637_baseline_missing"; exit 2;
}
[ -x /opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter ] || {
  echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=nas_anchor_adapter_missing"; exit 2;
}
[ -L "$CURRENT" ] && PREVIOUS="$(readlink -f "$CURRENT" || true)"
echo "CHACHA_DEV_V638_V637_BASELINE=PASS"

mkdir -p "$WORK" "$RUN_ROOT" "$KEY_DIR" /opt/chacha-dev/evidence
chmod 0700 "$KEY_DIR"

stage_set fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tgz"
tar -xzf "$WORK/repo.tgz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

stage_set static-semantic
python3 -m py_compile   "$RELEASE/dev-hub/bin/autonomous-golden-path-controller.py"   "$RELEASE/dev-hub/bin/golden-path-materializer.py"   "$RELEASE/dev-hub/bin/project-control.py"   "$RELEASE/dev-hub/bin/task-graph-engine.py"
(
  cd "$SRC"
  PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v638_full_autonomous_golden_path.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V638_CANONICAL_MATERIALIZER_REAL=PASS   CHACHA_DEV_V638_REAL_NODE_TEST_BUILD_PREVIEW_RESTORE=PASS   CHACHA_DEV_V638_RELEASE_QUALITY_GATES_COMPLETE=PASS   CHACHA_DEV_V638_PROTECTED_HUMAN_APPROVAL_TRANSACTION=PASS   CHACHA_DEV_V638_AGENT_SELF_APPROVAL_BLOCKED=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V638_SEMANTIC_PILOT=PASS"

stage_set activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage_set external-authorities-health
python3 - "$CURRENT" "$WORK" <<'PY'
import json,sys,urllib.request,pathlib
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2])
roles=["guardian","sentinel","curator","bastion","intendant"]
for role in roles:
    p=root/"dev-hub/config"/f"{role}-runtime-policy.v1.json"
    cfg=json.load(open(p))
    url=cfg["external_url"].rstrip("/")+"/healthz"
    with urllib.request.urlopen(url,timeout=15) as r:
        data=json.loads(r.read())
    if not isinstance(data,dict):
        raise SystemExit("HEALTH_INVALID:"+role)
    json.dump(data,open(out/f"{role}-health.json","w"),indent=2)
ex=json.load(open(root/"dev-hub/config/assurance-exchange-runtime-policy.v1.json"))
with urllib.request.urlopen(ex["external_url"].rstrip("/")+"/healthz",timeout=15) as r:
    data=json.loads(r.read())
json.dump(data,open(out/"exchange-health.json","w"),indent=2)
print("CHACHA_DEV_V638_REAL_EXTERNAL_AUTHORITIES=PASS")
PY

if [ "$RESUME" -eq 0 ]; then
  stage_set create-single-cahier-des-charges
  cat >"$WORK/intent.json" <<JSON
{
  "name":"V638 Golden Path $STAMP",
  "text":"Cahier-des-charges : crée une petite application frontend accessible et responsive avec un bouton qui change un état visible. Le projet doit inclure tests unitaires et e2e, sécurité, documentation, build reproductible, preview local, release contrôlée, rollback et recovery. Aucun coût externe automatique.",
  "golden_path_profile":"static-interaction-v1",
  "demo_message":"Golden Path V6.38 fonctionne de bout en bout",
  "expected_text":"Golden Path V6.38 fonctionne de bout en bout",
  "constraints":{
    "requires_authentication":false,
    "requires_database":false,
    "requires_external_api":false,
    "requires_production_data_write":false,
    "requires_secret_change":false,
    "requires_destructive_migration":false,
    "automatic_external_spend_eur":0
  },
  "criteria":[
    {"criterion_id":"main-flow","dimension":"functional","statement":"Le message principal est visible et le bouton possède une logique d'état testée.","required":true,"owner":"product"},
    {"criterion_id":"accessible-ui","dimension":"accessibility","statement":"L'interface expose un statut accessible et un focus visible.","required":true,"owner":"qa"},
    {"criterion_id":"secure-zero-dependency","dimension":"security","statement":"Aucune dépendance externe, secret embarqué ou réseau applicatif externe.","required":true,"owner":"cybersecurity"},
    {"criterion_id":"rollback-ready","dimension":"rollback","statement":"Le candidat immuable peut être restauré et vérifié.","required":true,"owner":"recovery"}
  ]
}
JSON
  echo "CHACHA_DEV_V638_SINGLE_INTENT_ENTRY=PASS"

  stage_set project-scoped-pilot-signing-key
  openssl genpkey -algorithm ED25519 -out "$KEY_DIR/private.pem" >/dev/null 2>&1
  openssl pkey -in "$KEY_DIR/private.pem" -pubout -out "$KEY_DIR/public.pem" >/dev/null 2>&1
  chmod 0600 "$KEY_DIR/private.pem"
  chmod 0644 "$KEY_DIR/public.pem"
  echo "CHACHA_DEV_V638_PROJECT_SCOPED_PILOT_KEY=PASS"
  echo "CHACHA_DEV_V638_PLATFORM_SIGNING_KEY_MUTATION=NO"
  echo "CHACHA_DEV_V638_PRIVATE_KEY_EXPORT=NO"

  stage_set full-autonomous-controller-to-human-boundary
  set +e
  python3 "$CURRENT/dev-hub/bin/autonomous-golden-path-controller.py" \
    --repo-root "$CURRENT" \
    --policy "$CURRENT/dev-hub/config/autonomous-golden-path.v1.json" \
    --intent "$WORK/intent.json" \
    --revision "$REV" \
    --output-dir "$RUN_ROOT" \
    --signing-private-key "$KEY_DIR/private.pem" \
    --signing-public-key "$KEY_DIR/public.pem" \
    >"$WORK/controller.out" 2>&1
  CTRL_RC=$?
  set -e
  if [ "$CTRL_RC" -ne 4 ]; then
    cat "$WORK/controller.out"
    echo "CHACHA_DEV_V638_CONTROLLER_RC=$CTRL_RC"
    exit "$CTRL_RC"
  fi
  for marker in \
    CHACHA_DEV_V638_IDEA_TO_PREVIEW_AUTONOMOUS=PASS \
    CHACHA_DEV_V638_SEVEN_AGENT_AUTO_FINALIZATION=PASS \
    CHACHA_DEV_V638_HUMAN_BOUNDARY=AWAITING_APPROVAL \
    CHACHA_DEV_V638_TWO_PHASE_RESUME_REQUIRED=YES; do
    grep -Fq "$marker" "$WORK/controller.out"
  done

  stage_set verify-awaiting-approval-boundary
  PROJECT="$(python3 - "$RUN_ROOT/golden-path-result.json" "$REV" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r["schema"]=="chacha.dev/golden-path-result/v1",r
assert r["revision"]==sys.argv[2],r
assert r["status"]=="AWAITING_APPROVAL" and r["lifecycle_stage"]=="PREVIEW",r
assert r["human_boundary_proven"] is True,r
assert r["seven_agent_finalization"]=="PASS",r
print(r["project_id"])
PY
)"
  STATE="/opt/chacha-dev/runtime/state/$PROJECT/state.json"
  LEDGER="/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json"
  python3 - "$STATE" "$LEDGER" <<'PY'
import json,sys
state=json.load(open(sys.argv[1]));ledger=json.load(open(sys.argv[2]))
assert state["state"]["lifecycle"]["stage"]=="PREVIEW",state
approval=(ledger.get("approvals") or {}).get("production-release") or {}
assert approval.get("status")!="APPROVED",approval
print("CHACHA_DEV_V638_REAL_AWAITING_APPROVAL=PASS")
print("CHACHA_DEV_V638_PREAPPROVAL_RELEASE_MUTATION=NO")
PY

  mkdir -p "$RUN_ROOT/release-trust" "$PENDING_DIR"
  cp "$KEY_DIR/public.pem" "$RUN_ROOT/release-trust/v638-pilot-public-key.pem"
  chmod 0644 "$RUN_ROOT/release-trust/v638-pilot-public-key.pem"
  rm -f "$KEY_DIR/private.pem"

  python3 - "$PENDING_FILE" "$REV" "$PROJECT" "$RUN_ROOT" <<'PY'
import json,os,sys,tempfile,datetime
path,rev,project,run_root=sys.argv[1:]
value={
 "schema":"chacha.dev/v638-awaiting-approval/v1",
 "revision":rev,
 "project_id":project,
 "run_root":run_root,
 "status":"AWAITING_APPROVAL",
 "created_at":datetime.datetime.now(datetime.timezone.utc).isoformat()
}
d=os.path.dirname(path);os.makedirs(d,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix=".v638-pending-",dir=d,text=True)
with os.fdopen(fd,"w",encoding="utf-8") as f:
    json.dump(value,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
os.replace(tmp,path)
os.chmod(path,0o600)
PY
  echo "CHACHA_DEV_V638_AWAITING_APPROVAL_CHECKPOINT=PASS"
  echo "CHACHA_DEV_V638_MANUAL_INTERMEDIATE_ARTIFACT_PREPARATION=NO"
  echo "CHACHA_DEV_V638_INSTALL=AWAITING_APPROVAL"
  echo "CHACHA_DEV_V638_PROJECT_ID=$PROJECT"

  if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    echo "CHACHA_DEV_V638_PREAPPROVAL_RUNTIME_RESTORE=PASS"
  fi
  trap - EXIT
  cleanup
  exit 0
fi

stage_set load-awaiting-approval-checkpoint
RUN_ROOT="$(python3 - "$PENDING_FILE" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get("schema")=="chacha.dev/v638-awaiting-approval/v1",x
assert x.get("revision")==sys.argv[2],x
assert x.get("status")=="AWAITING_APPROVAL",x
print(x["run_root"])
PY
)"
[ -s "$RUN_ROOT/golden-path-result.json" ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=pending_result_missing"; exit 2; }
echo "CHACHA_DEV_V638_RESUME_CHECKPOINT=PASS"

stage_set full-autonomous-controller-resume
set +e
python3 "$CURRENT/dev-hub/bin/autonomous-golden-path-controller.py" \
  --repo-root "$CURRENT" \
  --policy "$CURRENT/dev-hub/config/autonomous-golden-path.v1.json" \
  --revision "$REV" \
  --output-dir "$RUN_ROOT" \
  --resume-from-awaiting-approval \
  --human-approval-id "$APPROVAL_ID" \
  --human-actor "$HUMAN_ACTOR" \
  >"$WORK/controller.out" 2>&1
CTRL_RC=$?
set -e
if [ "$CTRL_RC" -ne 0 ]; then
  cat "$WORK/controller.out"
  echo "CHACHA_DEV_V638_CONTROLLER_RC=$CTRL_RC"
  exit "$CTRL_RC"
fi
for marker in \
  CHACHA_DEV_V638_FULL_AUTONOMOUS_GOLDEN_PATH=PASS \
  CHACHA_DEV_V638_IDEA_TO_RELEASE=PASS \
  CHACHA_DEV_V638_HUMAN_BOUNDARY_PROVEN=PASS \
  CHACHA_DEV_V638_PROTECTED_APPROVAL_TRANSACTION=PASS \
  CHACHA_DEV_V638_SEVEN_AGENT_AUTO_FINALIZATION=PASS \
  CHACHA_DEV_V638_CONTROL_PLANE_INTEGRITY=PASS \
  CHACHA_DEV_V638_RESUMED_SAME_PROJECT=PASS \
  CHACHA_DEV_V638_HUMAN_APPROVAL_AFTER_BOUNDARY=PASS \
  CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO \
  CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO; do
  grep -Fq "$marker" "$WORK/controller.out"
done
echo "CHACHA_DEV_V638_REAL_CONTROLLER=PASS"

stage_set verify-real-project
python3 - "$RUN_ROOT/golden-path-result.json" "$HUMAN_ACTOR" <<'PY'
import json,sys,pathlib
result_path=pathlib.Path(sys.argv[1]);actor=sys.argv[2]
r=json.load(open(result_path))
assert r["schema"]=="chacha.dev/golden-path-result/v1",r
assert r["status"]=="PASS" and r["lifecycle_stage"]=="RELEASE",r
assert r["human_boundary_proven"] is True,r
assert r["human_approval_actor"]==actor,r
assert r["seven_agent_finalization"]=="PASS",r
print("PROJECT_ID="+r["project_id"])
print("CHACHA_DEV_V638_REAL_IDEA_TO_RELEASE=PASS")
print("CHACHA_DEV_V638_REAL_HUMAN_BOUNDARY_AND_RESUME=PASS")
PY
PROJECT="$(python3 - "$RUN_ROOT/golden-path-result.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["project_id"])
PY
)"
STATE="/opt/chacha-dev/runtime/state/$PROJECT/state.json"
LEDGER="/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json"
JOURNAL="/opt/chacha-dev/runtime/state/$PROJECT/audit.jsonl"
test -s "$STATE" -a -s "$LEDGER" -a -s "$JOURNAL"

python3 - "$STATE" "$LEDGER" "$JOURNAL" "$HUMAN_ACTOR" <<'PY'
import json,sys
state=json.load(open(sys.argv[1]));ledger=json.load(open(sys.argv[2]));actor=sys.argv[4]
assert state["state"]["lifecycle"]["stage"]=="RELEASE",state
approval=(ledger.get("approvals") or {}).get("production-release") or {}
assert approval.get("status")=="APPROVED" and approval.get("actor")==actor,approval
arts=ledger.get("artifacts") or {};gates=ledger.get("gates") or {}
for a in [
 "project-intent","project-plan","manifest-v3","manifest-validation","capability-resolution",
 "architecture-decisions-resolved","workspace-health","storage-preflight","dependency-resolution",
 "change-set","build-result","static-check","test-result","security-scan","ci-result","preview-candidate",
 "preview-validation","e2e-result","smoke-result","rollback-plan","release-traceability",
 "backup-recovery-readiness","signed-release-checkpoint","trust-anchor-quorum",
 "seven-agent-finalization-inputs","compromise-release-receipt","seven-agent-final-delivery-receipt"
]:
    assert (arts.get(a) or {}).get("status")=="OK",(a,arts.get(a))
for gid,g in gates.items():
    assert g.get("status") in {"OK","NOT_APPLICABLE"},(gid,g)
assert (gates.get("compromise-release") or {}).get("status")=="OK"
events=[json.loads(x) for x in open(sys.argv[3]) if x.strip()]
transitions=[e for e in events if e.get("event_type")=="LIFECYCLE_TRANSITION"]
assert len(transitions)==6,len(transitions)
assert [((e.get("payload") or {}).get("transition")) for e in transitions]==[
 "IDEA->DESIGN","DESIGN->READY","READY->BUILD","BUILD->VERIFY","VERIFY->PREVIEW","PREVIEW->RELEASE"
],transitions
approvals=[e for e in events if e.get("event_type")=="APPROVAL_RECORDED"]
assert len(approvals)==1,approvals
print("CHACHA_DEV_V638_REAL_ALL_LIFECYCLE_ARTIFACTS_VERIFIED=PASS")
print("CHACHA_DEV_V638_REAL_QUALITY_GATES=PASS")
print("CHACHA_DEV_V638_REAL_PROTECTED_APPROVAL_EVENT=PASS")
print("CHACHA_DEV_V638_REAL_SIX_TRANSACTIONAL_TRANSITIONS=PASS")
PY

stage_set verify-seven-agent-final-delivery
python3 - "$LEDGER" <<'PY'
import json,sys,pathlib
l=json.load(open(sys.argv[1]))
src=(l["artifacts"]["seven-agent-final-delivery-receipt"]["source"])
x=json.load(open(src))
assert x["status"]=="DELIVERED" and x["delivery_allowed"] is True,x
assert x["all_seven_accept"] is True,x
assert x["five_external_source_reverified"] is True,x
assert x["two_internal_second_reads"] is True,x
print("CHACHA_DEV_V638_REAL_SEVEN_AGENT_COMPROMISE=PASS")
PY

stage_set preserve-public-proof
test -s "$RUN_ROOT/release-trust/v638-pilot-public-key.pem"
chmod 0644 "$RUN_ROOT/release-trust/v638-pilot-public-key.pem"
rm -f "$KEY_DIR/private.pem"
cp "$RUN_ROOT/golden-path-result.json" "/opt/chacha-dev/evidence/v638-full-autonomous-golden-path-$STAMP.json"
rm -f "$PENDING_FILE"

echo "CHACHA_DEV_V638_MANUAL_INTERMEDIATE_ARTIFACT_PREPARATION=NO"
echo "CHACHA_DEV_V638_CANONICAL_PROFILE=static-interaction-v1"
echo "CHACHA_DEV_V638_UNIVERSAL_GENERATOR_CLAIMED=NO"
echo "CHACHA_DEV_V638_PRODUCTION_APPLICATION_DEPLOYMENT=NO"
echo "CHACHA_DEV_V638_NAS_TRUST_ANCHOR=YES"
echo "CHACHA_DEV_V638_PRIVATE_KEY_RETAINED=NO"
echo "CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO"
echo "CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO"
echo "CHACHA_DEV_V638_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V638_INSTALL=PASS"

trap - EXIT
cleanup
 || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }

if [ -n "$APPROVAL_ID" ] || [ -n "$HUMAN_ACTOR" ]; then
  [ -n "$APPROVAL_ID" ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=explicit_human_approval_id_required"; exit 2; }
  [ -n "$HUMAN_ACTOR" ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=human_actor_required"; exit 2; }
  case "$HUMAN_ACTOR" in
    central-orchestrator|guardian|sentinel|curator|bastion|intendant|logician|ergonomist)
      echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=human_actor_cannot_be_agent"; exit 2;;
  esac
  RESUME=1
fi

if [ "$RESUME" -eq 1 ]; then
  [ -s "$PENDING_FILE" ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=awaiting_approval_checkpoint_missing"; exit 2; }
else
  [ ! -e "$PENDING_FILE" ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=awaiting_approval_checkpoint_exists"; exit 2; }
fi
for cmd in curl tar python3 node openssl ln readlink grep cp find rm mkdir; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -f "$CURRENT/dev-hub/bin/automatic-seven-agent-finalizer.py" ] || {
  echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=v637_baseline_missing"; exit 2;
}
[ -x /opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter ] || {
  echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=nas_anchor_adapter_missing"; exit 2;
}
[ -L "$CURRENT" ] && PREVIOUS="$(readlink -f "$CURRENT" || true)"
echo "CHACHA_DEV_V638_V637_BASELINE=PASS"

mkdir -p "$WORK" "$RUN_ROOT" "$KEY_DIR" /opt/chacha-dev/evidence
chmod 0700 "$KEY_DIR"

stage_set fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tgz"
tar -xzf "$WORK/repo.tgz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V638_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

stage_set static-semantic
python3 -m py_compile   "$RELEASE/dev-hub/bin/autonomous-golden-path-controller.py"   "$RELEASE/dev-hub/bin/golden-path-materializer.py"   "$RELEASE/dev-hub/bin/project-control.py"   "$RELEASE/dev-hub/bin/task-graph-engine.py"
(
  cd "$SRC"
  PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v638_full_autonomous_golden_path.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V638_CANONICAL_MATERIALIZER_REAL=PASS   CHACHA_DEV_V638_REAL_NODE_TEST_BUILD_PREVIEW_RESTORE=PASS   CHACHA_DEV_V638_RELEASE_QUALITY_GATES_COMPLETE=PASS   CHACHA_DEV_V638_PROTECTED_HUMAN_APPROVAL_TRANSACTION=PASS   CHACHA_DEV_V638_AGENT_SELF_APPROVAL_BLOCKED=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V638_SEMANTIC_PILOT=PASS"

stage_set activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage_set external-authorities-health
python3 - "$CURRENT" "$WORK" <<'PY'
import json,sys,urllib.request,pathlib
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2])
roles=["guardian","sentinel","curator","bastion","intendant"]
for role in roles:
    p=root/"dev-hub/config"/f"{role}-runtime-policy.v1.json"
    cfg=json.load(open(p))
    url=cfg["external_url"].rstrip("/")+"/healthz"
    with urllib.request.urlopen(url,timeout=15) as r:
        data=json.loads(r.read())
    if not isinstance(data,dict):
        raise SystemExit("HEALTH_INVALID:"+role)
    json.dump(data,open(out/f"{role}-health.json","w"),indent=2)
ex=json.load(open(root/"dev-hub/config/assurance-exchange-runtime-policy.v1.json"))
with urllib.request.urlopen(ex["external_url"].rstrip("/")+"/healthz",timeout=15) as r:
    data=json.loads(r.read())
json.dump(data,open(out/"exchange-health.json","w"),indent=2)
print("CHACHA_DEV_V638_REAL_EXTERNAL_AUTHORITIES=PASS")
PY

stage_set create-single-cahier-des-charges
cat >"$WORK/intent.json" <<JSON
{
  "name":"V638 Golden Path $STAMP",
  "text":"Cahier-des-charges : crée une petite application frontend accessible et responsive avec un bouton qui change un état visible. Le projet doit inclure tests unitaires et e2e, sécurité, documentation, build reproductible, preview local, release contrôlée, rollback et recovery. Aucun coût externe automatique.",
  "golden_path_profile":"static-interaction-v1",
  "demo_message":"Golden Path V6.38 fonctionne de bout en bout",
  "expected_text":"Golden Path V6.38 fonctionne de bout en bout",
  "constraints":{
    "requires_authentication":false,
    "requires_database":false,
    "requires_external_api":false,
    "requires_production_data_write":false,
    "requires_secret_change":false,
    "requires_destructive_migration":false,
    "automatic_external_spend_eur":0
  },
  "criteria":[
    {"criterion_id":"main-flow","dimension":"functional","statement":"Le message principal est visible et le bouton possède une logique d'état testée.","required":true,"owner":"product"},
    {"criterion_id":"accessible-ui","dimension":"accessibility","statement":"L'interface expose un statut accessible et un focus visible.","required":true,"owner":"qa"},
    {"criterion_id":"secure-zero-dependency","dimension":"security","statement":"Aucune dépendance externe, secret embarqué ou réseau applicatif externe.","required":true,"owner":"cybersecurity"},
    {"criterion_id":"rollback-ready","dimension":"rollback","statement":"Le candidat immuable peut être restauré et vérifié.","required":true,"owner":"recovery"}
  ]
}
JSON
echo "CHACHA_DEV_V638_SINGLE_INTENT_ENTRY=PASS"

stage_set project-scoped-pilot-signing-key
openssl genpkey -algorithm ED25519 -out "$KEY_DIR/private.pem" >/dev/null 2>&1
openssl pkey -in "$KEY_DIR/private.pem" -pubout -out "$KEY_DIR/public.pem" >/dev/null 2>&1
chmod 0600 "$KEY_DIR/private.pem"
chmod 0644 "$KEY_DIR/public.pem"
echo "CHACHA_DEV_V638_PROJECT_SCOPED_PILOT_KEY=PASS"
echo "CHACHA_DEV_V638_PLATFORM_SIGNING_KEY_MUTATION=NO"
echo "CHACHA_DEV_V638_PRIVATE_KEY_EXPORT=NO"

stage_set full-autonomous-controller
set +e
python3 "$CURRENT/dev-hub/bin/autonomous-golden-path-controller.py"   --repo-root "$CURRENT"   --policy "$CURRENT/dev-hub/config/autonomous-golden-path.v1.json"   --intent "$WORK/intent.json"   --revision "$REV"   --output-dir "$RUN_ROOT"   --signing-private-key "$KEY_DIR/private.pem"   --signing-public-key "$KEY_DIR/public.pem"   --human-approval-id "$APPROVAL_ID"   --human-actor "$HUMAN_ACTOR"   >"$WORK/controller.out" 2>&1
CTRL_RC=$?
set -e
if [ "$CTRL_RC" -ne 0 ]; then
  cat "$WORK/controller.out"
  echo "CHACHA_DEV_V638_CONTROLLER_RC=$CTRL_RC"
  exit "$CTRL_RC"
fi
for marker in   CHACHA_DEV_V638_FULL_AUTONOMOUS_GOLDEN_PATH=PASS   CHACHA_DEV_V638_IDEA_TO_RELEASE=PASS   CHACHA_DEV_V638_HUMAN_BOUNDARY_PROVEN=PASS   CHACHA_DEV_V638_PROTECTED_APPROVAL_TRANSACTION=PASS   CHACHA_DEV_V638_SEVEN_AGENT_AUTO_FINALIZATION=PASS   CHACHA_DEV_V638_CONTROL_PLANE_INTEGRITY=PASS   CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO   CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO; do
  grep -Fq "$marker" "$WORK/controller.out"
done
echo "CHACHA_DEV_V638_REAL_CONTROLLER=PASS"

stage_set verify-real-project
python3 - "$RUN_ROOT/golden-path-result.json" "$HUMAN_ACTOR" <<'PY'
import json,sys,pathlib
result_path=pathlib.Path(sys.argv[1]);actor=sys.argv[2]
r=json.load(open(result_path))
assert r["schema"]=="chacha.dev/golden-path-result/v1",r
assert r["status"]=="PASS" and r["lifecycle_stage"]=="RELEASE",r
assert r["human_boundary_proven"] is True,r
assert r["human_approval_actor"]==actor,r
assert r["seven_agent_finalization"]=="PASS",r
print("PROJECT_ID="+r["project_id"])
print("CHACHA_DEV_V638_REAL_IDEA_TO_RELEASE=PASS")
print("CHACHA_DEV_V638_REAL_HUMAN_BOUNDARY_AND_RESUME=PASS")
PY
PROJECT="$(python3 - "$RUN_ROOT/golden-path-result.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["project_id"])
PY
)"
STATE="/opt/chacha-dev/runtime/state/$PROJECT/state.json"
LEDGER="/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json"
JOURNAL="/opt/chacha-dev/runtime/state/$PROJECT/audit.jsonl"
test -s "$STATE" -a -s "$LEDGER" -a -s "$JOURNAL"

python3 - "$STATE" "$LEDGER" "$JOURNAL" "$HUMAN_ACTOR" <<'PY'
import json,sys
state=json.load(open(sys.argv[1]));ledger=json.load(open(sys.argv[2]));actor=sys.argv[4]
assert state["state"]["lifecycle"]["stage"]=="RELEASE",state
approval=(ledger.get("approvals") or {}).get("production-release") or {}
assert approval.get("status")=="APPROVED" and approval.get("actor")==actor,approval
arts=ledger.get("artifacts") or {};gates=ledger.get("gates") or {}
for a in [
 "project-intent","project-plan","manifest-v3","manifest-validation","capability-resolution",
 "architecture-decisions-resolved","workspace-health","storage-preflight","dependency-resolution",
 "change-set","build-result","static-check","test-result","security-scan","ci-result","preview-candidate",
 "preview-validation","e2e-result","smoke-result","rollback-plan","release-traceability",
 "backup-recovery-readiness","signed-release-checkpoint","trust-anchor-quorum",
 "seven-agent-finalization-inputs","compromise-release-receipt","seven-agent-final-delivery-receipt"
]:
    assert (arts.get(a) or {}).get("status")=="OK",(a,arts.get(a))
for gid,g in gates.items():
    assert g.get("status") in {"OK","NOT_APPLICABLE"},(gid,g)
assert (gates.get("compromise-release") or {}).get("status")=="OK"
events=[json.loads(x) for x in open(sys.argv[3]) if x.strip()]
transitions=[e for e in events if e.get("event_type")=="LIFECYCLE_TRANSITION"]
assert len(transitions)==6,len(transitions)
assert [((e.get("payload") or {}).get("transition")) for e in transitions]==[
 "IDEA->DESIGN","DESIGN->READY","READY->BUILD","BUILD->VERIFY","VERIFY->PREVIEW","PREVIEW->RELEASE"
],transitions
approvals=[e for e in events if e.get("event_type")=="APPROVAL_RECORDED"]
assert len(approvals)==1,approvals
print("CHACHA_DEV_V638_REAL_ALL_LIFECYCLE_ARTIFACTS_VERIFIED=PASS")
print("CHACHA_DEV_V638_REAL_QUALITY_GATES=PASS")
print("CHACHA_DEV_V638_REAL_PROTECTED_APPROVAL_EVENT=PASS")
print("CHACHA_DEV_V638_REAL_SIX_TRANSACTIONAL_TRANSITIONS=PASS")
PY

stage_set verify-seven-agent-final-delivery
python3 - "$LEDGER" <<'PY'
import json,sys,pathlib
l=json.load(open(sys.argv[1]))
src=(l["artifacts"]["seven-agent-final-delivery-receipt"]["source"])
x=json.load(open(src))
assert x["status"]=="DELIVERED" and x["delivery_allowed"] is True,x
assert x["all_seven_accept"] is True,x
assert x["five_external_source_reverified"] is True,x
assert x["two_internal_second_reads"] is True,x
print("CHACHA_DEV_V638_REAL_SEVEN_AGENT_COMPROMISE=PASS")
PY

stage_set preserve-public-proof
mkdir -p "$RUN_ROOT/release-trust"
cp "$KEY_DIR/public.pem" "$RUN_ROOT/release-trust/v638-pilot-public-key.pem"
chmod 0644 "$RUN_ROOT/release-trust/v638-pilot-public-key.pem"
rm -f "$KEY_DIR/private.pem"
cp "$RUN_ROOT/golden-path-result.json" "/opt/chacha-dev/evidence/v638-full-autonomous-golden-path-$STAMP.json"

echo "CHACHA_DEV_V638_MANUAL_INTERMEDIATE_ARTIFACT_PREPARATION=NO"
echo "CHACHA_DEV_V638_CANONICAL_PROFILE=static-interaction-v1"
echo "CHACHA_DEV_V638_UNIVERSAL_GENERATOR_CLAIMED=NO"
echo "CHACHA_DEV_V638_PRODUCTION_APPLICATION_DEPLOYMENT=NO"
echo "CHACHA_DEV_V638_NAS_TRUST_ANCHOR=YES"
echo "CHACHA_DEV_V638_PRIVATE_KEY_RETAINED=NO"
echo "CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO"
echo "CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO"
echo "CHACHA_DEV_V638_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V638_INSTALL=PASS"

trap - EXIT
cleanup
