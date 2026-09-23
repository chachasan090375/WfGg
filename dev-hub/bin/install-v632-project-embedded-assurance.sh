#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V632_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v632.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PREVIOUS=""
STAGE="bootstrap"
PROJECT="v632-embedded-assurance-pilot-$STAMP"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V632_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V632_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.stderr; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V632_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln readlink grep cp find openssl; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -f "$CURRENT/dev-hub/bin/assurance_exchange_runtime.py" ] || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=v631_baseline_missing"; exit 2; }
[ -s /opt/chacha-dev/runtime/secrets/central-learning-key.pem ] || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=central_signing_key_missing"; exit 2; }
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi
echo "CHACHA_DEV_V632_V631_BASELINE=PASS"

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }
for required in \
  dev-hub/bin/project-assurance-event.py \
  dev-hub/bin/project-assurance-relay.py \
  dev-hub/bin/project-assurance-identity-manager.py \
  dev-hub/bin/project-embedded-assurance.py \
  dev-hub/bin/project-factory.py \
  dev-hub/bin/project-bootstrap.py \
  dev-hub/bin/autonomous-project-orchestrator.py \
  dev-hub/bin/guardian-client.py \
  dev-hub/bin/sentinel-client.py \
  dev-hub/templates/project-assurance-client.mjs \
  dev-hub/config/project-embedded-assurance.v1.json \
  dev-hub/config/peripheral-assurance-network.v1.json \
  dev-hub/config/project-factory.v1.json \
  dev-hub/config/guardian-runtime-policy.v1.json \
  dev-hub/config/sentinel-runtime-policy.v1.json \
  dev-hub/tests/test_v632_project_embedded_assurance.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence /opt/chacha-dev/runtime/secrets/project-assurance
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile \
  "$RELEASE/dev-hub/bin/project-assurance-event.py" \
  "$RELEASE/dev-hub/bin/project-assurance-relay.py" \
  "$RELEASE/dev-hub/bin/project-assurance-identity-manager.py" \
  "$RELEASE/dev-hub/bin/project-embedded-assurance.py" \
  "$RELEASE/dev-hub/bin/project-factory.py" \
  "$RELEASE/dev-hub/bin/project-bootstrap.py" \
  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
python3 -m json.tool "$RELEASE/dev-hub/config/project-embedded-assurance.v1.json" >/dev/null
python3 -m json.tool "$RELEASE/dev-hub/config/peripheral-assurance-network.v1.json" >/dev/null
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V632_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v632_project_embedded_assurance.py
) >"$WORK/semantic.out" 2>&1
for marker in \
  CHACHA_DEV_V632_EVERY_PROJECT_EMBEDDED_ASSURANCE=PASS \
  CHACHA_DEV_V632_GUARDIAN_LOCAL=PASS \
  CHACHA_DEV_V632_SENTINEL_LOCAL=PASS \
  CHACHA_DEV_V632_PROJECT_SCOPED_IDENTITY=PASS \
  CHACHA_DEV_V632_SERVER_SIDE_RELAY_ONLY=PASS \
  CHACHA_DEV_V632_FIVE_AGENT_NETWORK_RESERVED=PASS \
  CHACHA_DEV_V632_COMMON_ASSURANCE_EXCHANGE=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V632_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage external-authorities-health
GUARDIAN_URL="$(python3 -c 'import json;print(json.load(open("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json"))["external_url"])')"
SENTINEL_URL="$(python3 -c 'import json;print(json.load(open("/opt/chacha-dev/platform/current/dev-hub/config/sentinel-runtime-policy.v1.json"))["external_url"])')"
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
curl -fsS "$SENTINEL_URL/healthz" -o "$WORK/sentinel-health.json"
python3 - "$WORK/guardian-health.json" "$WORK/sentinel-health.json" <<'PY'
import json,sys
g,s=[json.load(open(p)) for p in sys.argv[1:]]
assert g.get("embedded_guardian_local_ingest") is True,g
assert g.get("project_assurance_identity_registration") is True,g
assert g.get("project_event_project_identity_required") is True,g
assert s.get("embedded_sentinel_local_ingest") is True,s
assert s.get("project_assurance_identity_registration") is True,s
assert s.get("project_event_project_identity_required") is True,s
print("CHACHA_DEV_V632_REAL_EXTERNAL_AUTHORITIES_HEALTH=PASS")
PY

stage materialize-real-project-bundle
cat >"$WORK/functional-contract.json" <<JSON
{
  "schema":"chacha.dev/functional-contract/v1",
  "contract_id":"functional-$PROJECT",
  "name":"V6.32 embedded assurance pilot",
  "criteria":[
    {"criterion_id":"guardian-local","required":true},
    {"criterion_id":"sentinel-local","required":true}
  ]
}
JSON
python3 "$CURRENT/dev-hub/bin/project-embedded-assurance.py" \
  --project-id "$PROJECT" \
  --application-version "$REV" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --runtime-script "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --relay-script "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
  --client-runtime "$CURRENT/dev-hub/templates/project-assurance-client.mjs" \
  --functional-contract "$WORK/functional-contract.json" \
  --output-dir "$WORK/bundle" >"$WORK/bundle.out"
grep -Fq 'CHACHA_DEV_PROJECT_EMBEDDED_ASSURANCE=PASS' "$WORK/bundle.out"
echo "CHACHA_DEV_V632_REAL_PROJECT_BUNDLE=PASS"

stage project-scoped-identity
python3 "$CURRENT/dev-hub/bin/project-assurance-identity-manager.py" \
  --project-id "$PROJECT" \
  --guardian-client "$CURRENT/dev-hub/bin/guardian-client.py" \
  --guardian-policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  --sentinel-client "$CURRENT/dev-hub/bin/sentinel-client.py" \
  --sentinel-policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json" \
  --registration "$WORK/project-identity-registration.json" \
  --receipt "$WORK/project-identity-receipt.json" \
  --bundle "$WORK/bundle" >"$WORK/identity.out"
grep -Fq 'CHACHA_DEV_PROJECT_ASSURANCE_IDENTITY=PASS' "$WORK/identity.out"
KEY="/opt/chacha-dev/runtime/secrets/project-assurance/$PROJECT.pem"
[ -s "$KEY" ] || { echo "CHACHA_DEV_V632_INSTALL=BLOCKED reason=project_identity_key_missing"; exit 2; }
python3 - "$WORK/bundle/embedded-assurance.json" "$WORK/project-identity-receipt.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]));r=json.load(open(sys.argv[2]))
assert m["relay"]["identity_status"]=="ACTIVE",m
assert m["production_readiness"]["relay_identity_active"] is True,m
assert m["production_readiness"]["functional_contract_bound"] is True,m
assert m["production_readiness"]["ready"] is True,m
assert r["project_identity_active"] is True,r
assert r["private_key_exported"] is False,r
assert r["client_secret_allowed"] is False,r
print("CHACHA_DEV_V632_REAL_PROJECT_SCOPED_IDENTITY=PASS")
print("CHACHA_DEV_V632_REAL_PRODUCTION_READINESS=PASS")
PY

stage local-probes
python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --bundle "$WORK/bundle" --role guardian --event-type user-visible-failure --severity BLOCK \
  --fields-json '{"component_id":"pilot-ui","component_version":"v1","status_code":500}' \
  >"$WORK/guardian-local.out"
python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --bundle "$WORK/bundle" --role sentinel --event-type exception --severity BLOCK \
  --fields-json '{"component_id":"pilot-api","component_version":"v1","status_code":500}' \
  >"$WORK/sentinel-local.out"
grep -Fq 'CHACHA_DEV_PROJECT_ASSURANCE_EVENT=QUEUED' "$WORK/guardian-local.out"
grep -Fq 'CHACHA_DEV_PROJECT_ASSURANCE_EVENT=QUEUED' "$WORK/sentinel-local.out"
echo "CHACHA_DEV_V632_REAL_GUARDIAN_LOCAL_EVENT=PASS"
echo "CHACHA_DEV_V632_REAL_SENTINEL_LOCAL_EVENT=PASS"

stage privacy-negative-proof
set +e
python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --bundle "$WORK/bundle" --role guardian --event-type user-visible-failure --severity BLOCK \
  --fields-json '{"message":"raw user content must never leave the application"}' \
  >"$WORK/privacy-negative.out" 2>"$WORK/privacy-negative.stderr"
privacy_rc=$?
set -e
test "$privacy_rc" -ne 0
grep -Fq 'RAW_OR_SENSITIVE_FIELD_DENIED:message' "$WORK/privacy-negative.stderr"
echo "CHACHA_DEV_V632_REAL_RAW_USER_CONTENT_BLOCKED=PASS"

stage incremental-relay
python3 "$CURRENT/dev-hub/bin/project-assurance-relay.py"   --bundle "$WORK/bundle"   --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"   --private-key "$KEY" --role both >"$WORK/relay.out"
grep -Fq 'CHACHA_DEV_PROJECT_ASSURANCE_RELAY=PASS' "$WORK/relay.out"
python3 - "$WORK/relay.out" <<'PY'
import json,sys
first=open(sys.argv[1],encoding="utf-8").readline()
x=json.loads(first)
rows={r["role"]:r for r in x["results"]}
for role in ("guardian","sentinel"):
    r=rows[role]
    assert r["status"]=="DELIVERED",r
    assert int((r.get("ack") or {}).get("accepted") or 0)==1,r
    assert (r.get("ack") or {}).get("raw_user_content") is False,r
    assert (r.get("ack") or {}).get("direct_mutation") is False,r
assert x.get("client_secret_embedded") is False,x
assert x.get("direct_mutation") is False,x
print("CHACHA_DEV_V632_REAL_INCREMENTAL_RELAY=PASS")
print("CHACHA_DEV_V632_REAL_CENTRAL_GUARDIAN_INGEST=PASS")
print("CHACHA_DEV_V632_REAL_CENTRAL_SENTINEL_INGEST=PASS")
PY

stage cross-project-impersonation-block
PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$CURRENT" "$WORK" "$KEY" "$PROJECT" "$GUARDIAN_URL" <<'PY'
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);work=Path(sys.argv[2]);key=Path(sys.argv[3]);project=sys.argv[4];url=sys.argv[5].rstrip("/")
spec=importlib.util.spec_from_file_location("relay",root/"dev-hub/bin/project-assurance-relay.py")
relay=importlib.util.module_from_spec(spec);spec.loader.exec_module(relay)
event_files=list((work/"bundle"/"delivered"/"guardian").glob("*.json"))
assert event_files,event_files
event=json.load(open(event_files[0],encoding="utf-8"))
status,x=relay.post(url+"/v1/project-events",key,{
  "schema":"chacha.dev/project-assurance-event-batch/v1",
  "project_id":"other-"+project,
  "events":[event]
})
assert status==403,(status,x)
assert x.get("error")=="project_assurance_identity_project_mismatch",x
print("CHACHA_DEV_V632_REAL_CROSS_PROJECT_IMPERSONATION_BLOCKED=PASS")
PY

stage five-agent-network-contract
python3 - "$CURRENT/dev-hub/config/peripheral-assurance-network.v1.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
p=x["participants"];c=x["communication"]
assert set(p)=={"guardian","sentinel","curator","bastion","intendant"},p
assert p["guardian"]["status"]=="ACTIVE" and p["sentinel"]["status"]=="ACTIVE",p
assert p["curator"]["status"]=="PLANNED" and p["bastion"]["status"]=="PLANNED" and p["intendant"]["status"]=="PLANNED",p
assert c["common_exchange"]=="assurance-exchange",c
assert c["peer_to_peer_decision_making"] is False,c
assert c["direct_mutation"] is False,c
assert c["central_orchestrator_owns_remediation"] is True,c
assert c["architecture_change_requires_technology_watch"] is True,c
assert c["architecture_council_final_authority"] is True,c
print("CHACHA_DEV_V632_REAL_FIVE_AGENT_NETWORK_CONTRACT=PASS")
PY

cat >"/opt/chacha-dev/evidence/v632-project-embedded-assurance-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v632-project-embedded-assurance-evidence/v1",
  "revision":"$REV","observed_at":"$STAMP","project_id":"$PROJECT",
  "embedded_bundle":"PASS","project_scoped_identity":"PASS",
  "guardian_local_event":"PASS","sentinel_local_event":"PASS",
  "incremental_relay":"PASS","central_guardian_ingest":"PASS","central_sentinel_ingest":"PASS",
  "raw_user_content_blocked":"PASS","cross_project_impersonation_blocked":"PASS",
  "five_agent_network_contract":"PASS","direct_mutation":false,
  "remediation_owner":"central-orchestrator","automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V632_EVERY_PROJECT_EMBEDDED_ASSURANCE=YES"
echo "CHACHA_DEV_V632_GUARDIAN_LOCAL=YES"
echo "CHACHA_DEV_V632_SENTINEL_LOCAL=YES"
echo "CHACHA_DEV_V632_PROJECT_SCOPED_IDENTITY=YES"
echo "CHACHA_DEV_V632_INCREMENTAL_FEEDBACK=YES"
echo "CHACHA_DEV_V632_RAW_USER_CONTENT=NO"
echo "CHACHA_DEV_V632_CLIENT_SECRET=NO"
echo "CHACHA_DEV_V632_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V632_FIVE_AGENT_NETWORK_RESERVED=YES"
echo "CHACHA_DEV_V632_COMMON_ASSURANCE_EXCHANGE=YES"
echo "CHACHA_DEV_V632_REMEDIATION_OWNER=central-orchestrator"
echo "CHACHA_DEV_V632_TECHNOLOGY_WATCH_REQUIRED_FOR_ARCHITECTURE_CHANGE=YES"
echo "CHACHA_DEV_V632_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V632_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V632_INSTALL=PASS"

trap - EXIT
cleanup
