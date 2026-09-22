#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_COLLECTOR_KNOWLEDGE_ADAPTER_REV:-}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d /tmp/chacha-collector-knowledge-adapter.XXXXXX)"
REPO="$WORK/repo"
RECEIPT_ROOT="/opt/chacha-dev/runtime/adapter-provisioning"
RECEIPT="$RECEIPT_ROOT/collector-knowledge-adapter-$STAMP.json"
HEALTH_DIR="/opt/chacha-dev/runtime/health/wfgg-radar"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

die(){ echo "COLLECTOR_KNOWLEDGE_ADAPTER_BOOTSTRAP=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required

for cmd in curl python3 sha256sum systemctl grep mkdir; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

RADAR_STATE="$(systemctl is-active wfgg-radar-connector 2>/dev/null || true)"
RADAR_SENTINEL="$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
COLLECTOR_SENTINEL="$(systemctl is-active wfgg-collector-sentinel.timer 2>/dev/null || true)"

echo "RADAR_CONNECTOR_STATE=$RADAR_STATE"
echo "RADAR_SENTINEL_STATE=$RADAR_SENTINEL"
echo "COLLECTOR_SENTINEL_STATE=$COLLECTOR_SENTINEL"
[ "$RADAR_STATE" = "active" ] || die radar_connector_not_active
[ "$RADAR_SENTINEL" = "active" ] || die radar_sentinel_not_active
[ "$COLLECTOR_SENTINEL" = "active" ] || die collector_sentinel_not_active

mkdir -p "$REPO/dev-hub/bin" "$REPO/dev-hub/config" "$REPO/dev-hub/adapters" "$RECEIPT_ROOT" "$HEALTH_DIR"

curl -fsSL "$RAW/dev-hub/bin/adapter-provision.py" -o "$REPO/dev-hub/bin/adapter-provision.py"
curl -fsSL "$RAW/dev-hub/config/adapter-provisioning.v1.json" -o "$REPO/dev-hub/config/adapter-provisioning.v1.json"
curl -fsSL "$RAW/dev-hub/adapters/collector-knowledge-adapter.py" -o "$REPO/dev-hub/adapters/collector-knowledge-adapter.py"

python3 -m py_compile   "$REPO/dev-hub/bin/adapter-provision.py"   "$REPO/dev-hub/adapters/collector-knowledge-adapter.py"

cd "$REPO"
python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   plan --adapter collector-knowledge-adapter > "$WORK/provision-plan.json"

python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   apply --adapter collector-knowledge-adapter   --actor chacha-dev-bootstrap   --receipt "$RECEIPT"   --apply

python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   verify --adapter collector-knowledge-adapter   --receipt "$RECEIPT"

python3 - "$RECEIPT" "$HEALTH_DIR/providers.json" "$STAMP" "$REV" <<'PY'
import json,sys
from pathlib import Path
receipt_path,health_path,observed,revision=sys.argv[1:5]
r=json.load(open(receipt_path,encoding='utf-8'))
assert r['schema']=='chacha.dev/adapter-provisioning-receipt/v1',r
assert r['adapter']=='collector-knowledge-adapter',r
assert r['applied'] is True,r
assert r['probe']['status']=='PASS',r
assert r['executable_path']=='/opt/chacha-dev/adapters/collector-knowledge/current/collector-knowledge-adapter',r
assert r['source_digest']==r['installed_digest']==r['executable_digest'],r
print('COLLECTOR_KNOWLEDGE_ADAPTER_PROVISIONING=PASS')
print('COLLECTOR_KNOWLEDGE_ADAPTER_EXECUTABLE='+r['executable_path'])
print('COLLECTOR_KNOWLEDGE_ADAPTER_DIGEST='+r['executable_digest'])
print('COLLECTOR_KNOWLEDGE_ADAPTER_RECEIPT='+receipt_path)

p=Path(health_path)
if p.exists():
    try:x=json.loads(p.read_text(encoding='utf-8'))
    except Exception:x={}
else:x={}
if x.get('schema')!='chacha.dev/provider-health-snapshot/v1':
    x={'schema':'chacha.dev/provider-health-snapshot/v1','observed_at':observed,'providers':{}}
x['observed_at']=observed
x.setdefault('providers',{})['collector-knowledge-runtime']={
    'state':'HEALTHY',
    'source':'collector-knowledge-adapter-standard-provisioning',
    'checked_at':observed,
    'revision':revision,
    'executable_digest':r['executable_digest']
}
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
PY

echo "COLLECTOR_KNOWLEDGE_PROVIDER_HEALTH=HEALTHY"
echo "COLLECTOR_KNOWLEDGE_RADAR_PRODUCTION_MUTATION=NO"
echo "COLLECTOR_KNOWLEDGE_LASTWAR_MUTATION=NO"
echo "COLLECTOR_KNOWLEDGE_ADAPTER_BOOTSTRAP=PASS"
