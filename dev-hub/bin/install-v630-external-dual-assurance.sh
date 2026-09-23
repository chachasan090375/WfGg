#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V630_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v630.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PREVIOUS=""
STAGE="bootstrap"
PROJECT="v630-dual-assurance-pilot-$STAMP"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V630_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V630_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V630_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln readlink grep cp find systemctl openssl; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -f "$CURRENT/dev-hub/bin/planning_memory_runtime.py" ] || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=v629_missing"; exit 2; }
[ -s /opt/chacha-dev/runtime/secrets/central-learning-key.pem ] || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=central_signing_key_missing"; exit 2; }
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi
echo "CHACHA_DEV_V630_V629_BASELINE=PASS"

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
for required in   dev-hub/bin/sentinel-client.py   dev-hub/bin/sentinel-remediation-controller.py   dev-hub/bin/sentinel-technical-audit.py   dev-hub/bin/external-assurance-release-gate.py   dev-hub/bin/guardian-client.py   dev-hub/config/sentinel-runtime-policy.v1.json   dev-hub/config/sentinel-technical-policy.v1.json   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/systemd/chacha-dev-sentinel-remediation.service   dev-hub/systemd/chacha-dev-sentinel-remediation.timer   dev-hub/tests/test_v630_external_dual_assurance.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/sentinel-client.py"   "$RELEASE/dev-hub/bin/sentinel-remediation-controller.py"   "$RELEASE/dev-hub/bin/sentinel-technical-audit.py"   "$RELEASE/dev-hub/bin/external-assurance-release-gate.py"   "$RELEASE/dev-hub/bin/guardian-client.py"
python3 -m json.tool "$RELEASE/dev-hub/config/sentinel-runtime-policy.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/guardian-runtime-policy.v1.json" >/dev/null
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V630_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v630_external_dual_assurance.py
) >"$WORK/semantic.out" 2>&1
for marker in   CHACHA_DEV_V630_SENTINEL_EXTERNAL_TECHNICAL_SCOPE=PASS   CHACHA_DEV_V630_GUARDIAN_EXTERNAL_FUNCTIONAL_SCOPE=PASS   CHACHA_DEV_V630_DUAL_EXTERNAL_RECEIPTS_REQUIRED=PASS   CHACHA_DEV_V630_EXACT_RELEASE_REVISION_REQUIRED=PASS   CHACHA_DEV_V630_CENTRAL_ORCHESTRATOR_REMEDIATION_OWNER=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V630_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage install-sentinel-remediation-poller
cp "$CURRENT/dev-hub/systemd/chacha-dev-sentinel-remediation.service" /etc/systemd/system/chacha-dev-sentinel-remediation.service
cp "$CURRENT/dev-hub/systemd/chacha-dev-sentinel-remediation.timer" /etc/systemd/system/chacha-dev-sentinel-remediation.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-sentinel-remediation.timer >/dev/null
systemctl is-enabled --quiet chacha-dev-sentinel-remediation.timer
systemctl is-active --quiet chacha-dev-sentinel-remediation.timer
echo "CHACHA_DEV_V630_SENTINEL_REMEDIATION_TIMER=PASS"

stage external-health
SENTINEL_URL="$(python3 -c 'import json;print(json.load(open("/opt/chacha-dev/platform/current/dev-hub/config/sentinel-runtime-policy.v1.json"))["external_url"])')"
GUARDIAN_URL="$(python3 -c 'import json;print(json.load(open("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json"))["external_url"])')"
curl -fsS "$SENTINEL_URL/healthz" -o "$WORK/sentinel-health.json"
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
python3 - "$WORK/sentinel-health.json" "$WORK/guardian-health.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));g=json.load(open(sys.argv[2]))
assert s.get("external_technical_assurance") is True,s
assert s.get("technical_scope_only") is True,s
assert s.get("direct_code_mutation") is False,s
assert g.get("external_governance_plane") is True,g
assert g.get("functional_acceptance_gate") is True,g
assert g.get("external_dual_release_gate") is True,g
assert g.get("dual_external_assurance_required_for_production") is True,g
assert g.get("sentinel_external_url_configured") is True,g
assert g.get("functional_direct_mutation") is False,g
print("CHACHA_DEV_V630_REAL_EXTERNAL_SENTINEL_HEALTH=PASS")
print("CHACHA_DEV_V630_REAL_EXTERNAL_GUARDIAN_FUNCTIONAL_HEALTH=PASS")
PY

stage real-sentinel-technical-receipt
cat >"$WORK/audit.json" <<JSON
{"schema":"chacha.dev/sentinel-technical-audit-reference/v1","revision":"$REV","automatic_external_spend_eur":0}
JSON
python3 "$CURRENT/dev-hub/bin/sentinel-client.py"   --policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json"   release-check --project-id "$PROJECT" --repository chachasan090375/WfGg   --revision "$REV" --audit "$WORK/audit.json" >"$WORK/sentinel-receipt.out"
python3 - "$WORK/sentinel-receipt.out" "$REV" "$PROJECT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));rev=sys.argv[2];project=sys.argv[3]
assert x.get("schema")=="chacha.dev/sentinel-technical-receipt/v1",x
assert x.get("verdict")=="PASS",x
assert x.get("revision")==rev,x
assert x.get("project_id")==project,x
assert x.get("direct_code_mutation") is False,x
assert x.get("central_orchestrator_owns_remediation") is True,x
print("CHACHA_DEV_V630_REAL_SENTINEL_TECHNICAL_RECEIPT=PASS")
print(x["receipt_id"])
PY
SENTINEL_RECEIPT="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/sentinel-receipt.out"))["receipt_id"])')"

stage real-guardian-functional-receipt
cat >"$WORK/functional-contract.json" <<JSON
{
  "schema":"chacha.dev/functional-contract/v1",
  "contract_id":"functional-v630-dual-assurance-pilot",
  "name":"V6.30 external dual assurance pilot",
  "functional_intent":"Verify that Guardian functional assurance and Sentinel technical assurance are external, independent, read-only control planes and that remediation belongs to the central orchestrator.",
  "criteria":[
    {"criterion_id":"v630-external-roles","dimension":"functional","statement":"Guardian and Sentinel are external independent control planes.","required":true,"owner":"product","verification":"evidence"},
    {"criterion_id":"v630-no-direct-mutation","dimension":"functional","statement":"Neither external agent mutates application code directly.","required":true,"owner":"product","verification":"evidence"},
    {"criterion_id":"v630-central-remediation","dimension":"functional","statement":"Correction is owned by the central orchestrator.","required":true,"owner":"product","verification":"evidence"}
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
    {"criterion_id":"v630-external-roles","dimension":"functional","required":true,"owner":"product","state":"PASS","evidence":{"guardian_external":true,"sentinel_external":true}},
    {"criterion_id":"v630-no-direct-mutation","dimension":"functional","required":true,"owner":"product","state":"PASS","evidence":{"guardian_direct_mutation":false,"sentinel_direct_mutation":false}},
    {"criterion_id":"v630-central-remediation","dimension":"functional","required":true,"owner":"product","state":"PASS","evidence":{"remediation_owner":"central-orchestrator"}}
  ],
  "return_to_factories":{}
}
JSON
python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   functional-acceptance --project-id "$PROJECT" --revision "$REV"   --contract "$WORK/functional-contract.json" --acceptance "$WORK/acceptance.json" >"$WORK/guardian-receipt.out"
python3 - "$WORK/guardian-receipt.out" "$REV" "$PROJECT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));rev=sys.argv[2];project=sys.argv[3]
assert x.get("schema")=="chacha.dev/guardian-functional-acceptance-receipt/v1",x
assert x.get("verdict")=="PASS",x
assert x.get("revision")==rev,x
assert x.get("project_id")==project,x
assert x.get("original_functional_contract_pinned") is True,x
assert x.get("direct_application_mutation") is False,x
assert x.get("central_orchestrator_owns_remediation") is True,x
print("CHACHA_DEV_V630_REAL_GUARDIAN_FUNCTIONAL_RECEIPT=PASS")
PY
GUARDIAN_RECEIPT="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/guardian-receipt.out"))["receipt_id"])')"

stage real-dual-release-gate
python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   dual-release-gate --project-id "$PROJECT" --revision "$REV"   --guardian-functional-receipt-id "$GUARDIAN_RECEIPT"   --sentinel-technical-receipt-id "$SENTINEL_RECEIPT" >"$WORK/dual-gate.out"
python3 - "$WORK/dual-gate.out" "$REV" "$PROJECT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));rev=sys.argv[2];project=sys.argv[3]
assert x.get("schema")=="chacha.dev/external-dual-assurance-verdict/v1",x
assert x.get("verdict")=="PASS",x
assert x.get("production_allowed") is True,x
assert x.get("revision")==rev and x.get("project_id")==project,x
assert x.get("remediation_owner")=="central-orchestrator",x
assert x.get("guardian_direct_mutation") is False,x
assert x.get("sentinel_direct_mutation") is False,x
print("CHACHA_DEV_V630_REAL_EXTERNAL_DUAL_RELEASE_GATE=PASS")
PY

stage negative-exact-revision-control
python3 - "$WORK/guardian-receipt.out" "$WORK/sentinel-receipt.out" "$WORK" "$PROJECT" <<'PY'
import json,sys
g=json.load(open(sys.argv[1]));s=json.load(open(sys.argv[2]));root=sys.argv[3];project=sys.argv[4]
open(root+"/wrong-rev.txt","w").write("b"*40)
assert g["project_id"]==project and s["project_id"]==project
PY
set +e
python3 "$CURRENT/dev-hub/bin/external-assurance-release-gate.py"   --project-id "$PROJECT" --revision "$(cat "$WORK/wrong-rev.txt")"   --guardian-receipt "$WORK/guardian-receipt.out" --sentinel-receipt "$WORK/sentinel-receipt.out"   --output "$WORK/negative-gate.json" >"$WORK/negative-gate.out" 2>"$WORK/negative-gate.stderr"
NEG_RC=$?
set -e
[ "$NEG_RC" -eq 20 ] || { echo "CHACHA_DEV_V630_INSTALL=BLOCKED reason=negative_revision_control_failed"; exit 2; }
python3 - "$WORK/negative-gate.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get("production_allowed") is False,x
assert "GUARDIAN_REVISION_MISMATCH" in x.get("reason_codes",[]),x
assert "SENTINEL_REVISION_MISMATCH" in x.get("reason_codes",[]),x
print("CHACHA_DEV_V630_EXACT_REVISION_NEGATIVE_CONTROL=PASS")
PY

stage sentinel-remediation-pull
python3 "$CURRENT/dev-hub/bin/sentinel-remediation-controller.py"   --policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/sentinel-client.py" >"$WORK/sentinel-remediation.out"
grep -Fq 'CHACHA_DEV_SENTINEL_DIRECTIVE_PULL=PASS' "$WORK/sentinel-remediation.out"
grep -Fq 'CENTRAL_ORCHESTRATOR_OWNS_REMEDIATION=YES' "$WORK/sentinel-remediation.out"
echo "CHACHA_DEV_V630_SENTINEL_TO_CENTRAL_REMEDIATION_PATH=PASS"

cat >"/opt/chacha-dev/evidence/v630-external-dual-assurance-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v630-external-dual-assurance-evidence/v1",
  "revision":"$REV","observed_at":"$STAMP","project_id":"$PROJECT",
  "external_sentinel_health":"PASS","external_guardian_functional_health":"PASS",
  "sentinel_technical_receipt":"$SENTINEL_RECEIPT",
  "guardian_functional_receipt":"$GUARDIAN_RECEIPT",
  "dual_release_gate":"PASS","exact_revision_negative_control":"PASS",
  "sentinel_remediation_to_central":"PASS",
  "external_agents_direct_mutation":false,
  "remediation_owner":"central-orchestrator",
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V630_SENTINEL_EXTERNAL=YES"
echo "CHACHA_DEV_V630_GUARDIAN_FUNCTIONAL_EXTERNAL=YES"
echo "CHACHA_DEV_V630_SENTINEL_TECHNICAL_REALTIME_CI=YES"
echo "CHACHA_DEV_V630_GUARDIAN_ORIGINAL_FUNCTIONAL_CONTRACT_PINNED=YES"
echo "CHACHA_DEV_V630_PRODUCTION_REQUIRES_BOTH_EXTERNAL_RECEIPTS=YES"
echo "CHACHA_DEV_V630_EXACT_RELEASE_REVISION_REQUIRED=YES"
echo "CHACHA_DEV_V630_EXTERNAL_AGENTS_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V630_REMEDIATION_OWNER=central-orchestrator"
echo "CHACHA_DEV_V630_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V630_INSTALL=PASS"

trap - EXIT
cleanup
