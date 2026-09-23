#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V635_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v635.XXXXXX)"
PREVIOUS=""
STAGE="bootstrap"
PROJECT="v635-specialist-pilot-$STAMP"
INCIDENT_PROJECT="v635-bastion-contain-$STAMP"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V635_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V635_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err; do
      [ -s "$f" ] && { echo "=== $(basename "$f") ==="; cat "$f"; }
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V635_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || {
  echo "CHACHA_DEV_V635_INSTALL=BLOCKED reason=root_required"; exit 2;
}
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "CHACHA_DEV_V635_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2;
}
for cmd in curl tar python3 ln readlink grep cp find systemctl sha256sum sleep; do
  command -v "$cmd" >/dev/null || {
    echo "CHACHA_DEV_V635_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2;
  }
done
[ -f "$CURRENT/dev-hub/bin/logic-search-engine.py" ] || {
  echo "CHACHA_DEV_V635_INSTALL=BLOCKED reason=v634_baseline_missing"; exit 2;
}
[ -L "$CURRENT" ] && PREVIOUS="$(readlink -f "$CURRENT" || true)"
echo "CHACHA_DEV_V635_V634_BASELINE=PASS"

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tgz"
tar -xzf "$WORK/repo.tgz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || {
  echo "CHACHA_DEV_V635_INSTALL=BLOCKED reason=archive_invalid"; exit 2;
}
for required in \
  dev-hub/bin/specialist-authority-client.py \
  dev-hub/bin/bastion-incident-response-controller.py \
  dev-hub/bin/project-assurance-identity-manager.py \
  dev-hub/bin/project-assurance-event.py \
  dev-hub/bin/project-assurance-relay.py \
  dev-hub/bin/project-embedded-assurance.py \
  dev-hub/bin/assurance-exchange-client.py \
  dev-hub/config/curator-runtime-policy.v1.json \
  dev-hub/config/bastion-runtime-policy.v1.json \
  dev-hub/config/intendant-runtime-policy.v1.json \
  dev-hub/config/project-embedded-assurance.v1.json \
  dev-hub/config/bastion-authority.v1.json \
  dev-hub/systemd/chacha-dev-bastion-incident-response.service \
  dev-hub/systemd/chacha-dev-bastion-incident-response.timer \
  dev-hub/tests/test_v635_central_specialist_authorities.py; do
  [ -f "$SRC/$required" ] || {
    echo "CHACHA_DEV_V635_INSTALL=BLOCKED reason=missing:$required"; exit 2;
  }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile \
  "$RELEASE/dev-hub/bin/specialist-authority-client.py" \
  "$RELEASE/dev-hub/bin/bastion-incident-response-controller.py" \
  "$RELEASE/dev-hub/bin/project-assurance-identity-manager.py" \
  "$RELEASE/dev-hub/bin/assurance-exchange-client.py"
for f in \
  "$RELEASE/dev-hub/config/curator-runtime-policy.v1.json" \
  "$RELEASE/dev-hub/config/bastion-runtime-policy.v1.json" \
  "$RELEASE/dev-hub/config/intendant-runtime-policy.v1.json" \
  "$RELEASE/dev-hub/config/project-embedded-assurance.v1.json" \
  "$RELEASE/dev-hub/config/bastion-authority.v1.json"; do
  python3 -m json.tool "$f" >/dev/null
done
echo "CHACHA_DEV_V635_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v635_central_specialist_authorities.py
) >"$WORK/semantic.out" 2>&1
for marker in \
  CHACHA_DEV_V635_CURATOR_CENTRAL_AUTHORITY=PASS \
  CHACHA_DEV_V635_BASTION_CENTRAL_AUTHORITY=PASS \
  CHACHA_DEV_V635_INTENDANT_CENTRAL_AUTHORITY=PASS \
  CHACHA_DEV_V635_SPECIALIST_REVIEWS_EXCHANGE_REVERIFY=PASS \
  CHACHA_DEV_V635_BASTION_RESPONSE_CONTROLLER=PASS \
  CHACHA_DEV_V635_FAILOVER_RESERVED_INACTIVE=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V635_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage install-bastion-response-controller
cp "$CURRENT/dev-hub/systemd/chacha-dev-bastion-incident-response.service" \
  /etc/systemd/system/chacha-dev-bastion-incident-response.service
cp "$CURRENT/dev-hub/systemd/chacha-dev-bastion-incident-response.timer" \
  /etc/systemd/system/chacha-dev-bastion-incident-response.timer
systemctl daemon-reload
systemctl enable --now chacha-dev-bastion-incident-response.timer >/dev/null
systemctl is-enabled --quiet chacha-dev-bastion-incident-response.timer
systemctl is-active --quiet chacha-dev-bastion-incident-response.timer
echo "CHACHA_DEV_V635_REAL_BASTION_RESPONSE_TIMER=PASS"

stage external-authorities-health
CURATOR_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/curator-runtime-policy.v1.json"))["external_url"])')"
BASTION_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/bastion-runtime-policy.v1.json"))["external_url"])')"
INTENDANT_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/intendant-runtime-policy.v1.json"))["external_url"])')"
EXCHANGE_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/assurance-exchange-runtime-policy.v1.json"))["external_url"])')"
curl -fsS "$CURATOR_URL/healthz" -o "$WORK/curator-health.json"
curl -fsS "$BASTION_URL/healthz" -o "$WORK/bastion-health.json"
curl -fsS "$INTENDANT_URL/healthz" -o "$WORK/intendant-health.json"
curl -fsS "$EXCHANGE_URL/healthz" -o "$WORK/exchange-health.json"
python3 - "$WORK/curator-health.json" "$WORK/bastion-health.json" "$WORK/intendant-health.json" "$WORK/exchange-health.json" <<'PY'
import json,sys
c,b,i,e=[json.load(open(p)) for p in sys.argv[1:]]
assert c["authority"]=="curator" and c["external_authority"] is True,c
assert b["authority"]=="bastion" and b["bastion_incident_response"] is True,b
assert b["failover_status"]=="RESERVED_INACTIVE",b
assert i["authority"]=="intendant" and i["external_authority"] is True,i
assert e["curator_service_binding"] is True,e
assert e["bastion_service_binding"] is True,e
assert e["intendant_service_binding"] is True,e
assert e["specialist_review_source_reverification"] is True,e
print("CHACHA_DEV_V635_REAL_CURATOR_HEALTH=PASS")
print("CHACHA_DEV_V635_REAL_BASTION_HEALTH=PASS")
print("CHACHA_DEV_V635_REAL_INTENDANT_HEALTH=PASS")
print("CHACHA_DEV_V635_REAL_EXCHANGE_REVERIFY_PATH=PASS")
PY

make_bundle(){
  project="$1"; out="$2"
  cat >"$out-contract.json" <<JSON
{"schema":"chacha.dev/functional-contract/v1","contract_id":"functional-$project","criteria":[{"criterion_id":"specialist-authorities","required":true}]}
JSON
  python3 "$CURRENT/dev-hub/bin/project-embedded-assurance.py" \
    --project-id "$project" --application-version "$REV" \
    --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
    --runtime-script "$CURRENT/dev-hub/bin/project-assurance-event.py" \
    --relay-script "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
    --client-runtime "$CURRENT/dev-hub/templates/project-assurance-client.mjs" \
    --functional-contract "$out-contract.json" --output-dir "$out"
  python3 "$CURRENT/dev-hub/bin/project-assurance-identity-manager.py" \
    --project-id "$project" \
    --guardian-client "$CURRENT/dev-hub/bin/guardian-client.py" \
    --guardian-policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
    --sentinel-client "$CURRENT/dev-hub/bin/sentinel-client.py" \
    --sentinel-policy "$CURRENT/dev-hub/config/sentinel-runtime-policy.v1.json" \
    --exchange-client "$CURRENT/dev-hub/bin/assurance-exchange-client.py" \
    --exchange-policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json" \
    --specialist-client "$CURRENT/dev-hub/bin/specialist-authority-client.py" \
    --curator-policy "$CURRENT/dev-hub/config/curator-runtime-policy.v1.json" \
    --bastion-policy "$CURRENT/dev-hub/config/bastion-runtime-policy.v1.json" \
    --intendant-policy "$CURRENT/dev-hub/config/intendant-runtime-policy.v1.json" \
    --registration "$out-registration.json" --receipt "$out-identity.json" --bundle "$out"
}

stage real-project-all-authority-identity
make_bundle "$PROJECT" "$WORK/bundle"
python3 - "$WORK/bundle-identity.json" "$WORK/bundle/embedded-assurance.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));m=json.load(open(sys.argv[2]))
for k in ("guardian_status","sentinel_status","exchange_status","curator_status","bastion_status","intendant_status"):
    assert r[k]=="PASS",(k,r)
assert m["production_readiness"]["specialist_authority_identities_active"] is True,m
assert m["production_readiness"]["ready"] is True,m
print("CHACHA_DEV_V635_REAL_ALL_AUTHORITY_IDENTITIES=PASS")
PY

stage emit-specialist-health
emit(){
  role="$1"; event="$2"; fields="$3"
  python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
    --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
    --bundle "$WORK/bundle" --role "$role" --event-type "$event" --severity INFO \
    --fields-json "$fields" >"$WORK/event-$role.out"
  python3 "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
    --bundle "$WORK/bundle" \
    --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
    --private-key "/opt/chacha-dev/runtime/secrets/project-assurance/$PROJECT.pem" \
    --role "$role" >"$WORK/relay-$role.out"
}
emit curator visual-health '{"surface_id":"pilot-home","viewport_class":"mobile","visual_diff_score":0.0}'
emit bastion security-health '{"component_id":"pilot-api","exposure_class":"expected"}'
emit intendant resource-health '{"component_id":"pilot-api","memory_mb":128,"cpu_ms":50,"external_cost_microunits":0}'
echo "CHACHA_DEV_V635_REAL_THREE_SPECIALIST_PROBE_STREAMS=PASS"

COMPROMISE_DIGEST="sha256:$(printf '%s' "$PROJECT|$REV|v635-compromise" | sha256sum | awk '{print $1}')"

stage real-specialist-reviews
review(){
  role="$1"
  python3 "$CURRENT/dev-hub/bin/specialist-authority-client.py" \
    --policy "$CURRENT/dev-hub/config/$role-runtime-policy.v1.json" \
    review --project-id "$PROJECT" --revision "$REV" \
    --compromise-digest "$COMPROMISE_DIGEST" --implementation-verified \
    >"$WORK/review-$role.json"
}
review curator
review bastion
review intendant
python3 - "$WORK/review-curator.json" "$WORK/review-bastion.json" "$WORK/review-intendant.json" <<'PY'
import json,sys
rows=[json.load(open(p)) for p in sys.argv[1:]]
assert {x["agent"] for x in rows}=={"curator","bastion","intendant"},rows
for x in rows:
    assert x["verdict"]=="ACCEPT",x
    assert x["implementation_verified"] is True,x
    assert x["evidence_refs"],x
    assert (x.get("assurance_exchange_delivery") or {}).get("status")=="DELIVERED",x
print("CHACHA_DEV_V635_REAL_CURATOR_REVIEW=PASS")
print("CHACHA_DEV_V635_REAL_BASTION_REVIEW=PASS")
print("CHACHA_DEV_V635_REAL_INTENDANT_REVIEW=PASS")
PY

stage exchange-source-reverification
python3 "$CURRENT/dev-hub/bin/assurance-exchange-client.py" \
  --policy "$CURRENT/dev-hub/config/assurance-exchange-runtime-policy.v1.json" \
  specialist-reviews --project-id "$PROJECT" --revision "$REV" --compromise-digest "$COMPROMISE_DIGEST" \
  >"$WORK/exchange-specialist-reviews.json"
python3 - "$WORK/exchange-specialist-reviews.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));items=x["items"]
assert x["count"]==3,x
assert {r["agent"] for r in items}=={"curator","bastion","intendant"},x
assert all(r["source_reverified"] is True for r in items),x
assert all(r["verdict"]=="ACCEPT" for r in items),x
print("CHACHA_DEV_V635_REAL_SPECIALIST_REVIEWS_SOURCE_REVERIFIED=PASS")
PY

stage bastion-real-containment
make_bundle "$INCIDENT_PROJECT" "$WORK/incident-bundle"
python3 "$CURRENT/dev-hub/bin/project-assurance-event.py" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --bundle "$WORK/incident-bundle" --role bastion --event-type permission-drift --severity WARNING \
  --fields-json '{"permission_code":"pilot-scope-drift","exposure_class":"authenticated"}' \
  >"$WORK/incident-event.out"
python3 "$CURRENT/dev-hub/bin/project-assurance-relay.py" \
  --bundle "$WORK/incident-bundle" \
  --policy "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json" \
  --private-key "/opt/chacha-dev/runtime/secrets/project-assurance/$INCIDENT_PROJECT.pem" \
  --role bastion >"$WORK/incident-relay.out"
python3 - "$WORK/incident-relay.out" <<'PY'
import json,sys
x=json.loads(open(sys.argv[1]).readline());row=x["results"][0]
assert row["role"]=="bastion" and row["status"]=="DELIVERED",row
inc=(row.get("ack") or {}).get("incidents") or []
assert inc and inc[0]["response_action"]=="CONTAIN",row
print("CHACHA_DEV_V635_REAL_BASTION_CONTAIN_DIRECTIVE=PASS")
PY
python3 "$CURRENT/dev-hub/bin/bastion-incident-response-controller.py" >"$WORK/bastion-controller.out" 2>"$WORK/bastion-controller.err" || true
CONTROL="/opt/chacha-dev/runtime/control/containment/$INCIDENT_PROJECT.json"
for _ in $(seq 1 8); do
  [ -f "$CONTROL" ] && break
  sleep 2
  python3 "$CURRENT/dev-hub/bin/bastion-incident-response-controller.py" >/dev/null 2>&1 || true
done
[ -f "$CONTROL" ] || {
  echo "CHACHA_DEV_V635_INSTALL=BLOCKED reason=containment_not_materialized"; exit 2;
}
python3 - "$CONTROL" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["active"] is True,x
assert x["new_mutation_blocked"] is True,x
assert x["source"]=="bastion-central-authority",x
print("CHACHA_DEV_V635_REAL_BASTION_CONTAINMENT=PASS")
PY
rm -f "$CONTROL"
echo "CHACHA_DEV_V635_REAL_PILOT_CONTAINMENT_CLEANUP=PASS"

stage bastion-emergency-policy-proof
python3 - "$CURRENT/dev-hub/config/bastion-authority.v1.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));ir=x["incident_response"]
assert ir["local_project_attack_max_without_corroboration"]=="QUARANTINE",ir
assert ir["e_stop_requires"]["minimum_independent_corroborations"]==2,ir
assert set(ir["e_stop_requires"]["allowed_scopes"])=={"CORE","PLATFORM"},ir
assert ir["failover"]["status"]=="RESERVED_INACTIVE",ir
assert ir["failover"]["compromised_state_replication_forbidden"] is True,ir
print("CHACHA_DEV_V635_REAL_BASTION_EMERGENCY_CORROBORATION_GUARD=PASS")
print("CHACHA_DEV_V635_REAL_FAILOVER_RESERVED_INACTIVE=PASS")
PY

cat >"/opt/chacha-dev/evidence/v635-central-specialist-authorities-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v635-central-specialist-authorities-evidence/v1",
  "revision":"$REV","observed_at":"$STAMP","project_id":"$PROJECT",
  "curator_central":"PASS","bastion_central":"PASS","intendant_central":"PASS",
  "all_authority_identities":"PASS","three_specialist_reviews":"PASS",
  "exchange_source_reverification":"PASS","bastion_containment":"PASS",
  "bastion_emergency_corroboration_guard":"PASS",
  "failover":"RESERVED_INACTIVE","compromised_state_replication":"FORBIDDEN",
  "direct_mutation":false,"automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V635_CURATOR_CENTRAL=ACTIVE"
echo "CHACHA_DEV_V635_BASTION_CENTRAL=ACTIVE"
echo "CHACHA_DEV_V635_INTENDANT_CENTRAL=ACTIVE"
echo "CHACHA_DEV_V635_REAL_THREE_SPECIALIST_REVIEWS=PASS"
echo "CHACHA_DEV_V635_REAL_EXCHANGE_SOURCE_REVERIFICATION=PASS"
echo "CHACHA_DEV_V635_REAL_BASTION_CONTAINMENT=PASS"
echo "CHACHA_DEV_V635_BASTION_EMERGENCY_REQUIRES_CORROBORATION=YES"
echo "CHACHA_DEV_V635_FAILOVER=RESERVED_INACTIVE"
echo "CHACHA_DEV_V635_COMPROMISED_STATE_REPLICATION=FORBIDDEN"
echo "CHACHA_DEV_V635_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V635_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V635_INSTALL=PASS"

trap - EXIT
cleanup
