#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V639_REV:-}"
REPO="chachasan090375/WfGg"
WORK="/tmp/chacha-dev-v639-target-read-$(date -u +%Y%m%dT%H%M%SZ)"
WF_NAME="ChaCha DEV V6.39 controlled production handoff qualification"

cleanup(){ rm -rf -- "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "CHACHA_DEV_V639_TARGET_READ=BLOCKED reason=pinned_revision_required"
  exit 2
}
for cmd in curl python3 grep; do
  command -v "$cmd" >/dev/null || {
    echo "CHACHA_DEV_V639_TARGET_READ=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done
mkdir -p "$WORK"

API="https://api.github.com/repos/$REPO/actions/runs?head_sha=$REV&per_page=100"
READY=0
RUN_ID=""
for i in $(seq 1 80); do
  curl -fsS -H "Accept: application/vnd.github+json" -H "User-Agent: ChaCha-DEV-V639" "$API" -o "$WORK/runs.json"
  set +e
  RUN_ID="$(python3 - "$WORK/runs.json" "$REV" "$WF_NAME" <<'PY'
import json,sys
p,rev,name=sys.argv[1:]
runs=json.load(open(p,encoding="utf-8")).get("workflow_runs") or []
x=[r for r in runs if r.get("head_sha")==rev and r.get("name")==name]
if not x: raise SystemExit(2)
x.sort(key=lambda r:r.get("run_number",0),reverse=True)
r=x[0]
if r.get("status")!="completed": raise SystemExit(2)
print(r.get("id") or "")
if r.get("conclusion")!="success": raise SystemExit(10)
PY
)"
  RC=$?
  set -e
  if [ "$RC" -eq 0 ]; then READY=1; break; fi
  if [ "$RC" -eq 10 ]; then
    echo "CHACHA_DEV_V639_TARGET_READ=FAILED reason=exact_head_ci_failed"
    exit 10
  fi
  [ "$RC" -eq 2 ] || exit "$RC"
  sleep 15
done
[ "$READY" -eq 1 ] || {
  echo "CHACHA_DEV_V639_TARGET_READ=BLOCKED reason=exact_head_ci_timeout"
  exit 11
}

curl -fsS -H "Accept: application/vnd.github+json" -H "User-Agent: ChaCha-DEV-V639" \
  "https://api.github.com/repos/$REPO/actions/runs/$RUN_ID/jobs?per_page=100" \
  -o "$WORK/jobs.json"

JOB_ID="$(python3 - "$WORK/jobs.json" <<'PY'
import json,sys
jobs=json.load(open(sys.argv[1],encoding="utf-8")).get("jobs") or []
x=[j for j in jobs if j.get("name")=="qualify"]
if not x: raise SystemExit("QUALIFY_JOB_NOT_FOUND")
print(x[0].get("id") or "")
PY
)"

curl -fLsS -H "Accept: application/vnd.github+json" -H "User-Agent: ChaCha-DEV-V639" \
  "https://api.github.com/repos/$REPO/actions/jobs/$JOB_ID/logs" \
  -o "$WORK/job.log"

echo "CHACHA_DEV_V639_TARGET_DISCOVERY_RUN_ID=$RUN_ID"
grep -E 'CHACHA_DEV_V639_CF_PAGES_TARGET_DISCOVERY=|CHACHA_DEV_V639_CF_PAGES_TARGET_DISCOVERY_REASON=|CHACHA_DEV_V639_CF_PAGES_TARGET_COUNT=|^TARGET project=' "$WORK/job.log" || true

if grep -Fq 'CHACHA_DEV_V639_CF_PAGES_TARGET_DISCOVERY=PASS' "$WORK/job.log"; then
  echo "CHACHA_DEV_V639_TARGET_DISCOVERY_READ=PASS"
  exit 0
fi

if grep -Fq 'CHACHA_DEV_V639_CF_PAGES_TARGET_DISCOVERY=BLOCKED' "$WORK/job.log"; then
  echo "CHACHA_DEV_V639_TARGET_DISCOVERY_READ=BLOCKED"
  exit 3
fi

echo "CHACHA_DEV_V639_TARGET_DISCOVERY_READ=FAILED reason=marker_missing"
exit 12
