#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_ARCHITECT_REV:-}"
RAW_ARCHIVE="https://codeload.github.com/chachasan090375/WfGg/tar.gz/${REV}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d /tmp/chacha-architect-bootstrap.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
RECEIPT_ROOT="/opt/chacha-dev/runtime/adapter-provisioning"
RECEIPT="$RECEIPT_ROOT/architecture-specialist-adapter-$STAMP.json"
QUAL_ROOT="/opt/chacha-dev/runtime/adapter-promotions/architecture-specialist-adapter/$STAMP"
PROBE_RESULT="$QUAL_ROOT/inference-probe.json"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

die(){ echo "ARCHITECTURE_SPECIALIST_BOOTSTRAP=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required

for cmd in curl tar python3 sha256sum mkdir; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

[ -x /usr/local/bin/agy-dev ] || die agy_dev_missing

echo "=== CHACHA DEV ARCHITECTURE SPECIALIST BOOTSTRAP ==="
echo "SOURCE_REV=$REV"
echo "AGY_DEV=/usr/local/bin/agy-dev"

/usr/local/bin/agy-dev --version | head -1 | sed 's/^/AGY_DEV_VERSION=/'

mkdir -p "$RECEIPT_ROOT" "$QUAL_ROOT"

curl -fsSL "$RAW_ARCHIVE" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed

cd "$REPO"
python3 -m py_compile   dev-hub/bin/adapter-provision.py   dev-hub/adapters/architecture-specialist-adapter.py

python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   plan --adapter architecture-specialist-adapter   > "$QUAL_ROOT/provision-plan.json"

python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   apply   --adapter architecture-specialist-adapter   --actor chacha-dev-architecture-bootstrap   --receipt "$RECEIPT"   --apply

python3 dev-hub/bin/adapter-provision.py   --policy dev-hub/config/adapter-provisioning.v1.json   verify   --adapter architecture-specialist-adapter   --receipt "$RECEIPT"

EXEC="$(python3 - "$RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding='utf-8'))
assert r['adapter']=='architecture-specialist-adapter',r
assert r['applied'] is True,r
assert r['probe']['status']=='PASS',r
assert r['source_digest']==r['installed_digest']==r['executable_digest'],r
print(r['executable_path'])
PY
)"

echo "ARCHITECTURE_SPECIALIST_EXECUTABLE=$EXEC"
echo "ARCHITECTURE_SPECIALIST_PROVISIONING_RECEIPT=$RECEIPT"

cat > "$QUAL_ROOT/inference-envelope.json" <<'JSON'
{
  "schema":"chacha.dev/dispatch-envelope/v1",
  "project":"architecture-specialist-runtime-qualification",
  "transition":"DESIGN->DESIGN",
  "run_id":"architecture-specialist-inference-qualification",
  "wave":1,
  "task":{
    "id":"architecture-specialist:inference-probe",
    "kind":"runtime-contract",
    "description":"Structured planning-only inference qualification for ChaCha DEV Architecture Specialist Runtime.",
    "owner_role":"sre-observability-engineer",
    "permission":"plan",
    "outputs":[{"type":"gate","id":"architecture-specialist-inference-runtime"}],
    "verification":{
      "mode":"machine",
      "self_certification_allowed":false,
      "required_evidence":["source","timestamp","digest"]
    }
  },
  "bindings":[{
    "capability":"architecture-audit",
    "provider":"chacha-dev-architect",
    "adapter":"architecture-specialist-adapter",
    "fallback_used":false,
    "health_state":"HEALTHY"
  }],
  "policy_context":{
    "resource_class":"light",
    "requires_storage_preflight":false,
    "human_approval_required":false,
    "approval_id":null,
    "timeout_seconds":180
  },
  "workspace":null,
  "metadata":{"architecture_specialist":{"action":"inference-probe"}}
}
JSON

set +e
"$EXEC" < "$QUAL_ROOT/inference-envelope.json" > "$PROBE_RESULT"
PROBE_RC=$?
set -e

python3 - "$PROBE_RESULT" "$PROBE_RC" "$RECEIPT" <<'PY'
import hashlib,json,sys
result_path,rc_s,receipt_path=sys.argv[1:4]
rc=int(rc_s)
x=json.load(open(result_path,encoding='utf-8'))
r=json.load(open(receipt_path,encoding='utf-8'))
assert rc==0,(rc,x)
assert x['schema']=='chacha.dev/task-result/v1',x
assert x['project']=='architecture-specialist-runtime-qualification',x
assert x['task_id']=='architecture-specialist:inference-probe',x
assert x['producer']=='architecture-specialist-adapter',x
assert x['status']=='OK',x
assert x['verification']['status']=='UNVERIFIED',x
assert x['summary']=='ARCHITECTURE_SPECIALIST_INFERENCE_PROBE_PASS',x
ev=x.get('evidence') or []
assert len(ev)==1,ev
d=ev[0].get('details') or {}
assert d.get('backend')=='antigravity',d
assert d.get('tool_access')=='DENIED_BY_CUSTOM_AGENT',d
assert d.get('sandbox') is True,d
assert d.get('structured_output') is True,d
receipt_digest='sha256:'+hashlib.sha256(open(receipt_path,'rb').read()).hexdigest()
result_digest='sha256:'+hashlib.sha256(open(result_path,'rb').read()).hexdigest()
print('ARCHITECTURE_SPECIALIST_STANDARD_PROVISIONING=PASS')
print('ARCHITECTURE_SPECIALIST_INFERENCE_RUNTIME=PASS')
print('ARCHITECTURE_SPECIALIST_TOOL_ACCESS=DENIED')
print('ARCHITECTURE_SPECIALIST_SANDBOX=PASS')
print('ARCHITECTURE_SPECIALIST_STRUCTURED_OUTPUT=PASS')
print('ARCHITECTURE_SPECIALIST_SELF_VERIFICATION=NO')
print('ARCHITECTURE_SPECIALIST_EXECUTABLE_DIGEST='+str(r['executable_digest']))
print('ARCHITECTURE_SPECIALIST_PROVISIONING_RECEIPT_DIGEST='+receipt_digest)
print('ARCHITECTURE_SPECIALIST_INFERENCE_RESULT_DIGEST='+result_digest)
PY

echo "ARCHITECTURE_SPECIALIST_INFERENCE_RESULT=$PROBE_RESULT"
echo "ARCHITECTURE_SPECIALIST_REGISTRY_MUTATION=NO"
echo "ARCHITECTURE_SPECIALIST_PRODUCTION_MUTATION=NO"
echo "ARCHITECTURE_SPECIALIST_BOOTSTRAP=PASS"
