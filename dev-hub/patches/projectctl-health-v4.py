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

if "  projectctl health\n" not in text:
    marker = "Platform:\n  projectctl doctor\n  projectctl engines\n"
    replacement = "Platform:\n  projectctl health\n  projectctl doctor\n  projectctl engines\n"
    if marker not in text:
        print("USAGE_MARKER_NOT_FOUND", file=sys.stderr)
        raise SystemExit(3)
    text = text.replace(marker, replacement, 1)
    changed = True

if "cmd_health()" not in text:
    marker = "cmd_doctor() {\n"
    func = '''cmd_health() {\n  local health="${CHACHA_HEALTH_BIN:-$ROOT/platform/bin/devhub-health}"\n  if [[ ! -x "$health" ]]; then\n    health="$(command -v devhub-health 2>/dev/null || true)"\n  fi\n  [[ -n "$health" && -x "$health" ]] || { echo 'DEV_HUB_HEALTH_TOOL=missing' >&2; return 11; }\n  exec "$health" "$@"\n}\n\n'''
    if marker not in text:
        print("DOCTOR_MARKER_NOT_FOUND", file=sys.stderr)
        raise SystemExit(4)
    text = text.replace(marker, func + marker, 1)
    changed = True

if "  health) shift; cmd_health \"$@\" ;;" not in text:
    marker = "  doctor) shift; cmd_doctor \"$@\" ;;\n"
    replacement = "  health) shift; cmd_health \"$@\" ;;\n" + marker
    if marker not in text:
        print("CASE_MARKER_NOT_FOUND", file=sys.stderr)
        raise SystemExit(5)
    text = text.replace(marker, replacement, 1)
    changed = True

if changed:
    path.write_text(text)
    path.chmod(0o755)
    print("PROJECTCTL_HEALTH_PATCH=APPLIED")
else:
    print("PROJECTCTL_HEALTH_PATCH=ALREADY_PRESENT")

subprocess.run(["bash", "-n", str(path)], check=True)
print("PROJECTCTL_SYNTAX=OK")

out = subprocess.run([str(path), "--help"], text=True, capture_output=True)
if "projectctl health" not in (out.stdout + out.stderr):
    print("PROJECTCTL_HELP_HEALTH=MISSING", file=sys.stderr)
    raise SystemExit(6)
print("PROJECTCTL_HELP_HEALTH=OK")
