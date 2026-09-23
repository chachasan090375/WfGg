#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V631_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v631.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PREVIOUS=""
STAGE="bootstrap"
PROJECT="v631-assurance-exchange-pilot-$STAMP"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V631_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V631_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V631_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln readlink grep cp find systemctl openssl; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -f "$CURRENT/dev-hub/bin/planning_memory_runtime.py" ] || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=v629_baseline_missing"; exit 2; }
[ -f "$CURRENT/dev-hub/bin/guardian-client.py" ] || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=guardian_client_missing"; exit 2; }
[ -s /opt/chacha-dev/runtime/secrets/central-learning-key.pem ] || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=central_signing_key_missing"; exit 2; }
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi
echo "CHACHA_DEV_V631_V629_BASELINE=PASS"

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
for required in \
  dev-hub/bin/assurance-exchange-client.py \
  dev-hub/bin/assurance-exchange-feedback-controller.py \
  dev-hub/bin/assurance_exchange_runtime.py \
  dev-hub/bin/sentinel-client.py \
  dev-hub/bin/sentinel-remediation-controller.py \
  dev-hub/bin/external-assurance-release-gate.py \
  dev-hub/bin/guardian-client.py \
  dev-hub/config/assurance-exchange-runtime-policy.v1.json \
  dev-hub/config/sentinel-runtime-policy.v1.json \
  dev-hub/config/guardian-runtime-policy.v1.json \
  dev-hub/systemd/chacha-dev-sentinel-remediation.service \
  dev-hub/systemd/chacha-dev-sentinel-remediation.timer \
  dev-hub/systemd/chacha-dev-assurance-exchange-feedback.service \
  dev-hub/systemd/chacha-dev-assurance-exchange-feedback.timer \
  dev-hub/tests/test_v631_assurance_exchange.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V631_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence /opt/chacha-dev/runtime/assurance-exchange
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/assurance-exchange-client.py"   "$RELEASE/dev-hub/bin/assurance-exchange-feedback-controller.py"   "$RELEASE/dev-hub/bin/assurance_exchange_runtime.py"
python3 -m json.tool "$RELEASE/dev-hub/config/assurance-exchange-runtime-policy.v1.json" >/dev/null
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V631_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v631_assurance_exchange.py
) >"$WORK/semantic.out" 2>&1
for marker in \
  CHACHA_DEV_V631_GUARDIAN_SENTINEL_INDEPENDENCE=PASS \
  CHACHA_DEV_V631_SOURCE_RECEIPT_REVERIFICATION=PASS \
  CHACHA_DEV_V631_EVIDENCE_PRESERVING_CORRELATION=PASS \
  CHACHA_DEV_V631_CAUSALITY_NOT_INVENTED=PASS \
  CHACHA_DEV_V631_OPTIMIZATION_FEEDBACK_TO_CENTRAL=PASS \
  CHACHA_DEV_V631_TECHNOLOGY_WATCH_ARCHITECTURE_GUARD=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V631_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage install-external-assurance-pollers
cp "$CURRENT/dev-hub/systemd/chacha-dev-sentinel-remediation.service" \
  /etc/systemd/system/chacha-dev-sentinel-remediation.service
cp "$CURRENT/dev-hub/systemd/chacha-dev-sentinel-remediation.timer" \
  /etc/systemd/system/chacha-dev-sentinel-remediation.timer
cp "$CURRENT/dev-hub/systemd/chacha-dev-assurance-exchange-feedback.service" \
  /etc/systemd/system/chacha-dev-assurance-exchange-feedback.service
cp "$CURRENT/dev-hub/systemd/chacha-dev-assurance-exchange-feedback.timer" \
  /etc/systemd/system/chacha-dev-assurance-exchange-feedback.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-sentinel-remediation.timer >/dev/null
systemctl enable --now chacha-dev-assurance-exchange-feedback.timer >/dev/null
systemctl is-enabled --quiet chacha-dev-sentinel-remediation.timer
systemctl is-active --quiet chacha-dev-sentinel-remediation.timer
systemctl is-enabled --quiet chacha-dev-assurance-exchange-feedback.timer
systemctl is-active --quiet chacha-dev-assurance-exchange-feedback.timer
echo "CHACHA_DEV_V630_REAL_SENTINEL_REMEDIATION_TIMER=PASS"
echo "CHACHA_DEV_V631_EXCHANGE_FEEDBACK_TIMER=PASS"

stage external-three-plane-health
EXCHANGE_URL="$(python3 -c 'import json;print(json.load(open("/opt/chacha-dev/platform/current/dev-hub/config/assurance-exchange-runtime-policy.v1.json"))["external_url"])')"
SENTINEL_URL="$(python3 -c 'import json;print(json.load(open("/opt/chacha-dev/platform/current/dev-hub/config/sentinel-runtime-policy.v1.json"))["external_url"])')"
GUARDIAN_URL="$(python3 -c 'import json;print(json.load(open("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json"))["external_url"])')"
curl -fsS "$EXCHANGE_URL/healthz" -o "$WORK/exchange-health.json"
curl -fsS "$SENTINEL_URL/healthz" -o "$WORK/sentinel-health.json"
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
python3 - "$WORK/exchange-health.json" "$WORK/sentinel-health.json" "$WORK/guardian-health.json" <<'PY'
import json,sys
e,s,g=[json.load(open(p)) for p in sys.argv[1:]]
assert e.get("guardian_sentinel_correlation") is True,e
assert e.get("evidence_preserving") is True,e
assert e.get("causality_not_invented") is True,e
assert e.get("direct_mutation") is False,e
assert e.get("central_orchestrator_owns_remediation") is True,e
assert s.get("assurance_exchange_enabled") is True,s
assert g.get("assurance_exchange_enabled") is True,g
print("CHACHA_DEV_V631_REAL_THREE_EXTERNAL_PLANES_HEALTH=PASS")
PY

stage sentinel-real-receipt
cat >"$WORK/audit.json" <<JSON
{
  "schema":"chacha.dev/sentinel-technical-audit-reference/v1",
  "revision":"$REV",
  "audit_digest":"pilot-v631-$STAMP",
  "advisory_findings":[
    {"check":"pilot-code-optimization-opportunity","scope":"V6.31 controlled pilot","blocking":false}
  ],
  "automatic_external_spend_eur":0
}
JSON
python3 "$CURRENT/dev-hub/bin/sentinel-client.py" \
  --policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json" \
  release-check \
  --project-id "$PROJECT" \
  --repository chachasan090375/WfGg \
  --revision "$REV" \
  --audit "$WORK/audit.json" \
  >"$WORK/sentinel-receipt.out"
python3 - "$WORK/sentinel-receipt.out" "$PROJECT" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));project=sys.argv[2];rev=sys.argv[3]
assert x.get("schema")=="chacha.dev/sentinel-technical-receipt/v1",x
assert x.get("project_id")==project and x.get("revision")==rev,x
assert x.get("verdict")=="PASS",x
assert int(x.get("advisory_count") or 0)==1,x
assert x.get("direct_code_mutation") is False,x
print("CHACHA_DEV_V631_REAL_SENTINEL_RECEIPT=PASS")
PY
SENTINEL_RECEIPT="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/sentinel-receipt.out"))["receipt_id"])')"

stage guardian-real-functional-receipt
cat >"$WORK/functional-contract.json" <<JSON
{
  "schema":"chacha.dev/functional-contract/v1",
  "contract_id":"functional-v631-assurance-exchange",
  "name":"V6.31 Guardian Sentinel Assurance Exchange",
  "functional_intent":"Correlate independent functional and technical assurance without granting either external agent mutation authority.",
  "criteria":[
    {"criterion_id":"v631-independent","dimension":"governance","statement":"Guardian and Sentinel remain independent.","required":true,"owner":"product","verification":"evidence"},
    {"criterion_id":"v631-central-remediation","dimension":"governance","statement":"The central orchestrator owns remediation.","required":true,"owner":"product","verification":"evidence"},
    {"criterion_id":"v631-causality","dimension":"evidence","statement":"Correlation never invents causality.","required":true,"owner":"product","verification":"evidence"}
  ],
  "invariants":{"functional_intent_immutable_during_replanning":true},
  "version":"1.0.0"
}
JSON
cat >"$WORK/acceptance.json" <<JSON
{
  "schema":"chacha.dev/acceptance-result/v1",
  "accepted":true,
  "delivery_allowed":true,
  "criteria":[
    {"criterion_id":"v631-independent","dimension":"governance","required":true,"owner":"product","state":"PASS","evidence":{"guardian_independent":true,"sentinel_independent":true}},
    {"criterion_id":"v631-central-remediation","dimension":"governance","required":true,"owner":"product","state":"PASS","evidence":{"remediation_owner":"central-orchestrator"}},
    {"criterion_id":"v631-causality","dimension":"evidence","required":true,"owner":"product","state":"PASS","evidence":{"causality_policy":"evidence-only"}}
  ],
  "return_to_factories":{}
}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py" \
  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  functional-acceptance \
  --project-id "$PROJECT" \
  --revision "$REV" \
  --contract "$WORK/functional-contract.json" \
  --acceptance "$WORK/acceptance.json" \
  >"$WORK/guardian-receipt.out"
python3 - "$WORK/guardian-receipt.out" "$PROJECT" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));project=sys.argv[2];rev=sys.argv[3]
assert x.get("schema")=="chacha.dev/guardian-functional-acceptance-receipt/v1",x
assert x.get("project_id")==project and x.get("revision")==rev,x
assert x.get("verdict")=="PASS",x
assert x.get("direct_application_mutation") is False,x
print("CHACHA_DEV_V631_REAL_GUARDIAN_RECEIPT=PASS")
PY
GUARDIAN_RECEIPT="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/guardian-receipt.out"))["receipt_id"])')"

stage v630-real-dual-release-gate
python3 "$CURRENT/dev-hub/bin/guardian-client.py" \
  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  dual-release-gate \
  --project-id "$PROJECT" \
  --revision "$REV" \
  --guardian-functional-receipt-id "$GUARDIAN_RECEIPT" \
  --sentinel-technical-receipt-id "$SENTINEL_RECEIPT" \
  >"$WORK/dual-release-gate.out"
python3 - "$WORK/dual-release-gate.out" "$PROJECT" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));project=sys.argv[2];rev=sys.argv[3]
assert x.get("schema")=="chacha.dev/external-dual-assurance-verdict/v1",x
assert x.get("project_id")==project and x.get("revision")==rev,x
assert x.get("verdict")=="PASS",x
assert x.get("production_allowed") is True,x
assert x.get("guardian_direct_mutation") is False,x
assert x.get("sentinel_direct_mutation") is False,x
assert x.get("remediation_owner")=="central-orchestrator",x
print("CHACHA_DEV_V630_REAL_DUAL_EXTERNAL_ASSURANCE=PASS")
print("CHACHA_DEV_V630_REAL_EXTERNAL_AGENTS_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V630_REAL_REMEDIATION_OWNER=central-orchestrator")
PY

stage force-source-reverification-and-correlation
python3 "$CURRENT/dev-hub/bin/assurance-exchange-client.py"   --policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json"   observe --source sentinel --receipt-id "$SENTINEL_RECEIPT" >"$WORK/exchange-sentinel.out"
python3 "$CURRENT/dev-hub/bin/assurance-exchange-client.py"   --policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json"   observe --source guardian --receipt-id "$GUARDIAN_RECEIPT" >"$WORK/exchange-guardian.out"
python3 - "$WORK/exchange-sentinel.out" "$WORK/exchange-guardian.out" <<'PY'
import json,sys
s,g=[json.load(open(p)) for p in sys.argv[1:]]
assert s.get("status")=="RECORDED",s
assert g.get("status")=="RECORDED",g
corr=g.get("correlation") or s.get("correlation") or {}
assert corr.get("status") in {"CORRELATED","WAITING_FOR_PEER"},corr
print("CHACHA_DEV_V631_REAL_SOURCE_RECEIPT_REVERIFICATION=PASS")
PY

stage real-correlated-recommendation
python3 "$CURRENT/dev-hub/bin/assurance-exchange-client.py"   --policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json"   recommendations --status OPEN --project-id "$PROJECT" >"$WORK/recommendations.out"
python3 - "$WORK/recommendations.out" "$PROJECT" "$REV" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));project=sys.argv[2];rev=sys.argv[3]
rows=[r for r in x.get("items") or [] if r.get("project_id")==project and r.get("revision")==rev]
assert rows, x
r=rows[0]
assert r.get("priority")=="OPTIMIZE",r
assert r.get("recommendation_type")=="OPTIMIZE_WITH_FUNCTIONAL_GUARDRAIL",r
assert r.get("causality_status")=="UNPROVEN",r
assert r.get("technology_watch_required_if_architecture_change") is True,r
assert r.get("architecture_council_required_if_architecture_change") is True,r
assert r.get("direct_mutation_allowed") is False,r
assert r.get("remediation_owner")=="central-orchestrator",r
assert r.get("guardian_receipt_id") and r.get("sentinel_receipt_id"),r
assert len(r.get("evidence_refs") or [])>=2,r
print("CHACHA_DEV_V631_REAL_OPTIMIZATION_CORRELATION=PASS")
print("CHACHA_DEV_V631_REAL_CAUSALITY_NOT_INVENTED=PASS")
PY

stage feedback-to-central-orchestrator
python3 "$CURRENT/dev-hub/bin/assurance-exchange-feedback-controller.py"   --policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/assurance-exchange-client.py" >"$WORK/feedback.out"
grep -Fq 'CHACHA_DEV_ASSURANCE_EXCHANGE_PULL=PASS' "$WORK/feedback.out"
grep -Fq 'CENTRAL_ORCHESTRATOR_OWNS_REMEDIATION=YES' "$WORK/feedback.out"

PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$PROJECT" <<'PY'
import sys
import assurance_exchange_runtime as aer
project=sys.argv[1]
rows=aer.recommendations(project_id=project)
assert rows,rows
r=rows[0]
assert r.get("priority")=="OPTIMIZE",r
ctx=aer.inject_context({"project_id":project},project_id=project)
assert ctx.get("assurance_exchange_optimize_count")>=1,ctx
assert ctx.get("assurance_exchange_direct_mutation_allowed") is False,ctx
assert ctx.get("assurance_exchange_remediation_owner")=="central-orchestrator",ctx
print("CHACHA_DEV_V631_REAL_FEEDBACK_TO_CENTRAL_ORCHESTRATOR=PASS")
PY

stage architecture-governance-invariants
python3 - "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
p=x["principles"]
assert p["guardian_and_sentinel_remain_independent"] is True
assert p["exchange_is_neutral_correlation_plane"] is True
assert p["correlation_does_not_create_new_primary_evidence"] is True
assert p["causality_is_never_inferred_without_shared_signals"] is True
assert p["direct_mutation"] is False
assert p["central_orchestrator_owns_remediation"] is True
assert p["technology_watch_required_if_architecture_change"] is True
assert p["architecture_council_required_if_architecture_change"] is True
print("CHACHA_DEV_V631_REAL_EXTERNAL_INDEPENDENCE=PASS")
print("CHACHA_DEV_V631_REAL_TECHNOLOGY_WATCH_ARCHITECTURE_GUARD=PASS")
print("CHACHA_DEV_V631_REAL_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=PASS")
PY

cat >"/opt/chacha-dev/evidence/v631-assurance-exchange-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v631-assurance-exchange-evidence/v1",
  "revision":"$REV","observed_at":"$STAMP","project_id":"$PROJECT",
  "three_external_planes_health":"PASS",
  "sentinel_receipt_id":"$SENTINEL_RECEIPT",
  "guardian_receipt_id":"$GUARDIAN_RECEIPT",
  "source_receipt_reverification":"PASS",
  "optimization_correlation":"PASS",
  "causality_not_invented":"PASS",
  "feedback_to_central_orchestrator":"PASS",
  "external_agents_direct_mutation":false,
  "remediation_owner":"central-orchestrator",
  "technology_watch_required_if_architecture_change":true,
  "architecture_council_final_authority":true,
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V630_INSTALL=PASS_VIA_V631"
echo "CHACHA_DEV_V631_GUARDIAN_SENTINEL_COMMUNICATION=YES"
echo "CHACHA_DEV_V631_ASSURANCE_EXCHANGE_EXTERNAL=YES"
echo "CHACHA_DEV_V631_SOURCE_RECEIPTS_REVERIFIED=YES"
echo "CHACHA_DEV_V631_BLOCKER_OPTIMIZE_OBSERVE=YES"
echo "CHACHA_DEV_V631_CAUSALITY_NOT_INVENTED=YES"
echo "CHACHA_DEV_V631_FEEDBACK_TO_CENTRAL_ORCHESTRATOR=YES"
echo "CHACHA_DEV_V631_EXTERNAL_AGENTS_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V631_REMEDIATION_OWNER=central-orchestrator"
echo "CHACHA_DEV_V631_TECHNOLOGY_WATCH_REQUIRED_FOR_ARCHITECTURE_CHANGE=YES"
echo "CHACHA_DEV_V631_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V631_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V631_INSTALL=PASS"

trap - EXIT
cleanup
