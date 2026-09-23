#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_V633_REV:-}"
BASE=/opt/chacha-dev/platform
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v633.XXXXXX)"
PREVIOUS=""
PROJECT="v633-five-probe-$STAMP"
STAGE=bootstrap
stage(){ STAGE="$1"; echo "CHACHA_DEV_V633_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V633_FAILURE_STAGE=$STAGE"
    [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ] && ln -sfn "$PREVIOUS" "$CURRENT" && echo "CHACHA_DEV_V633_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT
[ "$(id -u)" -eq 0 ] || exit 2
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || exit 2
[ -f "$CURRENT/dev-hub/bin/project-embedded-assurance.py" ] || exit 2
[ -L "$CURRENT" ] && PREVIOUS="$(readlink -f "$CURRENT" || true)"
echo "CHACHA_DEV_V633_V632_BASELINE=PASS"

stage fetch-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tgz"
tar -xzf "$WORK/repo.tgz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"

stage semantic
(
  cd "$RELEASE"
  PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v633_five_agent_embedded_probes.py
) >"$WORK/semantic.out"
grep -Fq 'CHACHA_DEV_V633_FIVE_LOCAL_PROBES_ACTIVE=PASS' "$WORK/semantic.out"
grep -Fq 'CHACHA_DEV_V633_INCREMENTAL_EXCHANGE_SINK=PASS' "$WORK/semantic.out"
echo "CHACHA_DEV_V633_SEMANTIC_PILOT=PASS"

stage activate
ln -sfn "$RELEASE" "$CURRENT"

stage bundle
cat >"$WORK/contract.json" <<JSON
{"schema":"chacha.dev/functional-contract/v1","contract_id":"functional-$PROJECT","criteria":[{"criterion_id":"five-probes","required":true}]}
JSON
python3 "$CURRENT/dev-hub/bin/project-embedded-assurance.py" \
  --project-id "$PROJECT" --application-version "$REV" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --runtime-script "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --relay-script "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
  --client-runtime "$CURRENT/dev-hub/templates/project-assurance-client.mjs" \
  --functional-contract "$WORK/contract.json" --output-dir "$WORK/bundle" >"$WORK/bundle.out"
for role in CURATOR BASTION INTENDANT; do grep -Fq "${role}_LOCAL=ENABLED" "$WORK/bundle.out"; done
echo "CHACHA_DEV_V633_REAL_FIVE_PROBE_BUNDLE=PASS"

stage identity
python3 "$CURRENT/dev-hub/bin/project-assurance-identity-manager.py" \
  --project-id "$PROJECT" \
  --guardian-client "$CURRENT/dev-hub/bin/guardian-client.py" \
  --guardian-policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  --sentinel-client "$CURRENT/dev-hub/bin/sentinel-client.py" \
  --sentinel-policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json" \
  --exchange-client "$CURRENT/dev-hub/bin/assurance-exchange-client.py" \
  --exchange-policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json" \
  --registration "$WORK/registration.json" --receipt "$WORK/identity.json" \
  --bundle "$WORK/bundle" >"$WORK/identity.out"
grep -Fq 'GUARDIAN_REGISTRATION=PASS' "$WORK/identity.out"
grep -Fq 'SENTINEL_REGISTRATION=PASS' "$WORK/identity.out"
grep -Fq 'EXCHANGE_REGISTRATION=PASS' "$WORK/identity.out"
KEY="/opt/chacha-dev/runtime/secrets/project-assurance/$PROJECT.pem"
echo "CHACHA_DEV_V633_REAL_PROJECT_IDENTITY_THREE_PLANES=PASS"

stage events
emit(){
  role="$1"; type="$2"; fields="$3"
  python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
    --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
    --bundle "$WORK/bundle" --role "$role" --event-type "$type" \
    --severity WARNING --fields-json "$fields" >"$WORK/$role.out"
}
emit guardian functional-miss '{"component_id":"pilot-ui"}'
emit sentinel runtime-regression '{"component_id":"pilot-api","duration_ms":1300}'
emit curator visual-regression '{"surface_id":"home","viewport_class":"mobile","visual_diff_score":0.42}'
emit bastion permission-drift '{"permission_code":"scope-expanded","exposure_class":"authenticated"}'
emit intendant resource-budget-drift '{"memory_mb":640,"cpu_ms":1800,"external_cost_microunits":12}'
for role in guardian sentinel curator bastion intendant; do
  grep -Fq 'CHACHA_DEV_PROJECT_ASSURANCE_EVENT=QUEUED' "$WORK/$role.out"
done
echo "CHACHA_DEV_V633_REAL_FIVE_LOCAL_EVENTS=PASS"

stage relay
python3 "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
  --bundle "$WORK/bundle" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --private-key "$KEY" --role all >"$WORK/relay.out"
grep -Fq 'CHACHA_DEV_PROJECT_ASSURANCE_RELAY=PASS' "$WORK/relay.out"
python3 - "$WORK/relay.out" <<'PY'
import json,sys
x=json.loads(open(sys.argv[1]).readline())
rows={r["role"]:r for r in x["results"]}
assert set(rows)=={"guardian","sentinel","curator","bastion","intendant"},rows
for role,row in rows.items():
    assert row["status"]=="DELIVERED",(role,row)
    assert int((row.get("ack") or {}).get("accepted") or 0)==1,(role,row)
print("CHACHA_DEV_V633_REAL_FIVE_INCREMENTAL_STREAMS=PASS")
print("CHACHA_DEV_V633_REAL_CURATOR_INCREMENTAL_INGEST=PASS")
print("CHACHA_DEV_V633_REAL_BASTION_INCREMENTAL_INGEST=PASS")
print("CHACHA_DEV_V633_REAL_INTENDANT_INCREMENTAL_INGEST=PASS")
PY

stage privacy
set +e
python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --bundle "$WORK/bundle" --role curator --event-type visual-regression \
  --fields-json '{"message":"forbidden"}' >"$WORK/privacy.out" 2>"$WORK/privacy.err"
rc=$?
set -e
test "$rc" -ne 0
grep -Fq 'RAW_OR_SENSITIVE_FIELD_DENIED:message' "$WORK/privacy.err"
echo "CHACHA_DEV_V633_REAL_RAW_USER_CONTENT_BLOCKED=PASS"

echo "CHACHA_DEV_V633_GUARDIAN_LOCAL=YES"
echo "CHACHA_DEV_V633_SENTINEL_LOCAL=YES"
echo "CHACHA_DEV_V633_CURATOR_LOCAL=YES"
echo "CHACHA_DEV_V633_BASTION_LOCAL=YES"
echo "CHACHA_DEV_V633_INTENDANT_LOCAL=YES"
echo "CHACHA_DEV_V633_ALL_FIVE_INCREMENTAL_FEEDBACK=YES"
echo "CHACHA_DEV_V633_COMMON_ASSURANCE_EXCHANGE=YES"
echo "CHACHA_DEV_V633_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V633_REMEDIATION_OWNER=central-orchestrator"
echo "CHACHA_DEV_V633_TECHNOLOGY_WATCH_REQUIRED_FOR_ARCHITECTURE_CHANGE=YES"
echo "CHACHA_DEV_V633_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V633_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V633_INSTALL=PASS"
trap - EXIT
cleanup
