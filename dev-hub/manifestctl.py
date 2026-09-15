#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "chacha.dev/project-manifest/v1"
VALID_PHASES = ("setup", "test", "build", "deploy")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def root_dir():
    return Path(os.environ.get("CHACHA_DEV_ROOT", "/opt/chacha-dev"))


def manifest_dir():
    p = root_dir() / "registry" / "manifests"
    p.mkdir(parents=True, exist_ok=True)
    return p


def valid_name(name):
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", name or ""))


def manifest_path(name):
    if not valid_name(name):
        raise ValueError("invalid project name")
    return manifest_dir() / f"{name}.json"


def infer_engines(project_type):
    t = (project_type or "generic").strip().lower()
    if t in {"web", "javascript", "js", "node", "frontend", "fullstack"}:
        return ["node", "npm"]
    if t in {"python", "py"}:
        return ["python"]
    if t in {"unity", "unity-assets", "game-assets", "assets"}:
        return ["python", "unitypy", "blender"]
    if t in {"blender", "3d"}:
        return ["blender"]
    return []


def default_manifest(args, existing=None):
    created = (existing or {}).get("created_at") or now_iso()
    nas = args.nas_storage or ""
    project_type = args.type or "generic"
    required_engines = infer_engines(project_type)
    workspace = args.workspace

    return {
        "schema": SCHEMA,
        "name": args.name,
        "type": project_type,
        "repository": {
            "url": args.repo or "",
            "default_branch": "main",
            "source_of_truth": "git",
        },
        "workspace": {
            "local": workspace,
            "root_strategy": "repo-if-cloned-else-workspace",
        },
        "engines": {
            "required": required_engines,
            "optional": [],
        },
        "agents": {
            "enabled": ["antigravity", "skywork"],
            "knowledge": ["mdn", "context7"],
        },
        "storage": {
            "provider": "nas-ssh" if nas else "local",
            "remote": nas,
            "policy": {
                "source_code": "git",
                "large_files": "nas",
                "artifacts": "nas",
                "backups": "nas",
            },
        },
        "commands": {
            "setup": "",
            "test": "",
            "build": "",
            "deploy": "",
        },
        "artifacts": {
            "local": f"{workspace.rstrip('/')}/artifacts",
            "nas_subdir": "artifacts",
        },
        "quality": {
            "health_required": True,
            "manifest_validation_required": True,
        },
        "lifecycle": {
            "development_branch": "dev",
            "production_branch": "main",
            "release_mode": "git",
        },
        "created_at": created,
        "updated_at": now_iso(),
    }


def load(name):
    p = manifest_path(name)
    if not p.is_file():
        print(f"MANIFEST_NOT_FOUND={p}", file=sys.stderr)
        raise SystemExit(3)
    try:
        return p, json.loads(p.read_text())
    except Exception as e:
        print(f"MANIFEST_JSON_ERROR={e}", file=sys.stderr)
        raise SystemExit(4)


def validate_data(data):
    errors = []
    if data.get("schema") != SCHEMA:
        errors.append("schema")
    if not valid_name(data.get("name")):
        errors.append("name")
    if not isinstance(data.get("type"), str) or not data.get("type"):
        errors.append("type")

    repo = data.get("repository")
    if not isinstance(repo, dict) or "url" not in repo:
        errors.append("repository")

    workspace = data.get("workspace")
    if not isinstance(workspace, dict) or not isinstance(workspace.get("local"), str) or not workspace.get("local"):
        errors.append("workspace.local")

    engines = data.get("engines")
    if not isinstance(engines, dict) or not isinstance(engines.get("required"), list):
        errors.append("engines.required")

    agents = data.get("agents")
    if not isinstance(agents, dict) or not isinstance(agents.get("enabled"), list):
        errors.append("agents.enabled")
    if not isinstance(agents, dict) or not isinstance(agents.get("knowledge"), list):
        errors.append("agents.knowledge")

    storage = data.get("storage")
    if not isinstance(storage, dict) or storage.get("provider") not in {"local", "nas-ssh"}:
        errors.append("storage.provider")

    commands = data.get("commands")
    if not isinstance(commands, dict):
        errors.append("commands")
    else:
        for phase in VALID_PHASES:
            if phase not in commands or not isinstance(commands[phase], str):
                errors.append(f"commands.{phase}")

    lifecycle = data.get("lifecycle")
    if not isinstance(lifecycle, dict):
        errors.append("lifecycle")

    return errors


def cmd_init(args):
    if not valid_name(args.name):
        print("MANIFEST_NAME_INVALID", file=sys.stderr)
        return 2
    p = manifest_path(args.name)
    existing = None
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except Exception:
            existing = None
        if not args.force:
            print(f"MANIFEST_ALREADY_EXISTS={p}")
            return cmd_validate(argparse.Namespace(name=args.name))

    data = default_manifest(args, existing=existing)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    p.chmod(0o640)
    print("MANIFEST_INIT=OK")
    print(f"MANIFEST_PATH={p}")
    print(f"MANIFEST_SCHEMA={SCHEMA}")
    print(f"MANIFEST_ENGINES={','.join(data['engines']['required']) or 'none'}")
    print(f"MANIFEST_STORAGE={data['storage']['provider']}")
    return 0


def cmd_show(args):
    p, data = load(args.name)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"MANIFEST_PATH={p}")
    return 0


def cmd_validate(args):
    p, data = load(args.name)
    errors = validate_data(data)
    if errors:
        print("MANIFEST_VALIDATE=FAIL")
        for e in errors:
            print(f"MANIFEST_ERROR={e}")
        return 5
    print("MANIFEST_VALIDATE=OK")
    print(f"MANIFEST_NAME={data['name']}")
    print(f"MANIFEST_TYPE={data['type']}")
    print(f"MANIFEST_SCHEMA={data['schema']}")
    print(f"MANIFEST_PATH={p}")
    return 0


def cmd_path(args):
    print(manifest_path(args.name))
    return 0


def cmd_set_command(args):
    p, data = load(args.name)
    if args.phase not in VALID_PHASES:
        print("MANIFEST_PHASE_INVALID", file=sys.stderr)
        return 2
    command = " ".join(args.command).strip()
    data.setdefault("commands", {})[args.phase] = command
    data["updated_at"] = now_iso()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    p.chmod(0o640)
    print("MANIFEST_COMMAND_SET=OK")
    print(f"MANIFEST_PHASE={args.phase}")
    print(f"MANIFEST_COMMAND={command}")
    return 0


def parser():
    p = argparse.ArgumentParser(prog="manifestctl", description="ChaCha DEV HUB generic project manifest manager")
    sp = p.add_subparsers(dest="sub", required=True)

    i = sp.add_parser("init")
    i.add_argument("--name", required=True)
    i.add_argument("--type", default="generic")
    i.add_argument("--repo", default="")
    i.add_argument("--workspace", required=True)
    i.add_argument("--nas-storage", default="")
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init)

    s = sp.add_parser("show")
    s.add_argument("name")
    s.set_defaults(func=cmd_show)

    v = sp.add_parser("validate")
    v.add_argument("name")
    v.set_defaults(func=cmd_validate)

    pa = sp.add_parser("path")
    pa.add_argument("name")
    pa.set_defaults(func=cmd_path)

    sc = sp.add_parser("set-command")
    sc.add_argument("name")
    sc.add_argument("phase", choices=VALID_PHASES)
    sc.add_argument("command", nargs=argparse.REMAINDER)
    sc.set_defaults(func=cmd_set_command)

    return p


def main():
    args = parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
