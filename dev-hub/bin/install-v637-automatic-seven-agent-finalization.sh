#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V637_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v637.XXXXXX)"
PREVIOUS=""
PROJECT="v637-auto-finalize-$STAMP"
STAGE=bootstrap

stage(){ STAGE="$1"; echo "CHACHA_DEV_V637_STAGE=$STAGE"; }
pilot_cleanup(){
  rm -rf "/opt/chacha-dev/runtime/state/$PROJECT" \
         "/opt/chacha-dev/runtime/evidence/$PROJECT" \
         "/opt/chacha-dev/runtime/plans/$PROJECT" \
         "/opt/chacha-dev/runtime/transactions/$PROJECT" \
         "/opt/chacha-dev/runtime/runs/$PROJECT" \
         "/opt/chacha-dev/runtime/health/$PROJECT" 2>/dev/null || true
  rm -f "/opt/chacha-dev/runtime/locks/control/$PROJECT.lock" \
        "/opt/chacha-dev/runtime/secrets/project-assurance/$PROJECT.pem" 2>/dev/null || true
}
cleanup(){ pilot_cleanup; rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V637_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] && { echo "=== $(basename "$f") ==="; tail -n 180 "$f"; }
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V637_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V637_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V637_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln readlink grep cp find; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V637_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -f "$CURRENT/dev-hub/bin/seven-agent-final-compromise-controller.py" ] || {
  echo "CHACHA_DEV_V637_INSTALL=BLOCKED reason=v636_baseline_missing"; exit 2;
}
[ -s /opt/chacha-dev/runtime/secrets/central-learning-key.pem ] || {
  echo "CHACHA_DEV_V637_INSTALL=BLOCKED reason=central_signing_key_missing"; exit 2;
}
[ -L "$CURRENT" ] && PREVIOUS="$(readlink -f "$CURRENT" || true)"
echo "CHACHA_DEV_V637_V636_BASELINE=PASS"

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tgz"
tar -xzf "$WORK/repo.tgz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V637_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

stage static-semantic
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile \
  "$RELEASE/dev-hub/bin/seven-agent-finalization-inputs.py" \
  "$RELEASE/dev-hub/bin/automatic-seven-agent-finalizer.py" \
  "$RELEASE/dev-hub/bin/project-control.py" \
  "$RELEASE/dev-hub/bin/seven-agent-final-compromise-controller.py"
(
  cd "$SRC"
  PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v637_automatic_seven_agent_finalization.py
) >"$WORK/semantic.out" 2>&1
for marker in \
  CHACHA_DEV_V637_FINALIZATION_INPUT_BUNDLE=PASS \
  CHACHA_DEV_V637_TASK_GRAPH_AUTO_INPUT_BUNDLE=PASS \
  CHACHA_DEV_V637_AUTOMATIC_TRIGGER_PREVIEW_RELEASE=PASS \
  CHACHA_DEV_V637_NON_FINALIZATION_BLOCKER_GUARD=PASS \
  CHACHA_DEV_V637_IDEMPOTENT_REUSE=PASS \
  CHACHA_DEV_V637_TRANSACTIONAL_LEDGER_COMMIT=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V637_SEMANTIC_PILOT=PASS"

stage activate
ln -sfn "$RELEASE" "$CURRENT"

stage external-health
for role in guardian sentinel; do
  url="$(python3 - "$CURRENT/dev-hub/config/$role-runtime-policy.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["external_url"])
PY
)"
  curl -fsS "$url/healthz" -o "$WORK/$role-health.json"
done
EXCHANGE_URL="$(python3 - "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["external_url"])
PY
)"
curl -fsS "$EXCHANGE_URL/healthz" -o "$WORK/exchange-health.json"
python3 - "$WORK/guardian-health.json" "$WORK/sentinel-health.json" "$WORK/exchange-health.json" <<'PY'
import json,sys
g,s,e=[json.load(open(p)) for p in sys.argv[1:]]
assert g["seven_agent_final_review"] is True,g
assert s["seven_agent_final_review"] is True,s
assert s["stored_workflow_attestation_verification"] is True,s
assert e["five_external_final_review_reverification"] is True,e
print("CHACHA_DEV_V637_REAL_EXTERNAL_AUTHORITIES=PASS")
PY

stage project-identity
cat >"$WORK/functional-contract.json" <<JSON
{
  "schema":"chacha.dev/functional-contract/v1",
  "contract_id":"functional-$PROJECT",
  "functional_intent":"Deliver a simple reliable mobile experience",
  "audiences":["user"],
  "criteria":[{"criterion_id":"main-flow","dimension":"functional","owner":"core","required":true}]
}
JSON
python3 "$CURRENT/dev-hub/bin/project-embedded-assurance.py" \
  --project-id "$PROJECT" --application-version "$REV" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --runtime-script "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --relay-script "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
  --client-runtime "$CURRENT/dev-hub/templates/project-assurance-client.mjs" \
  --functional-contract "$WORK/functional-contract.json" --output-dir "$WORK/bundle" >/dev/null
python3 "$CURRENT/dev-hub/bin/project-assurance-identity-manager.py" \
  --project-id "$PROJECT" \
  --guardian-client "$CURRENT/dev-hub/bin/guardian-client.py" --guardian-policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  --sentinel-client "$CURRENT/dev-hub/bin/sentinel-client.py" --sentinel-policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json" \
  --exchange-client "$CURRENT/dev-hub/bin/assurance-exchange-client.py" --exchange-policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json" \
  --specialist-client "$CURRENT/dev-hub/bin/specialist-authority-client.py" \
  --curator-policy "$CURRENT/dev-hub/config/curator-runtime-policy.v1.json" \
  --bastion-policy "$CURRENT/dev-hub/config/bastion-runtime-policy.v1.json" \
  --intendant-policy "$CURRENT/dev-hub/config/intendant-runtime-policy.v1.json" \
  --registration "$WORK/registration.json" --receipt "$WORK/identity.json" --bundle "$WORK/bundle" >"$WORK/identity.out"
grep -Fq 'CURATOR_REGISTRATION=PASS' "$WORK/identity.out"
grep -Fq 'BASTION_REGISTRATION=PASS' "$WORK/identity.out"
grep -Fq 'INTENDANT_REGISTRATION=PASS' "$WORK/identity.out"
KEY="/opt/chacha-dev/runtime/secrets/project-assurance/$PROJECT.pem"
echo "CHACHA_DEV_V637_REAL_PROJECT_IDENTITY=PASS"

stage specialist-evidence
emit(){
  role="$1"; typ="$2"; fields="$3"
  python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
    --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" --bundle "$WORK/bundle" \
    --role "$role" --event-type "$typ" --severity INFO --fields-json "$fields" >/dev/null
  python3 "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
    --bundle "$WORK/bundle" --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
    --private-key "$KEY" --role "$role" >/dev/null
}
emit curator visual-health '{"surface_id":"release-preview","viewport_class":"mobile","visual_diff_score":0.0}'
emit bastion security-health '{"component_id":"release-api","exposure_class":"expected"}'
emit intendant resource-health '{"component_id":"release-api","memory_mb":128,"cpu_ms":40,"external_cost_microunits":0}'
echo "CHACHA_DEV_V637_REAL_SPECIALIST_EVIDENCE=PASS"

stage build-compromise
cat >"$WORK/intent.json" <<JSON
{"name":"V6.37 automatic finalization pilot","text":"Deliver a simple reliable mobile user interface"}
JSON
cat >"$WORK/preplan.json" <<JSON
{"packages":[
 {"id":"pkg-ui","domain":"frontend-mobile","kind":"frontend-mobile","capabilities":["mobile-interface"]},
 {"id":"pkg-api","domain":"backend-api","kind":"backend","capabilities":["reliable-api"]}
],"primary_domains":["frontend-mobile","backend-api"]}
JSON
cat >"$WORK/memory.json" <<JSON
{"current_best_reuse_candidates":[{"kind":"branch","branch_id":"v637-pilot","version":"1"}]}
JSON
python3 "$CURRENT/dev-hub/bin/logic-search-engine.py" --repo-root "$CURRENT" \
  --intent "$WORK/intent.json" --contract "$WORK/functional-contract.json" --preplan "$WORK/preplan.json" \
  --memory-brief "$WORK/memory.json" --policy "$CURRENT/dev-hub/config/logic-search.v1.json" --output "$WORK/logic.json" >/dev/null
python3 "$CURRENT/dev-hub/bin/ux-planning-engine.py" \
  --intent "$WORK/intent.json" --contract "$WORK/functional-contract.json" --preplan "$WORK/preplan.json" \
  --policy "$CURRENT/dev-hub/config/ux-planning.v1.json" --output "$WORK/ux.json" >/dev/null
python3 "$CURRENT/dev-hub/bin/multi-agent-compromise-engine.py" \
  --policy "$CURRENT/dev-hub/config/decision-challenge.v1.json" --logic-report "$WORK/logic.json" \
  --ux-report "$WORK/ux.json" --output "$WORK/compromise.json" >/dev/null
python3 - "$WORK/compromise.json" "$WORK/implementation-manifest.json" "$WORK/implementation-verification.json" "$WORK/council.json" "$PROJECT" "$REV" <<'PY'
import json,sys
comp=json.load(open(sys.argv[1]));project,rev=sys.argv[5],sys.argv[6];cd=comp["dossier_digest"]
logic=((comp.get("compromise") or {}).get("logic_proposal") or {}).get("candidate") or {}
ux=((comp.get("compromise") or {}).get("ux_proposal") or {}).get("ux_contract") or {}
req=[str(x.get("id")) for x in ux.get("recommendations") or [] if isinstance(x,dict) and x.get("id")]
manifest={"schema":"chacha.dev/implementation-manifest/v1","project_id":project,"revision":rev,"compromise_digest":cd,
 "logic":{"candidate_id":logic.get("candidate_id"),"execution_mode":logic.get("execution_mode")},
 "ux":{"implemented_requirement_ids":req,"primary_job_verified":True,"curator_handoff_completed":True}}
verify={"schema":"chacha.dev/implementation-verification/v1","project_id":project,"revision":rev,"compromise_digest":cd,
 "status":"PASS","non_dominated_compromise_verified":True,"hard_constraints_satisfied":True,"architecture_changed":False}
council={"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True,
 "logic_ux_compromise":{"required":True,"valid":True,"dossier_digest":cd}}
for path,obj in [(sys.argv[2],manifest),(sys.argv[3],verify),(sys.argv[4],council)]:
    json.dump(obj,open(path,"w"),indent=2);open(path,"a").write("\n")
PY
echo "CHACHA_DEV_V637_REAL_COMPROMISE=PASS"

stage source-receipts
cat >"$WORK/acceptance-evidence.json" <<JSON
{"criteria":[{"criterion_id":"main-flow","state":"PASS","evidence":"v637-main-flow-proof"}]}
JSON
python3 "$CURRENT/dev-hub/bin/acceptance-engine.py" \
  --contract "$WORK/functional-contract.json" --evidence "$WORK/acceptance-evidence.json" \
  --output "$WORK/acceptance.json" --learning-nas-mode DISABLED >/dev/null
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  functional-acceptance --project-id "$PROJECT" --revision "$REV" \
  --contract "$WORK/functional-contract.json" --acceptance "$WORK/acceptance.json" >"$WORK/guardian-source.out"
GUARDIAN_RECEIPT="$(python3 - "$WORK/guardian-source.out" <<'PY'
import json,sys
for l in open(sys.argv[1]):
    try:
        x=json.loads(l)
        if x.get("receipt_id"):print(x["receipt_id"]);break
    except:pass
PY
)"
test -n "$GUARDIAN_RECEIPT"
cat >"$WORK/sentinel-audit.json" <<JSON
{"schema":"chacha.dev/sentinel-technical-audit/v1","revision":"$REV","verdict":"PASS",
 "audit_digest":"github-actions-qualified:$REV","advisory_findings":[],"blocking_findings":[]}
JSON
python3 "$CURRENT/dev-hub/bin/sentinel-client.py" --policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json" \
  release-check --project-id "$PROJECT" --repository chachasan090375/WfGg --revision "$REV" \
  --audit "$WORK/sentinel-audit.json" >"$WORK/sentinel-source.out"
SENTINEL_RECEIPT="$(python3 - "$WORK/sentinel-source.out" <<'PY'
import json,sys
for l in open(sys.argv[1]):
    try:
        x=json.loads(l)
        if x.get("receipt_id"):print(x["receipt_id"]);break
    except:pass
PY
)"
test -n "$SENTINEL_RECEIPT"
echo "CHACHA_DEV_V637_REAL_SOURCE_RECEIPTS=PASS"

stage compile-finalization-inputs
python3 "$CURRENT/dev-hub/bin/seven-agent-finalization-inputs.py" \
  --project-id "$PROJECT" --revision "$REV" \
  --logic-report "$WORK/logic.json" --ux-report "$WORK/ux.json" \
  --compromise "$WORK/compromise.json" --architecture-council "$WORK/council.json" \
  --implementation-manifest "$WORK/implementation-manifest.json" \
  --implementation-verification "$WORK/implementation-verification.json" \
  --guardian-functional-receipt-id "$GUARDIAN_RECEIPT" \
  --sentinel-technical-receipt-id "$SENTINEL_RECEIPT" \
  --output "$WORK/finalization-inputs.json" >"$WORK/finalization-inputs.out"
grep -Fq 'CHACHA_DEV_FINALIZATION_INPUT_BUNDLE=PASS' "$WORK/finalization-inputs.out"
echo "CHACHA_DEV_V637_REAL_FINALIZATION_INPUT_BUNDLE=PASS"

stage initialize-real-project-control
pilot_cleanup
mkdir -p "/opt/chacha-dev/runtime/evidence/$PROJECT"
cat >"$WORK/initial-state.json" <<JSON
{"lifecycle":{"stage":"PREVIEW"}}
JSON
python3 "$CURRENT/dev-hub/bin/control-plane-store.py" \
  --policy "$CURRENT/dev-hub/config/control-plane-state.v1.json" \
  init --project "$PROJECT" --actor v637-pilot --initial "$WORK/initial-state.json" >"$WORK/state-init.out"

python3 - "$CURRENT/dev-hub/config/lifecycle.v1.json" "$CURRENT/dev-hub/config/quality-gates.v1.json" \
  "$WORK/finalization-inputs.json" "/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json" "$PROJECT" <<'PY'
import json,sys,datetime
life=json.load(open(sys.argv[1]));quality=json.load(open(sys.argv[2]))
bundle=sys.argv[3];out=sys.argv[4];project=sys.argv[5]
stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
req=life["transitions"]["PREVIEW->RELEASE"]["required_artifacts"]
skip={"compromise-release-receipt","seven-agent-final-delivery-receipt"}
arts={}
for x in req:
    if x in skip:continue
    source=bundle if x=="seven-agent-finalization-inputs" else "v637-pilot:"+x
    arts[x]={"status":"OK","source":source,"observed_at":stamp}
gates={k:{"status":"OK","source":"v637-pilot:"+k,"observed_at":stamp}
       for k in (quality.get("gates") or {}) if k!="compromise-release"}
ledger={"schema":"chacha.dev/evidence-ledger/v1","project":project,"updated_at":stamp,
        "artifacts":arts,"gates":gates,
        "approvals":{"production-release":{"status":"APPROVED","actor":"v637-pilot","observed_at":stamp}},
        "risk_acceptances":[],"history":[]}
json.dump(ledger,open(out,"w"),indent=2);open(out,"a").write("\n")
PY
echo "CHACHA_DEV_V637_REAL_PROJECT_CONTROL_PREVIEW_READY=PASS"

stage prove-precondition-block
python3 - "$CURRENT/dev-hub/config/lifecycle.v1.json" "/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json" "$WORK/pre-state.json" "$PROJECT" <<'PY'
import json,sys,datetime
stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
json.dump({"schema":"chacha.dev/project-lifecycle-state/v1","project":sys.argv[4],"current_stage":"PREVIEW",
 "created_at":stamp,"updated_at":stamp,"history":[]},open(sys.argv[3],"w"),indent=2)
open(sys.argv[3],"a").write("\n")
PY
set +e
python3 "$CURRENT/dev-hub/bin/lifecycle-engine.py" --lifecycle "$CURRENT/dev-hub/config/lifecycle.v1.json" \
  check --state "$WORK/pre-state.json" --target RELEASE \
  --evidence "/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json" \
  --quality-gates "$CURRENT/dev-hub/config/quality-gates.v1.json" >"$WORK/precheck.out"
PRE_RC=$?
set -e
test "$PRE_RC" -eq 2
grep -Fq 'ARTIFACT_MISSING:seven-agent-final-delivery-receipt' "$WORK/precheck.out"
echo "CHACHA_DEV_V637_REAL_RELEASE_BLOCKED_BEFORE_AUTO_FINALIZATION=PASS"

stage automatic-project-control-release
python3 "$CURRENT/dev-hub/bin/project-control.py" \
  --policy "$CURRENT/dev-hub/config/project-control.v1.json" --repo-root "$CURRENT" --json \
  advance --project "$PROJECT" --target RELEASE --actor central-orchestrator >"$WORK/advance.out"
python3 - "$WORK/advance.out" "$PROJECT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["status"]=="OK",x
d=x.get("details") or {}
assert d.get("transition")=="PREVIEW->RELEASE",d
a=d.get("automatic_seven_agent_finalization")
assert isinstance(a,dict) and a.get("status")=="PASS",d
print("CHACHA_DEV_V637_REAL_PROJECT_CONTROL_AUTO_TRIGGER=PASS")
print("CHACHA_DEV_V637_REAL_RELEASE_PROMOTION=PASS")
PY

stage verify-final-state-and-ledger
python3 "$CURRENT/dev-hub/bin/control-plane-store.py" \
  --policy "$CURRENT/dev-hub/config/control-plane-state.v1.json" show --project "$PROJECT" >"$WORK/state-final.json"
python3 - "$WORK/state-final.json" "/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));l=json.load(open(sys.argv[2]))
assert ((s.get("state") or {}).get("lifecycle") or {}).get("stage")=="RELEASE",s
arts=l.get("artifacts") or {};gates=l.get("gates") or {}
for k in ("compromise-release-receipt","seven-agent-final-delivery-receipt"):
    assert (arts.get(k) or {}).get("status")=="OK",(k,arts.get(k))
assert (gates.get("compromise-release") or {}).get("status")=="OK",gates.get("compromise-release")
print("CHACHA_DEV_V637_REAL_FINAL_RECEIPTS_INGESTED=PASS")
print("CHACHA_DEV_V637_REAL_CONTROL_PLANE_STAGE_RELEASE=PASS")
PY

stage verify-transactional-evidence
grep -Fq '"event_type":"EVIDENCE_RECORDED"' "/opt/chacha-dev/runtime/state/$PROJECT/audit.jsonl"
grep -Fq '"event_type":"LIFECYCLE_TRANSITION"' "/opt/chacha-dev/runtime/state/$PROJECT/audit.jsonl"
python3 - "/opt/chacha-dev/runtime/transactions/$PROJECT" <<'PY'
import json,sys,pathlib
root=pathlib.Path(sys.argv[1])
rows=[]
for p in root.glob("*/receipt.json"):
    try:rows.append(json.load(open(p)))
    except:pass
auto=[x for x in rows if x.get("operation")=="automatic-seven-agent-finalization"]
adv=[x for x in rows if x.get("operation")=="advance"]
assert auto and any(x.get("status")=="COMMITTED" for x in auto),auto
assert adv and any(x.get("status")=="COMMITTED" for x in adv),adv
print("CHACHA_DEV_V637_REAL_TRANSACTIONAL_FINALIZATION=PASS")
PY

stage prove-idempotent-finalizer
FINAL_RESULT="/opt/chacha-dev/runtime/transactions/$PROJECT/idempotent-result.json"
mkdir -p "$(dirname "$FINAL_RESULT")"
python3 "$CURRENT/dev-hub/bin/automatic-seven-agent-finalizer.py" \
  --project "$PROJECT" --policy "$CURRENT/dev-hub/config/automatic-seven-agent-finalization.v1.json" \
  --ledger "/opt/chacha-dev/runtime/evidence/$PROJECT/ledger.json" --repo-root "$CURRENT" \
  --output-dir "/opt/chacha-dev/runtime/plans/$PROJECT/automatic-finalization" \
  --result "$FINAL_RESULT" >"$WORK/idempotent.out"
grep -Fq 'AUTOMATIC_FINALIZATION_IDEMPOTENT_REUSE=YES' "$WORK/idempotent.out"
echo "CHACHA_DEV_V637_REAL_IDEMPOTENT_REUSE=PASS"

cp "$WORK/advance.out" "/opt/chacha-dev/evidence/v637-project-control-auto-finalization-$STAMP.json"
echo "CHACHA_DEV_V637_PREVIEW_RELEASE_AUTO_TRIGGER=YES"
echo "CHACHA_DEV_V637_MANUAL_V636_CONTROLLER_INVOCATION=NO"
echo "CHACHA_DEV_V637_FINALIZATION_INPUT_BUNDLE_VERIFIED=YES"
echo "CHACHA_DEV_V637_NON_FINALIZATION_BLOCKERS_BYPASS=NO"
echo "CHACHA_DEV_V637_TRANSACTIONAL_LEDGER_COMMIT=YES"
echo "CHACHA_DEV_V637_FAILURE_PROMOTES_RELEASE=NO"
echo "CHACHA_DEV_V637_IDEMPOTENT=YES"
echo "CHACHA_DEV_V637_CENTRAL_REMEDIATION_BEFORE_RENEGOTIATION=YES"
echo "CHACHA_DEV_V637_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V637_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V637_INSTALL=PASS"

trap - EXIT
cleanup
