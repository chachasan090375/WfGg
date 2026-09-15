#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CHACHA_DEV_ROOT", "/opt/chacha-dev"))
CONFIG = ROOT / "platform" / "config"
REGISTRY = ROOT / "registry"


def run(cmd, timeout=45):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 99, str(e)


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def cmd_status(_args):
    print("=== CHACHA DEV ARCHITECT ===")
    print("AGENT=chacha-dev-architect")

    tools = {
        "projectctl": shutil.which("projectctl"),
        "devhub-health": shutil.which("devhub-health"),
        "techwatch": shutil.which("techwatch"),
        "antigravity": shutil.which("agy-dev") or shutil.which("agy"),
        "git": shutil.which("git"),
        "node": shutil.which("node"),
        "npm": shutil.which("npm"),
        "python": shutil.which("python3"),
        "blender": shutil.which("blender"),
        "rsync": shutil.which("rsync"),
    }
    for name, path in tools.items():
        print(f"TOOL_{name.upper().replace('-', '_')}={'OK' if path else 'MISSING'}")

    agy = shutil.which("agy")
    if agy:
        rc, out = run([agy, "mcp", "list"])
        print(f"MCP_LIST={'OK' if rc == 0 else 'FAIL'}")
        if out:
            print(out)

    health = shutil.which("devhub-health")
    if health:
        rc, out = run([health])
        summary = [x for x in out.splitlines() if x.startswith(("HEALTH_", "DEV_HUB_HEALTH="))]
        for line in summary:
            print(line)
        print(f"PLATFORM_HEALTH={'OK' if rc == 0 else 'CHECK'}")
    return 0


def cmd_radar(_args):
    p = CONFIG / "technology-radar.json"
    data = load_json(p)
    if not data:
        print(f"RADAR_NOT_FOUND={p}", file=sys.stderr)
        return 2
    print(f"RADAR_SCHEMA={data.get('schema','')}")
    for e in data.get("entries", []):
        print(f"{e.get('ring','?'):6} | {e.get('category','?'):24} | {e.get('name','?')}")
    return 0


def cmd_watch_plan(_args):
    p = CONFIG / "tech-watch-sources.json"
    data = load_json(p)
    if not data:
        print(f"WATCH_CONFIG_NOT_FOUND={p}", file=sys.stderr)
        return 2
    print("=== TECH WATCH PLAN ===")
    for k, v in data.get("cadence", {}).items():
        print(f"CADENCE_{k.upper()}={v}")
    for item in data.get("sources", []):
        print(f"WATCH={item.get('category')} :: {','.join(item.get('sources', []))}")
    return 0


def techwatch_bin():
    return shutil.which("techwatch")


def cmd_watch_status(_args):
    tw = techwatch_bin()
    if not tw:
        print("TECHWATCH=MISSING", file=sys.stderr)
        return 2
    return subprocess.run([tw, "status"]).returncode


def cmd_watch_report(_args):
    tw = techwatch_bin()
    if not tw:
        print("TECHWATCH=MISSING", file=sys.stderr)
        return 2
    return subprocess.run([tw, "report"]).returncode


def cmd_watch_run(args):
    tw = techwatch_bin()
    if not tw:
        print("TECHWATCH=MISSING", file=sys.stderr)
        return 2
    cmd = [tw, "run"]
    if args.market:
        cmd.append("--market")
    try:
        return subprocess.run(cmd, timeout=240).returncode
    except subprocess.TimeoutExpired:
        print("TECHWATCH=TIMEOUT", file=sys.stderr)
        return 124


def cmd_audit(args):
    p = REGISTRY / "manifests" / f"{args.name}.json"
    data = load_json(p)
    if not data:
        print(f"MANIFEST_NOT_FOUND_OR_INVALID={p}", file=sys.stderr)
        return 2

    schema = data.get("schema", "")
    print(f"PROJECT={args.name}")
    print(f"SCHEMA={schema}")

    if schema == "chacha.dev/project-manifest/v1":
        print("ARCHITECTURE_MODEL=LEGACY_V1")
        print("MULTICOMPONENT=NO")
        print("RECOMMENDATION=UPGRADE_TO_V2")
        return 0

    if schema != "chacha.dev/project-manifest/v2":
        print("ARCHITECTURE_MODEL=UNKNOWN")
        return 3

    components = data.get("components", [])
    gates = data.get("quality_gates", {})
    unassessed = [k for k, v in gates.items() if v == "UNASSESSED"]
    missing = []
    required_top = ["repository", "workspace", "components", "integrations", "agents", "storage", "security", "quality_gates", "operations", "governance"]
    for key in required_top:
        if key not in data:
            missing.append(key)

    score_base = max(0, 100 - len(unassessed) * 5 - len(missing) * 10)
    print(f"COMPONENTS={len(components)}")
    for c in components:
        print(f"COMPONENT={c.get('name','?')} TYPE={c.get('type','?')} PATH={c.get('path','?')}")
    print(f"UNASSESSED_GATES={len(unassessed)}")
    for g in unassessed:
        print(f"GATE_UNASSESSED={g}")
    for m in missing:
        print(f"REQUIRED_MISSING={m}")
    print(f"ARCHITECTURE_SCORE={score_base}")
    print(f"STATUS={'ACTION_REQUIRED' if unassessed or missing else 'OK'}")
    return 0


def parser():
    p = argparse.ArgumentParser(prog="architectctl", description="ChaCha DEV Architect controller")
    sp = p.add_subparsers(dest="sub", required=True)

    s = sp.add_parser("status")
    s.set_defaults(func=cmd_status)

    r = sp.add_parser("radar")
    r.set_defaults(func=cmd_radar)

    w = sp.add_parser("watch-plan")
    w.set_defaults(func=cmd_watch_plan)

    ws = sp.add_parser("watch-status")
    ws.set_defaults(func=cmd_watch_status)

    wr = sp.add_parser("watch-report")
    wr.set_defaults(func=cmd_watch_report)

    wx = sp.add_parser("watch-run")
    wx.add_argument("--market", action="store_true")
    wx.set_defaults(func=cmd_watch_run)

    a = sp.add_parser("audit")
    a.add_argument("name")
    a.set_defaults(func=cmd_audit)
    return p


def main():
    args = parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
