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
  "$SRC/dev-hub/tests/test_v639_controlled_production_handoff.py"

for f in \
  "$SRC/dev-hub/config/controlled-production-handoff.v1.json" \
  "$SRC/dev-hub/config/controlled-production-adapter-dry-run.v1.json" \
  "$SRC/dev-hub/config/cloudflare-pages-production-adapter.v1.json" \
  "$SRC/dev-hub/config/provider-adapters.v1.json" \
  "$SRC/dev-hub/config/adapter-provisioning.v1.json" \
  "$SRC/dev-hub/config/adapter-rollbacks.v1.json" \
  "$SRC/dev-hub/config/lifecycle.v1.json" \
  "$SRC/dev-hub/config/project-control.v1.json"; do
  python3 -m json.tool "$f" >/dev/null
done
echo "CHACHA_DEV_V639_STATIC=PASS"

echo "CHACHA_DEV_V639_STAGE=cloudflare-pages-static-contract"
python3 "$SRC/dev-hub/bin/qualify-cloudflare-pages-production-adapter.py" \
  --evidence "$WORK/cloudflare-pages-static-contract-evidence.json" \
  --report "$WORK/cloudflare-pages-static-contract-report.json" \
  | tee "$WORK/cloudflare-pages-static-contract.out"
grep -Fq "CHACHA_DEV_V639_CF_PAGES_STATIC_CONTRACT=PASS" "$WORK/cloudflare-pages-static-contract.out"
grep -Fq "CHACHA_DEV_V639_CF_PAGES_NETWORK_WRITE_TEST=NO" "$WORK/cloudflare-pages-static-contract.out"
grep -Fq "CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO" "$WORK/cloudflare-pages-static-contract.out"

echo "CHACHA_DEV_V639_STAGE=contract-ok-promotion-plan"
python3 "$SRC/dev-hub/bin/adapter-promotion.py" \
  --registry "$SRC/dev-hub/config/provider-adapters.v1.json" \
  --contract "$SRC/dev-hub/config/adapter-contract.v1.json" \
  --policy "$SRC/dev-hub/config/adapter-promotion.v1.json" \
  --evidence "$WORK/cloudflare-pages-static-contract-evidence.json" \
  --report "$WORK/cloudflare-pages-contract-ok-plan.json" \
  --json \
  plan \
  --adapter cloudflare-pages-production-adapter \
  --target CONTRACT_OK \
  > "$WORK/cloudflare-pages-contract-ok-plan.out"
python3 - "$WORK/cloudflare-pages-contract-ok-plan.out" "$SRC/dev-hub/config/provider-adapters.v1.json" <<'PY'
import json,sys
plan=json.load(open(sys.argv[1],encoding="utf-8"))
registry=json.load(open(sys.argv[2],encoding="utf-8"))
assert plan["adapter"]=="cloudflare-pages-production-adapter",plan
assert plan["current_status"]=="DESIGNED",plan
assert plan["target_status"]=="CONTRACT_OK",plan
assert plan["eligible"] is True,plan
assert plan["applied"] is False,plan
assert plan["approval_required"] is False,plan
entry=registry["adapters"]["cloudflare-pages-production-adapter"]
assert entry["status"]=="DESIGNED",entry
assert entry["executable"] is None,entry
print("CHACHA_DEV_V639_CF_PAGES_CONTRACT_OK_ELIGIBLE=PASS")
print("CHACHA_DEV_V639_CF_PAGES_REGISTRY_MUTATION=NO")
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
  CHACHA_DEV_V639_CLOUDFLARE_PAGES_PRODUCTION_ADAPTER=DESIGNED \
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
echo "CHACHA_DEV_V639_CF_PAGES_CONTRACT_OK_ELIGIBLE=PASS"
echo "CHACHA_DEV_V639_CF_PAGES_REGISTRY_MUTATION=NO"
echo "CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V639_DRY_RUN_PILOT=PASS"
