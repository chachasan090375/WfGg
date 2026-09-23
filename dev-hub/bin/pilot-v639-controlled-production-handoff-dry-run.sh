#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V639_REV:-}"
REPO="chachasan090375/WfGg"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/chacha-dev-v639-dry-run-$STAMP"

cleanup(){ rm -rf -- "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "CHACHA_DEV_V639_DRY_RUN_PILOT=BLOCKED reason=pinned_revision_required"
  exit 2
}

for cmd in curl tar python3 grep; do
  command -v "$cmd" >/dev/null || {
    echo "CHACHA_DEV_V639_DRY_RUN_PILOT=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$WORK/src"
echo "CHACHA_DEV_V639_STAGE=fetch-pinned-source"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REV" -o "$WORK/source.tar.gz"
tar -xzf "$WORK/source.tar.gz" -C "$WORK/src" --strip-components=1
SRC="$WORK/src"

echo "CHACHA_DEV_V639_STAGE=static-validation"
python3 -m py_compile \
  "$SRC/dev-hub/bin/controlled-production-adapter.py" \
  "$SRC/dev-hub/bin/controlled-production-handoff-controller.py" \
  "$SRC/dev-hub/adapters/cloudflare-pages-production-adapter.py" \
  "$SRC/dev-hub/bin/qualify-cloudflare-pages-production-adapter.py" \
  "$SRC/dev-hub/bin/adapter-provision.py" \
  "$SRC/dev-hub/tests/test_v639_controlled_production_handoff.py"

for f in \
  "$SRC/dev-hub/config/controlled-production-handoff.v1.json" \
  "$SRC/dev-hub/config/controlled-production-adapter-dry-run.v1.json" \
  "$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json" \
  "$SRC/dev-hub/config/provider-adapters.v1.json" \
  "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  "$SRC/dev-hub/config/adapter-rollbacks.v1.json" \
  "$SRC/dev-hub/config/lifecycle.v1.json" \
  "$SRC/dev-hub/config/project-control.v1.json" \
  "$SRC/dev-hub/evidence/v639/cloudflare-pages-production-contract-ok-promotion-receipt.json"; do
  python3 -m json.tool "$f" >/dev/null
done
echo "CHACHA_DEV_V639_STATIC=PASS"

echo "CHACHA_DEV_V639_STAGE=cloudflare-pages-post-promotion-contract"
python3 "$SRC/dev-hub/bin/qualify-cloudflare-pages-production-adapter.py" \
  --evidence "$WORK/cloudflare-pages-static-contract-evidence.json" \
  --report "$WORK/cloudflare-pages-static-contract-report.json" \
  | tee "$WORK/cloudflare-pages-static-contract.out"

grep -Fq "CHACHA_DEV_V639_CF_PAGES_STATIC_CONTRACT=PASS" "$WORK/cloudflare-pages-static-contract.out"
grep -Fq "CHACHA_DEV_V639_CF_PAGES_NETWORK_WRITE_TEST=NO" "$WORK/cloudflare-pages-static-contract.out"
grep -Fq "CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO" "$WORK/cloudflare-pages-static-contract.out"

python3 - \
  "$SRC/dev-hub/config/provider-adapters.v1.json" \
  "$SRC/dev-hub/evidence/v639/cloudflare-pages-production-contract-ok-promotion-receipt.json" <<'PY'
import json,sys
registry=json.load(open(sys.argv[1],encoding="utf-8"))
receipt=json.load(open(sys.argv[2],encoding="utf-8"))
entry=registry["adapters"]["cloudflare-pages-production-adapter"]
assert entry["status"]=="CONTRACT_OK",entry
assert entry["executable"] is None,entry
assert receipt["transition"]=="DESIGNED->CONTRACT_OK",receipt
assert receipt["status"]=="COMMITTED",receipt
assert receipt["production_execution_enabled"] is False,receipt
print("CHACHA_DEV_V639_CF_PAGES_CONTRACT_OK=PASS")
print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_EXECUTION=BLOCKED")
PY

echo "CHACHA_DEV_V639_STAGE=cloudflare-pages-sandbox-provisioning"
SANDBOX_ROOT="$WORK/adapter-runtime"
PROV_RECEIPT="$WORK/cloudflare-pages-provisioning-receipt.json"
export CHACHA_CF_PAGES_PROD_POLICY="$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json"
unset CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION || true
unset CLOUDFLARE_API_TOKEN || true
unset CLOUDFLARE_ACCOUNT_ID || true

python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  --root "$SANDBOX_ROOT" \
  plan --adapter cloudflare-pages-production-adapter \
  > "$WORK/cloudflare-pages-provisioning-plan.json"

python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  --root "$SANDBOX_ROOT" \
  apply \
  --adapter cloudflare-pages-production-adapter \
  --actor v639-sandbox-pilot \
  --receipt "$PROV_RECEIPT" \
  --apply \
  | tee "$WORK/cloudflare-pages-provisioning.out"

python3 "$SRC/dev-hub/bin/adapter-provision.py" \
  --policy "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  --root "$SANDBOX_ROOT" \
  verify \
  --adapter cloudflare-pages-production-adapter \
  --receipt "$PROV_RECEIPT" \
  | tee "$WORK/cloudflare-pages-provisioning-verify.out"

grep -Fq "PROVISIONING_VERIFY=PASS" "$WORK/cloudflare-pages-provisioning-verify.out"

python3 - "$PROV_RECEIPT" "$SANDBOX_ROOT" <<'PY'
import json,sys,pathlib
receipt=json.load(open(sys.argv[1],encoding="utf-8"))
root=pathlib.Path(sys.argv[2]).resolve()
exe=pathlib.Path(receipt["executable_path"]).resolve()
assert receipt["schema"]=="chacha.dev/adapter-provisioning-receipt/v1",receipt
assert receipt["adapter"]=="cloudflare-pages-production-adapter",receipt
assert receipt["applied"] is True,receipt
assert receipt["probe"]["status"]=="PASS",receipt
assert exe.is_relative_to(root),(exe,root)
assert receipt["source_digest"]==receipt["installed_digest"]==receipt["executable_digest"],receipt
print("CHACHA_DEV_V639_CF_PAGES_SANDBOX_PROVISIONING=PASS")
print("CHACHA_DEV_V639_CF_PAGES_PROVISIONING_DIGEST_CHAIN=PASS")
print("CHACHA_DEV_V639_CF_PAGES_REAL_VPS_PROVISIONING=NO")
PY

echo "CHACHA_DEV_V639_STAGE=sandbox-two-phase-pilot"
(
  cd "$SRC"
  PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v639_controlled_production_handoff.py
) | tee "$WORK/v639-test.out"

for marker in \
  CHACHA_DEV_V639_PRODUCTION_APPROVAL_BOUNDARY=PASS \
  CHACHA_DEV_V639_RELEASE_OPERATE_TASK_GRAPH=PASS \
  CHACHA_DEV_V639_TRUE_TWO_PHASE_DEPLOYMENT_HANDOFF=PASS \
  CHACHA_DEV_V639_PROTECTED_APPROVAL_TRANSACTION=PASS \
  CHACHA_DEV_V639_CONTROLLED_ADAPTER_DRY_RUN=PASS \
  CHACHA_DEV_V639_ROLLBACK_PROVEN=PASS \
  CHACHA_DEV_V639_OPERATE_ADVANCED=NO \
  CHACHA_DEV_V639_REAL_PRODUCTION_TARGET=NO \
  CHACHA_DEV_V639_CLOUDFLARE_PAGES_PRODUCTION_ADAPTER=CONTRACT_OK \
  CHACHA_DEV_V639_CLOUDFLARE_PAGES_PRODUCTION_EXECUTION=BLOCKED \
  CHACHA_DEV_V639_CLOUDFLARE_PAGES_ROLLBACK_CONTRACT=PASS \
  CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0; do
  grep -Fq "$marker" "$WORK/v639-test.out"
done

if grep -Fq 'CHACHA_DEV_V639_INSTALL=PASS' "$WORK/v639-test.out"; then
  echo "CHACHA_DEV_V639_DRY_RUN_PILOT=FAILED reason=install_pass_forbidden_in_dry_run"
  exit 20
fi

echo "CHACHA_DEV_V639_PLATFORM_CURRENT_MUTATION=NO"
echo "CHACHA_DEV_V639_PRODUCTION_MUTATION=NO"
echo "CHACHA_DEV_V639_REAL_PRODUCTION_TARGET=NO"
echo "CHACHA_DEV_V639_OPERATE_ADVANCED=NO"
echo "CHACHA_DEV_V639_CLOUDFLARE_PAGES_PRODUCTION_EXECUTION=BLOCKED"
echo "CHACHA_DEV_V639_CF_PAGES_STATIC_CONTRACT=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_CONTRACT_OK=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_SANDBOX_PROVISIONING=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_REAL_VPS_PROVISIONING=NO"
echo "CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V639_DRY_RUN_PILOT=PASS"
