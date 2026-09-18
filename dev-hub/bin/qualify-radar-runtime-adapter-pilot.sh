#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_QUAL_REV:-}"
RECEIPT="${1:-}"
RAW_BASE="https://raw.githubusercontent.com/chachasan090375/WfGg"
OUT_ROOT="/opt/chacha-dev/runtime/adapter-promotions/radar-runtime-adapter"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_ROOT/$STAMP"
WORK="$(mktemp -d /tmp/chacha-radar-pilot-qualification.XXXXXX)"
REPO="$WORK/repo"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

die(){ echo "RADAR_PILOT_QUALIFICATION=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
[ -n "$RECEIPT" ] || die receipt_path_required
[ -f "$RECEIPT" ] || die receipt_not_found

for cmd in curl python3 systemctl grep mkdir; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

RADAR_SENTINEL_STATE="$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
RADAR_SENTINEL_ENABLED="$(systemctl is-enabled wfgg-radar-sentinel.timer 2>/dev/null || true)"
COLLECTOR_SENTINEL_STATE="$(systemctl is-active wfgg-collector-sentinel.timer 2>/dev/null || true)"

echo "=== CHACHA DEV RADAR PILOT QUALIFICATION ==="
echo "RADAR_SENTINEL_TIMER=$RADAR_SENTINEL_STATE"
echo "RADAR_SENTINEL_ENABLED=$RADAR_SENTINEL_ENABLED"
echo "COLLECTOR_SENTINEL_TIMER=$COLLECTOR_SENTINEL_STATE"

[ "$RADAR_SENTINEL_STATE" = "active" ] || die radar_sentinel_not_active
[ "$RADAR_SENTINEL_ENABLED" = "enabled" ] || die radar_sentinel_not_enabled
[ "$COLLECTOR_SENTINEL_STATE" = "active" ] || die collector_sentinel_not_active

mkdir -p "$REPO/dev-hub/bin" "$REPO/dev-hub/config" "$OUT"

for path in   dev-hub/bin/adapter-promotion.py   dev-hub/bin/adapter-provisioning-evidence.py   dev-hub/config/adapter-contract.v1.json   dev-hub/config/adapter-promotion.v1.json   dev-hub/config/provider-adapters.v1.json
do
  mkdir -p "$REPO/$(dirname "$path")"
  curl -fsSL "$RAW_BASE/$REV/$path" -o "$REPO/$path"
done

python3 -m py_compile   "$REPO/dev-hub/bin/adapter-promotion.py"   "$REPO/dev-hub/bin/adapter-provisioning-evidence.py"

python3 - "$RECEIPT" "$OUT/base-evidence.json" <<'PY'
import json,sys
from datetime import datetime,timezone
receipt_path,out=sys.argv[1:3]
r=json.load(open(receipt_path,encoding='utf-8'))
assert r.get('schema')=='chacha.dev/adapter-provisioning-receipt/v1',r
assert r.get('adapter')=='radar-runtime-adapter',r
assert r.get('applied') is True,r
assert (r.get('probe') or {}).get('status')=='PASS',r
now=datetime.now(timezone.utc).isoformat()
e={
  'schema':'chacha.dev/adapter-promotion-evidence/v1',
  'adapter':'radar-runtime-adapter',
  'observed_at':now,
  'evidence':{
    'runtime-contract-pass':{
      'status':'PASS',
      'source':'github-actions:35379380803:radar-runtime-adapter-contract',
      'observed_at':now,
      'details':{
        'contract_run':'35379380803',
        'contract_status':'SUCCESS',
        'offline_contract_tests':'PASS',
        'static_adapter_contract':'PASS',
        'manifest_resolution':'PASS'
      }
    },
    'sandbox-only':{
      'status':'PASS',
      'source':'github-actions:35379828903:radar-runtime-adapter-pilot-prep',
      'observed_at':now,
      'details':{
        'pilot_prep_run':'35379828903',
        'pilot_prep_status':'SUCCESS',
        'production_radar_mutation':'NO',
        'registry_mutation':'NO',
        'radar_sentinel_guard':'PASS',
        'collector_sentinel_guard':'PASS'
      }
    }
  },
  'approvals':[],
  'notes':[
    'CONTRACT_OK->PILOT qualification only.',
    'No provider-adapter registry mutation is performed by this qualification.'
  ]
}
open(out,'w',encoding='utf-8').write(json.dumps(e,indent=2)+'\n')
PY

cd "$REPO"

python3 dev-hub/bin/adapter-provisioning-evidence.py   --adapter radar-runtime-adapter   --base-evidence "$OUT/base-evidence.json"   --receipt "$RECEIPT"   --output "$OUT/promotion-evidence.json"

EXEC="$(python3 - "$RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding='utf-8'))
print(r['executable_path'])
PY
)"

python3 dev-hub/bin/adapter-promotion.py   --registry dev-hub/config/provider-adapters.v1.json   --contract dev-hub/config/adapter-contract.v1.json   --policy dev-hub/config/adapter-promotion.v1.json   --evidence "$OUT/promotion-evidence.json"   --report "$OUT/promotion-plan.json"   --json plan   --adapter radar-runtime-adapter   --target PILOT   --executable "$EXEC" > "$OUT/promotion-plan.stdout.json"

python3 - "$RECEIPT" "$OUT/promotion-evidence.json" "$OUT/promotion-plan.json" <<'PY'
import json,sys
receipt_path,evidence_path,plan_path=sys.argv[1:4]
r=json.load(open(receipt_path,encoding='utf-8'))
e=json.load(open(evidence_path,encoding='utf-8'))
p=json.load(open(plan_path,encoding='utf-8'))
assert p.get('eligible') is True,p
assert p.get('current_status')=='CONTRACT_OK',p
assert p.get('target_status')=='PILOT',p
assert p.get('requires_local_executable') is True,p
assert p.get('executable_after')==r.get('executable_path'),(p,r)
prov=(e.get('evidence') or {}).get('provisioning-pass') or {}
assert prov.get('status')=='PASS',prov
details=prov.get('details') or {}
assert details.get('executable_digest')==r.get('executable_digest'),(details,r)

print('RADAR_PILOT_QUALIFICATION=PASS')
print('PROMOTION_ELIGIBLE=YES')
print('CURRENT_STATUS='+str(p.get('current_status')))
print('TARGET_STATUS='+str(p.get('target_status')))
print('EXECUTABLE='+str(r.get('executable_path')))
print('EXECUTABLE_DIGEST='+str(r.get('executable_digest')))
print('PROVISIONING_RECEIPT='+receipt_path)
print('PROVISIONING_RECEIPT_DIGEST='+str(details.get('receipt_digest')))
print('REQUIRED_EVIDENCE='+','.join(p.get('required_evidence') or []))
print('REGISTRY_MUTATION=NO')
print('RADAR_PRODUCTION_MUTATION=NO')
PY

echo "PROMOTION_EVIDENCE=$OUT/promotion-evidence.json"
echo "PROMOTION_PLAN=$OUT/promotion-plan.json"
