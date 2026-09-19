#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_DESIGN_REV:-}"
PROJECT="${WFGG_DEV_HUB_PROJECT:-}"
REQUIREMENT="${WFGG_DEV_HUB_REQUIREMENT:-}"
MANIFEST="${WFGG_DEV_HUB_MANIFEST:-}"
WORK="$(mktemp -d /tmp/chacha-technical-design.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"

cleanup(){ rm -rf "$WORK"; }
trap cleanup EXIT

die(){ echo "TECHNICAL_DESIGN_RUNTIME=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
[ -n "$PROJECT" ] || die project_required
[ -n "$REQUIREMENT" ] || die requirement_required
[ -n "$MANIFEST" ] || die manifest_required

for cmd in curl tar python3 grep; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing_command:$cmd"
done

echo "=== CHACHA DEV PRODUCT -> TECHNICAL DESIGN ==="
echo "SOURCE_REV=$REV"
echo "PROJECT=$PROJECT"
echo "REQUIREMENT=$REQUIREMENT"
echo "MANIFEST=$MANIFEST"

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
REPO="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -n "$REPO" ] && [ -d "$REPO/dev-hub" ] || die repo_extract_failed

[ -f "$REPO/$REQUIREMENT" ] || die requirement_not_found
[ -f "$REPO/$MANIFEST" ] || die manifest_not_found

cd "$REPO"

python3 -m py_compile   dev-hub/bin/project-control-cli.py   dev-hub/bin/technical-design-router.py

OUT="$WORK/project-control-response.json"

python3 dev-hub/bin/project-control-cli.py   --repo-root "$REPO"   --policy dev-hub/config/project-control.v1.json   --json   technical-design   --project "$PROJECT"   --requirement "$REQUIREMENT"   --manifest "$MANIFEST"   > "$OUT"

python3 - "$OUT" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
assert x['schema']=='chacha.dev/project-control-response/v1',x
assert x['operation']=='technical-design',x
assert x['status']=='READY',x
d=x.get('details') or {}
assert d.get('code_generation_allowed') is False,d
roles=d.get('specialist_roles') or []
print('PROJECT_CONTROL_TECHNICAL_DESIGN=PASS')
print('TECHNICAL_DESIGN_STATUS='+str(x['status']))
print('REQUIREMENT_ID='+str(d.get('requirement_id')))
print('AFFECTED_COMPONENTS='+','.join(d.get('affected_components') or []))
print('SPECIALIST_ROLES='+','.join(roles))
print('BACKEND_ARCHITECT='+('YES' if d.get('backend_architect') else 'NO'))
print('DATA_ARCHITECT='+('YES' if d.get('data_architect') else 'NO'))
print('CODE_GENERATION_ALLOWED=NO')
print('IMPLEMENTATION_GATE=CLOSED')
print('TECHNICAL_DESIGN_PLAN='+str(d.get('technical_design_plan')))
print('TECHNICAL_DESIGN_TASK_GRAPH='+str(d.get('technical_design_task_graph')))
print('IMPLEMENTATION_BLOCKERS='+','.join(d.get('implementation_blockers') or []))
PY

echo "RADAR_PRODUCTION_MUTATION=NO"
echo "TECHNICAL_DESIGN_RUNTIME=PASS"
