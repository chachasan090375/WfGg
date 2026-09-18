#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_ADAPTER_REV:-dev-hub-v5-radar-runtime-adapter-pilot-prep}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}"
BASE="/opt/chacha-dev/adapters/radar-runtime"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
HEALTH_DIR="/opt/chacha-dev/runtime/health/wfgg-radar"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
WORK="$(mktemp -d /tmp/chacha-radar-adapter-pilot.XXXXXX)"
CURRENT="$BASE/current"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "RADAR_RUNTIME_ADAPTER_PILOT=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 sha256sum install ln systemctl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "RADAR_RUNTIME_ADAPTER_PILOT=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

echo "=== CHACHA DEV RADAR RUNTIME ADAPTER PILOT PREP ==="

RADAR_SENTINEL_STATE="$(systemctl is-active wfgg-radar-sentinel.timer 2>/dev/null || true)"
RADAR_SENTINEL_ENABLED="$(systemctl is-enabled wfgg-radar-sentinel.timer 2>/dev/null || true)"
COLLECTOR_SENTINEL_STATE="$(systemctl is-active wfgg-collector-sentinel.timer 2>/dev/null || true)"

echo "RADAR_SENTINEL_TIMER=$RADAR_SENTINEL_STATE"
echo "RADAR_SENTINEL_ENABLED=$RADAR_SENTINEL_ENABLED"
echo "COLLECTOR_SENTINEL_TIMER=$COLLECTOR_SENTINEL_STATE"

[ "$RADAR_SENTINEL_STATE" = "active" ] || {
  echo "RADAR_RUNTIME_ADAPTER_PILOT=BLOCKED reason=radar_sentinel_not_active"
  exit 2
}
[ "$RADAR_SENTINEL_ENABLED" = "enabled" ] || {
  echo "RADAR_RUNTIME_ADAPTER_PILOT=BLOCKED reason=radar_sentinel_not_enabled"
  exit 2
}
[ "$COLLECTOR_SENTINEL_STATE" = "active" ] || {
  echo "RADAR_RUNTIME_ADAPTER_PILOT=BLOCKED reason=collector_sentinel_not_active"
  exit 2
}

mkdir -p "$RELEASE" "$EVIDENCE_DIR" "$HEALTH_DIR"

curl -fsSL "$RAW/dev-hub/adapters/radar-runtime-adapter.py" -o "$RELEASE/radar-runtime-adapter"
chmod 0755 "$RELEASE/radar-runtime-adapter"
python3 -m py_compile "$RELEASE/radar-runtime-adapter"
ADAPTER_SHA="$(sha256sum "$RELEASE/radar-runtime-adapter" | awk '{print $1}')"
echo "RADAR_RUNTIME_ADAPTER_SHA256=$ADAPTER_SHA"

cat > "$WORK/status-envelope.json" <<'JSON'
{
  "schema": "chacha.dev/dispatch-envelope/v1",
  "project": "wfgg-radar",
  "transition": "OPERATE->OPERATE",
  "run_id": "radar-runtime-adapter-pilot-status",
  "wave": 1,
  "task": {
    "id": "radar-runtime:status",
    "kind": "runtime-status",
    "description": "Read WfGg Radar runtime and Sentinel state.",
    "owner_role": "sre-observability",
    "permission": "read",
    "outputs": [{"type":"artifact","id":"radar-runtime-status"}],
    "verification": {
      "mode": "machine",
      "self_certification_allowed": false,
      "required_evidence": ["source","timestamp","digest"]
    }
  },
  "bindings": [{
    "capability": "radar-runtime-inspect",
    "provider": "radar-vps-runtime",
    "adapter": "radar-runtime-adapter",
    "fallback_used": false,
    "health_state": "HEALTHY"
  }],
  "policy_context": {
    "resource_class": "light",
    "requires_storage_preflight": false,
    "human_approval_required": false,
    "approval_id": null,
    "timeout_seconds": 30
  },
  "workspace": null,
  "metadata": {"radar_runtime":{"action":"status"}}
}
JSON

"$RELEASE/radar-runtime-adapter" < "$WORK/status-envelope.json" > "$WORK/status-result.json"

python3 - "$WORK/status-result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['schema']=='chacha.dev/task-result/v1',x
assert x['project']=='wfgg-radar',x
assert x['task_id']=='radar-runtime:status',x
assert x['status']=='OK',x
assert x['producer']=='radar-runtime-adapter',x
assert x['verification']['status']=='UNVERIFIED',x
details=(x.get('evidence') or [{}])[0].get('details') or {}
assert details.get('radar_service')=='active',details
assert details.get('radar_sentinel_timer')=='active',details
assert details.get('radar_sentinel_enabled')=='enabled',details
assert details.get('collector_sentinel_timer')=='active',details
print('RADAR_RUNTIME_ADAPTER_STATUS_PROBE=PASS')
print('RADAR_RUNTIME_ADAPTER_SELF_VERIFIED=NO')
PY

ln -sfn "$RELEASE" "$CURRENT"

python3 - "$EVIDENCE_DIR/radar-runtime-adapter-pilot-$STAMP.json" "$STAMP" "$RELEASE" "$ADAPTER_SHA" "$REV" "$WORK/status-result.json" <<'PY'
import json,sys
path,stamp,release,digest,revision,status_path=sys.argv[1:7]
status=json.load(open(status_path,encoding='utf-8'))
e={
  "schema":"chacha.dev/radar-runtime-adapter-pilot-evidence/v1",
  "observed_at":stamp,
  "status":"PASS",
  "adapter":"radar-runtime-adapter",
  "provider":"radar-vps-runtime",
  "runtime_path":release+"/radar-runtime-adapter",
  "current_path":"/opt/chacha-dev/adapters/radar-runtime/current/radar-runtime-adapter",
  "source_revision":revision,
  "digest":"sha256:"+digest,
  "checks":{
    "python_compile":"PASS",
    "runtime_status":"PASS",
    "result_contract":"PASS",
    "self_verification":"NO",
    "radar_sentinel_active":"PASS",
    "collector_sentinel_active":"PASS",
    "production_radar_mutation":"NO"
  },
  "promotion":{"automatic":False}
}
open(path,"w",encoding="utf-8").write(json.dumps(e,indent=2)+"\n")
PY

python3 - "$HEALTH_DIR/providers.json" "$STAMP" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); observed=sys.argv[2]
if p.exists():
    try: x=json.loads(p.read_text(encoding='utf-8'))
    except Exception: x={}
else:
    x={}
if x.get('schema')!='chacha.dev/provider-health-snapshot/v1':
    x={"schema":"chacha.dev/provider-health-snapshot/v1","observed_at":observed,"providers":{}}
x["observed_at"]=observed
x.setdefault("providers",{})["radar-vps-runtime"]={
    "state":"HEALTHY",
    "source":"radar-runtime-adapter-pilot",
    "checked_at":observed
}
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(x,indent=2)+"\n",encoding='utf-8')
PY

echo "RADAR_RUNTIME_ADAPTER_CURRENT=$CURRENT/radar-runtime-adapter"
echo "RADAR_RUNTIME_ADAPTER_HEALTH=HEALTHY"
echo "RADAR_RUNTIME_ADAPTER_PRODUCTION_RADAR_MUTATION=NO"
echo "RADAR_RUNTIME_ADAPTER_PILOT_RUNTIME=PASS"
