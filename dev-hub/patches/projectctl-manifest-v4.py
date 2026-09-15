#!/usr/bin/env python3
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

pctl = shutil.which("projectctl")
if not pctl:
    print("PROJECTCTL_NOT_FOUND", file=sys.stderr)
    raise SystemExit(2)

path = Path(pctl).resolve()
text = path.read_text()
backup = path.with_name(path.name + ".backup." + datetime.now().strftime("%Y%m%d_%H%M%S"))
shutil.copy2(path, backup)
print(f"PROJECTCTL={path}")
print(f"BACKUP={backup}")

changed = False

usage_block = (
    "  projectctl manifest-init <name> [--force]\n"
    "  projectctl manifest <name>\n"
    "  projectctl manifest-validate <name>\n"
    "  projectctl manifest-path <name>\n"
    "  projectctl manifest-command <name> <setup|test|build|deploy> <command...>\n"
)

if "projectctl manifest-init <name>" not in text:
    marker = "  projectctl run <name> <command> [args...]\n"
    if marker not in text:
        print("USAGE_PROJECT_MARKER_NOT_FOUND", file=sys.stderr)
        raise SystemExit(3)
    text = text.replace(marker, marker + usage_block, 1)
    changed = True

if "MANIFESTCTL=" not in text:
    marker = 'STORAGE_ENV="${CHACHA_STORAGE_ENV:-$ROOT/platform/config/storage.env}"\n'
    replacement = marker + 'MANIFESTCTL="${CHACHA_MANIFESTCTL:-$ROOT/platform/bin/manifestctl.py}"\n'
    if marker not in text:
        print("CONFIG_MARKER_NOT_FOUND", file=sys.stderr)
        raise SystemExit(4)
    text = text.replace(marker, replacement, 1)
    changed = True

if "cmd_manifest_init()" not in text:
    funcs = r'''manifest_tool() {
  [[ -f "$MANIFESTCTL" ]] || { echo "MANIFESTCTL_MISSING=$MANIFESTCTL" >&2; return 12; }
  printf '%s\n' "$MANIFESTCTL"
}

cmd_manifest_init() {
  local name="${1:-}" force="${2:-}" tool remote=""
  [[ -n "$name" ]] || { usage; return 2; }
  [[ -z "$force" || "$force" == "--force" ]] || { echo "MANIFEST_OPTION_INVALID=$force" >&2; return 2; }
  load_project "$name"
  tool="$(manifest_tool)" || return $?

  local -a args=(
    init
    --name "$NAME"
    --type "${TYPE:-generic}"
    --repo "${REPO:-}"
    --workspace "$WORKSPACE"
  )

  if load_storage >/dev/null 2>&1; then
    remote="$NAS_USER@$NAS_HOST:$(storage_project_root "$NAME")"
    args+=(--nas-storage "$remote")
  fi
  [[ "$force" == "--force" ]] && args+=(--force)

  python3 "$tool" "${args[@]}"
}

cmd_manifest() {
  local name="${1:-}" tool
  [[ -n "$name" ]] || { usage; return 2; }
  load_project "$name"
  tool="$(manifest_tool)" || return $?
  python3 "$tool" show "$NAME"
}

cmd_manifest_validate() {
  local name="${1:-}" tool
  [[ -n "$name" ]] || { usage; return 2; }
  load_project "$name"
  tool="$(manifest_tool)" || return $?
  python3 "$tool" validate "$NAME"
}

cmd_manifest_path() {
  local name="${1:-}" tool
  [[ -n "$name" ]] || { usage; return 2; }
  load_project "$name"
  tool="$(manifest_tool)" || return $?
  python3 "$tool" path "$NAME"
}

cmd_manifest_command() {
  local name="${1:-}" phase="${2:-}" tool
  [[ -n "$name" && -n "$phase" ]] || { usage; return 2; }
  shift 2 || true
  [[ $# -gt 0 ]] || { echo 'MANIFEST_COMMAND_EMPTY' >&2; return 2; }
  load_project "$name"
  tool="$(manifest_tool)" || return $?
  python3 "$tool" set-command "$NAME" "$phase" "$@"
}

'''
    marker = "cmd_doctor() {\n"
    if marker not in text:
        print("DOCTOR_MARKER_NOT_FOUND", file=sys.stderr)
        raise SystemExit(5)
    text = text.replace(marker, funcs + marker, 1)
    changed = True

case_lines = (
    '  manifest-init) shift; cmd_manifest_init "$@" ;;\n'
    '  manifest) shift; cmd_manifest "$@" ;;\n'
    '  manifest-validate) shift; cmd_manifest_validate "$@" ;;\n'
    '  manifest-path) shift; cmd_manifest_path "$@" ;;\n'
    '  manifest-command) shift; cmd_manifest_command "$@" ;;\n'
)

if '  manifest-init) shift; cmd_manifest_init "$@" ;;' not in text:
    marker = '  doctor) shift; cmd_doctor "$@" ;;\n'
    if marker not in text:
        print("CASE_MARKER_NOT_FOUND", file=sys.stderr)
        raise SystemExit(6)
    text = text.replace(marker, case_lines + marker, 1)
    changed = True

if changed:
    path.write_text(text)
    path.chmod(0o755)
    print("PROJECTCTL_MANIFEST_PATCH=APPLIED")
else:
    print("PROJECTCTL_MANIFEST_PATCH=ALREADY_PRESENT")

subprocess.run(["bash", "-n", str(path)], check=True)
print("PROJECTCTL_SYNTAX=OK")

out = subprocess.run([str(path), "--help"], text=True, capture_output=True)
combined = out.stdout + out.stderr
for expected in (
    "projectctl manifest-init <name>",
    "projectctl manifest <name>",
    "projectctl manifest-validate <name>",
    "projectctl manifest-command <name>",
):
    if expected not in combined:
        print(f"PROJECTCTL_HELP_MISSING={expected}", file=sys.stderr)
        raise SystemExit(7)
print("PROJECTCTL_HELP_MANIFEST=OK")
