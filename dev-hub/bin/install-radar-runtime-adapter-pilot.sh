#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_ADAPTER_REV:-dev-hub-v5-radar-runtime-adapter-pilot-prep}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d /tmp/chacha-radar-adapter-bootstrap.XXXXXX)"
REPO="$WORK/repo"
RECEIPT_ROOT="/opt/chacha-dev/runtime/adapter-provisioning"
RECEIPT="$RECEIPT_ROOT/radar-runtime-adapter-$STAMP.json"
HEALTH_DIR="/opt/chacha-dev/runtime/health/wfgg-radar"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "RADAR_RUNTIME_ADAPTER_BOOTSTRAP=BLOCKED reason=root_required"
  exit 2
fi

if ! printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "RADAR_RUNTIME_ADAPTER_BOOTSTRAP=BLOCKED reason=pinned_revision_required"
  exit 2
fi

for cmd in curl python3 sha256sum systemctl grep mkdir; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "RADAR_RUNTIME_ADAPTER_BOOTSTRAP=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

echo "=== CHACHA DEV RADAR RUNTIME ADAPTER BOOTSTRAP ==="

RADAR_SENTINEL_STATE="$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
RADAR_SENTINEL_ENABLED="$(systemctl is-enabled wfgg-radar-sentinel.timer 2>/dev/null || true)"
COLLECTOR_SENTINEL_STATE="$(systemctl is-active wfgg-collector-sentinel.timer 2>/dev/null || true)"

echo "RADAR_SENTINEL_TIMER=$RADAR_SENTINEL_STATE"
echo "RADAR_SENTINEL_ENABLED=$RADAR_SENTINEL_ENABLED"
echo "COLLECTOR_SENTINEL_TIMER=$COLLECTOR_SENTINEL_STATE"

[ "$RADAR_SENTINEL_STATE" = "active" ] || {
  echo "RADAR_RUNTIME_ADAPTER_BOOTSTRAP=BLOCKED reason=radar_sentinel_not_active"
  exit 2
}
[ "$RADAR_SENTINEL_ENABLED" = "enabled" ] || {
  echo "RADAR_RUNTIME_ADAPTER_BOOTSTRAP=BLOCKED reason=radar_sentinel_not_enabled"
  exit 2
}
[ "$COLLECTOR_SENTINEL_STATE" = "active" ] || {
  echo "RADAR_RUNTIME_ADAPTER_BOOTSTRAP=BLOCKED reason=collector_sentinel_not_active"
  exit 2
}

mkdir -p "$REPO/dev-hub/bin" "$REPO/dev-hub/config" "$REPO/dev-hub/adapters" "$RECEIPT_ROOT" "$HEALTH_DIR"

curl -fsSL "$RAW/dev-hub/bin/adapter-provision.py" -o "$REPO/dev-hub/bin/adapter-provision.py"
curl -fsSL "$RAW/dev-hub/config/adapter-provisioning.v1.json" -o "$REPO/dev-hub/config/adapter-provisioning.v1.json"
curl -fsSL "$RAW/dev-hub/adapters/radar-runtime-adapter.py" -o "$REPO/dev-hub/adapters/radar-runtime-adapter.py"

python3 -m py_compile "$REPO/dev-hub/bin/adapter-provision.py" "$REPO/dev-hub/adapters/radar-runtime-adapter.py"

cd "$REPO"
python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   plan --adapter radar-runtime-adapter > "$WORK/provision-plan.json"

python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   apply   --adapter radar-runtime-adapter   --actor chacha-dev-bootstrap   --receipt "$RECEIPT"   --apply

python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   verify   --adapter radar-runtime-adapter   --receipt "$RECEIPT"

python3 - "$RECEIPT" "$HEALTH_DIR/providers.json" "$STAMP" "$REV" <<'PY'
import json,sys
from pathlib import Path
receipt_path,health_path,observed,revision=sys.argv[1:5]
r=json.load(open(receipt_path,encoding='utf-8'))
assert r['schema']=='chacha.dev/adapter-provisioning-receipt/v1',r
assert r['adapter']=='radar-runtime-adapter',r
assert r['applied'] is True,r
assert r['probe']['status']=='PASS',r
assert r['executable_path']=='/opt/chacha-dev/adapters/radar-runtime/current/radar-runtime-adapter',r
assert r['source_digest']==r['installed_digest']==r['executable_digest'],r
print('RADAR_RUNTIME_ADAPTER_STANDARD_PROVISIONING=PASS')
print('RADAR_RUNTIME_ADAPTER_EXECUTABLE='+r['executable_path'])
print('RADAR_RUNTIME_ADAPTER_DIGEST='+r['executable_digest'])
print('RADAR_RUNTIME_ADAPTER_PROVISIONING_RECEIPT='+receipt_path)

p=Path(health_path)
if p.exists():
    try: x=json.loads(p.read_text(encoding='utf-8'))
    except Exception: x={}
else:
    x={}
if x.get('schema')!='chacha.dev/provider-health-snapshot/v1':
    x={'schema':'chacha.dev/provider-health-snapshot/v1','observed_at':observed,'providers':{}}
x['observed_at']=observed
x.setdefault('providers',{})['radar-vps-runtime']={
    'state':'HEALTHY',
    'source':'radar-runtime-adapter-standard-provisioning',
    'checked_at':observed,
    'revision':revision,
    'executable_digest':r['executable_digest']
}
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
PY

echo "RADAR_RUNTIME_ADAPTER_HEALTH=HEALTHY"
echo "RADAR_RUNTIME_ADAPTER_PRODUCTION_RADAR_MUTATION=NO"
echo "RADAR_RUNTIME_ADAPTER_REGISTRY_MUTATION=NO"
echo "RADAR_RUNTIME_ADAPTER_BOOTSTRAP=PASS"
