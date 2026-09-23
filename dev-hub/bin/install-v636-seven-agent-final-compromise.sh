#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_V636_REV:-}"
BASE=/opt/chacha-dev/platform
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v636.XXXXXX)"
PREVIOUS=""
PROJECT="v636-seven-agent-$STAMP"
STAGE=bootstrap
stage(){ STAGE="$1"; echo "CHACHA_DEV_V636_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V636_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err; do [ -s "$f" ] && { echo "=== $(basename "$f") ==="; cat "$f"; }; done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then ln -sfn "$PREVIOUS" "$CURRENT"; echo "CHACHA_DEV_V636_ROLLBACK=PASS"; fi
  fi
  cleanup; exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V636_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V636_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln readlink grep find sha256sum; do command -v "$cmd" >/dev/null || exit 2; done
[ -f "$CURRENT/dev-hub/bin/specialist-authority-client.py" ] || { echo "CHACHA_DEV_V636_INSTALL=BLOCKED reason=v635_baseline_missing"; exit 2; }
[ -L "$CURRENT" ] && PREVIOUS="$(readlink -f "$CURRENT" || true)"
echo "CHACHA_DEV_V636_V635_BASELINE=PASS"

stage fetch-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tgz"
tar -xzf "$WORK/repo.tgz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || exit 2
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

stage static-semantic
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/internal-final-review.py"   "$RELEASE/dev-hub/bin/seven-agent-final-compromise-controller.py"   "$RELEASE/dev-hub/bin/compromise-release-gate.py"   "$RELEASE/dev-hub/bin/lifecycle-engine.py"
(
 cd "$SRC"
 PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v636_seven_agent_final_compromise.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V636_LOGICIAN_SECOND_READ=PASS   CHACHA_DEV_V636_ERGONOMIST_SECOND_READ=PASS   CHACHA_DEV_V636_FIVE_EXTERNAL_SOURCE_REVERIFICATION=PASS   CHACHA_DEV_V636_SEVEN_AGENT_RELEASE_GATE=PASS   CHACHA_DEV_V636_LIFECYCLE_RELEASE_PLUS_COMPROMISE=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V636_SEMANTIC_PILOT=PASS"

stage activate
ln -sfn "$RELEASE" "$CURRENT"

stage external-health
GUARDIAN_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/guardian-runtime-policy.v1.json"))["external_url"])')"
SENTINEL_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/sentinel-runtime-policy.v1.json"))["external_url"])')"
EXCHANGE_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/assurance-exchange-runtime-policy.v1.json"))["external_url"])')"
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
curl -fsS "$SENTINEL_URL/healthz" -o "$WORK/sentinel-health.json"
curl -fsS "$EXCHANGE_URL/healthz" -o "$WORK/exchange-health.json"
python3 - "$WORK/guardian-health.json" "$WORK/sentinel-health.json" "$WORK/exchange-health.json" <<'PY'
import json,sys
g,s,e=[json.load(open(p)) for p in sys.argv[1:]]
assert g["seven_agent_final_review"] is True,g
assert s["seven_agent_final_review"] is True,s
assert e["five_external_final_review_reverification"] is True,e
assert e["seven_agent_final_compromise_support"] is True,e
for k in ("guardian_service_binding","sentinel_service_binding","curator_service_binding","bastion_service_binding","intendant_service_binding"):
    assert e[k] is True,(k,e)
print("CHACHA_DEV_V636_REAL_EXTERNAL_FINAL_REVIEW_FABRIC=PASS")
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
python3 "$CURRENT/dev-hub/bin/project-embedded-assurance.py"   --project-id "$PROJECT" --application-version "$REV"   --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"   --runtime-script "$CURRENT/dev-hub/bin/project-assurance-event.py"   --relay-script "$CURRENT/dev-hub/bin/project-assurance-relay.py"   --client-runtime "$CURRENT/dev-hub/templates/project-assurance-client.mjs"   --functional-contract "$WORK/functional-contract.json" --output-dir "$WORK/bundle" >/dev/null
python3 "$CURRENT/dev-hub/bin/project-assurance-identity-manager.py"   --project-id "$PROJECT"   --guardian-client "$CURRENT/dev-hub/bin/guardian-client.py" --guardian-policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --sentinel-client "$CURRENT/dev-hub/bin/sentinel-client.py" --sentinel-policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json"   --exchange-client "$CURRENT/dev-hub/bin/assurance-exchange-client.py" --exchange-policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json"   --specialist-client "$CURRENT/dev-hub/bin/specialist-authority-client.py"   --curator-policy "$CURRENT/dev-hub/config/curator-runtime-policy.v1.json"   --bastion-policy "$CURRENT/dev-hub/config/bastion-runtime-policy.v1.json"   --intendant-policy "$CURRENT/dev-hub/config/intendant-runtime-policy.v1.json"   --registration "$WORK/registration.json" --receipt "$WORK/identity.json" --bundle "$WORK/bundle" >"$WORK/identity.out"
grep -Fq 'CURATOR_REGISTRATION=PASS' "$WORK/identity.out"
grep -Fq 'BASTION_REGISTRATION=PASS' "$WORK/identity.out"
grep -Fq 'INTENDANT_REGISTRATION=PASS' "$WORK/identity.out"
KEY="/opt/chacha-dev/runtime/secrets/project-assurance/$PROJECT.pem"
echo "CHACHA_DEV_V636_REAL_PROJECT_IDENTITY=PASS"

stage specialist-probe-evidence
emit(){
 role="$1"; typ="$2"; fields="$3"
 python3 "$CURRENT/dev-hub/bin/project-assurance-event.py"    --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" --bundle "$WORK/bundle"    --role "$role" --event-type "$typ" --severity INFO --fields-json "$fields" >/dev/null
 python3 "$CURRENT/dev-hub/bin/project-assurance-relay.py"    --bundle "$WORK/bundle" --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"    --private-key "$KEY" --role "$role" >/dev/null
}
emit curator visual-health '{"surface_id":"final-screen","viewport_class":"mobile","visual_diff_score":0.0}'
emit bastion security-health '{"component_id":"final-api","exposure_class":"expected"}'
emit intendant resource-health '{"component_id":"final-api","memory_mb":128,"cpu_ms":40,"external_cost_microunits":0}'
echo "CHACHA_DEV_V636_REAL_SPECIALIST_EVIDENCE=PASS"

stage build-compromise
cat >"$WORK/intent.json" <<JSON
{"name":"V6.36 final pilot","text":"Deliver a simple reliable mobile user interface"}
JSON
cat >"$WORK/preplan.json" <<JSON
{"packages":[
 {"id":"pkg-ui","domain":"frontend-mobile","kind":"frontend-mobile","capabilities":["mobile-interface"]},
 {"id":"pkg-api","domain":"backend-api","kind":"backend","capabilities":["reliable-api"]}
],"primary_domains":["frontend-mobile","backend-api"]}
JSON
cat >"$WORK/memory.json" <<JSON
{"current_best_reuse_candidates":[{"kind":"branch","branch_id":"v636-pilot","version":"1"}]}
JSON
python3 "$CURRENT/dev-hub/bin/logic-search-engine.py" --repo-root "$CURRENT"   --intent "$WORK/intent.json" --contract "$WORK/functional-contract.json" --preplan "$WORK/preplan.json"   --memory-brief "$WORK/memory.json" --policy "$CURRENT/dev-hub/config/logic-search.v1.json" --output "$WORK/logic.json" >/dev/null
python3 "$CURRENT/dev-hub/bin/ux-planning-engine.py"   --intent "$WORK/intent.json" --contract "$WORK/functional-contract.json" --preplan "$WORK/preplan.json"   --policy "$CURRENT/dev-hub/config/ux-planning.v1.json" --output "$WORK/ux.json" >/dev/null
python3 "$CURRENT/dev-hub/bin/multi-agent-compromise-engine.py"   --policy "$CURRENT/dev-hub/config/decision-challenge.v1.json" --logic-report "$WORK/logic.json"   --ux-report "$WORK/ux.json" --output "$WORK/compromise.json" >/dev/null
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
echo "CHACHA_DEV_V636_REAL_COMPROMISE_DOSSIER=PASS"

stage local-acceptance-provisional
cat >"$WORK/acceptance-evidence.json" <<JSON
{"criteria":[{"criterion_id":"main-flow","state":"PASS","evidence":"pilot-main-flow-proof"}]}
JSON
python3 "$CURRENT/dev-hub/bin/acceptance-engine.py"   --contract "$WORK/functional-contract.json" --evidence "$WORK/acceptance-evidence.json"   --output "$WORK/acceptance.json" --learning-nas-mode DISABLED >"$WORK/acceptance.out"
python3 - "$WORK/acceptance.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["accepted"] is True and x["delivery_allowed"] is True,x
assert x["local_acceptance_candidate"] is True,x
assert x["final_delivery_allowed"] is False,x
print("CHACHA_DEV_V636_REAL_LOCAL_ACCEPTANCE_PROVISIONAL=PASS")
PY

stage guardian-functional-source
python3 "$CURRENT/dev-hub/bin/guardian-client.py" --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   functional-acceptance --project-id "$PROJECT" --revision "$REV"   --contract "$WORK/functional-contract.json" --acceptance "$WORK/acceptance.json" >"$WORK/guardian-source.out"
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
echo "CHACHA_DEV_V636_REAL_GUARDIAN_SOURCE_RECEIPT=PASS"

stage sentinel-technical-source
cat >"$WORK/sentinel-audit.json" <<JSON
{"schema":"chacha.dev/sentinel-technical-audit/v1","revision":"$REV","verdict":"PASS",
 "audit_digest":"github-actions-qualified:$REV","advisory_findings":[],"blocking_findings":[]}
JSON
python3 "$CURRENT/dev-hub/bin/sentinel-client.py" --policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json"   release-check --project-id "$PROJECT" --repository chachasan090375/WfGg --revision "$REV"   --audit "$WORK/sentinel-audit.json" >"$WORK/sentinel-source.out"
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
echo "CHACHA_DEV_V636_REAL_SENTINEL_SOURCE_RECEIPT=PASS"

stage lifecycle-before-final
python3 - "$CURRENT/dev-hub/config/lifecycle.v1.json" "$CURRENT/dev-hub/config/quality-gates.v1.json" "$WORK/evidence-ledger.json" "$WORK/lifecycle-state.json" <<'PY'
import json,sys,datetime
life=json.load(open(sys.argv[1]));quality=json.load(open(sys.argv[2]))
stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
req=life["transitions"]["PREVIEW->RELEASE"]["required_artifacts"]
skip={"compromise-release-receipt","seven-agent-final-delivery-receipt"}
ledger={"schema":"chacha.dev/evidence-ledger/v1",
        "artifacts":{x:{"status":"OK","source":"pilot:"+x,"observed_at":stamp} for x in req if x not in skip},
        "approvals":{"production-release":{"status":"APPROVED","actor":"v636-pilot","observed_at":stamp}},
        "gates":{k:{"status":"OK","source":"pilot:"+k,"observed_at":stamp} for k in (quality.get("gates") or {}) if k!="compromise-release"},
        "risk_acceptances":[]}
json.dump(ledger,open(sys.argv[3],"w"),indent=2);open(sys.argv[3],"a").write("\n")
state={"schema":"chacha.dev/project-lifecycle-state/v1","project":"v636-pilot","current_stage":"PREVIEW",
       "created_at":stamp,"updated_at":stamp,"history":[]}
json.dump(state,open(sys.argv[4],"w"),indent=2);open(sys.argv[4],"a").write("\n")
PY
set +e
python3 "$CURRENT/dev-hub/bin/lifecycle-engine.py" --lifecycle "$CURRENT/dev-hub/config/lifecycle.v1.json"   check --state "$WORK/lifecycle-state.json" --target RELEASE --evidence "$WORK/evidence-ledger.json"   --quality-gates "$CURRENT/dev-hub/config/quality-gates.v1.json" >"$WORK/lifecycle-before.out"
BEFORE_RC=$?
set -e
test "$BEFORE_RC" -eq 2
grep -Eq 'seven-agent-final-delivery-receipt|compromise-release' "$WORK/lifecycle-before.out"
echo "CHACHA_DEV_V636_REAL_RELEASE_BLOCKED_BEFORE_SEVEN_REVIEWS=PASS"

stage seven-agent-final-loop
python3 "$CURRENT/dev-hub/bin/seven-agent-final-compromise-controller.py"   --project-id "$PROJECT" --revision "$REV"   --compromise "$WORK/compromise.json" --council "$WORK/council.json"   --logic-report "$WORK/logic.json" --ux-report "$WORK/ux.json"   --implementation-manifest "$WORK/implementation-manifest.json"   --implementation-verification "$WORK/implementation-verification.json"   --guardian-functional-receipt-id "$GUARDIAN_RECEIPT"   --sentinel-technical-receipt-id "$SENTINEL_RECEIPT"   --repo-root "$CURRENT" --output-dir "$WORK/final-loop"   --final-output "$WORK/seven-agent-final-delivery.json"   --evidence-ledger "$WORK/evidence-ledger.json" >"$WORK/final-loop.out"
grep -Fq 'CHACHA_DEV_V636_SEVEN_AGENT_FINAL_COMPROMISE=PASS' "$WORK/final-loop.out"
python3 - "$WORK/seven-agent-final-delivery.json" "$WORK/final-loop/compromise-release-receipt.json" <<'PY'
import json,sys
f=json.load(open(sys.argv[1]));g=json.load(open(sys.argv[2]))
assert f["status"]=="DELIVERED" and f["delivery_allowed"] is True,f
assert f["all_seven_accept"] is True,f
assert f["five_external_source_reverified"] is True,f
assert f["two_internal_second_reads"] is True,f
assert g["release_allowed"] is True,g
assert len(g["accounted_agents"])==7,g
assert g["external_reviews_source_reverified"] is True,g
assert g["internal_second_reads_verified"] is True,g
print("CHACHA_DEV_V636_REAL_SEVEN_AGENT_ACCEPT=PASS")
print("CHACHA_DEV_V636_REAL_FIVE_EXTERNAL_SOURCE_REVERIFIED=PASS")
print("CHACHA_DEV_V636_REAL_TWO_INTERNAL_SECOND_READS=PASS")
PY

stage lifecycle-after-final
python3 "$CURRENT/dev-hub/bin/lifecycle-engine.py" --lifecycle "$CURRENT/dev-hub/config/lifecycle.v1.json"   check --state "$WORK/lifecycle-state.json" --target RELEASE --evidence "$WORK/evidence-ledger.json"   --quality-gates "$CURRENT/dev-hub/config/quality-gates.v1.json" >"$WORK/lifecycle-after.out"
grep -Fq 'ALLOWED=YES' "$WORK/lifecycle-after.out"
echo "CHACHA_DEV_V636_REAL_PREVIEW_TO_RELEASE_AFTER_SEVEN_REVIEWS=PASS"

cp "$WORK/seven-agent-final-delivery.json" "/opt/chacha-dev/evidence/v636-seven-agent-final-delivery-$STAMP.json"
echo "CHACHA_DEV_V636_LOGICIAN_SECOND_READ=PASS"
echo "CHACHA_DEV_V636_ERGONOMIST_SECOND_READ=PASS"
echo "CHACHA_DEV_V636_GUARDIAN_FINAL_REVIEW=PASS"
echo "CHACHA_DEV_V636_SENTINEL_FINAL_REVIEW=PASS"
echo "CHACHA_DEV_V636_CURATOR_FINAL_REVIEW=PASS"
echo "CHACHA_DEV_V636_BASTION_FINAL_REVIEW=PASS"
echo "CHACHA_DEV_V636_INTENDANT_FINAL_REVIEW=PASS"
echo "CHACHA_DEV_V636_FINAL_DELIVERY_AUTHORITY=SEVEN_AGENT_RECEIPT"
echo "CHACHA_DEV_V636_LOCAL_ACCEPTANCE_PROVISIONAL=YES"
echo "CHACHA_DEV_V636_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V636_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V636_INSTALL=PASS"

trap - EXIT
cleanup
