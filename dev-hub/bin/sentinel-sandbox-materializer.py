#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA = "chacha.dev/sentinel-sandbox-materializer-receipt/v1"
OVERLAY_SCHEMA = "chacha.dev/sentinel-sandbox-overlay-manifest/v1"
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def run(argv: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(argv, cwd=str(cwd) if cwd else None, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("COMMAND_FAILED:" + " ".join(argv) + ":" + p.stderr[-2000:])
    return p.stdout.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_NOT_OBJECT:" + str(path))
    return value


def safe_target(value: str) -> Path:
    p = Path(value)
    if p.is_absolute() or not value or any(part in {"", ".", ".."} for part in p.parts):
        raise ValueError("OVERLAY_TARGET_INVALID:" + value)
    return p


def copy_authoritative_tree(source: Path, destination: Path) -> None:
    for root, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        root_path = Path(root)
        rel_root = root_path.relative_to(source)
        out_root = destination / rel_root
        out_root.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name == ".git" or Path(name).suffix in EXCLUDED_SUFFIXES:
                continue
            src = root_path / name
            dst = out_root / name
            if src.is_symlink():
                if dst.exists() or dst.is_symlink():
                    dst.unlink()
                os.symlink(os.readlink(src), dst)
            else:
                shutil.copy2(src, dst)


def materialize(source: Path, sandbox: Path, overlay_manifest: Path, receipt: Path) -> dict[str, Any]:
    source = source.resolve()
    sandbox = sandbox.resolve()
    if not source.is_dir():
        raise ValueError("SOURCE_ROOT_MISSING")
    source_top = Path(run(["git", "rev-parse", "--show-toplevel"], source)).resolve()
    if source_top != source:
        raise ValueError("SOURCE_ROOT_MUST_BE_GIT_TOPLEVEL")
    tracked_changes = [line for line in run(["git", "status", "--porcelain"], source).splitlines()
                       if line and not line.startswith("??")]
    if tracked_changes:
        raise ValueError("AUTHORITATIVE_SOURCE_TRACKED_DIRTY")
    source_head = run(["git", "rev-parse", "HEAD"], source)
    spec = load_json(overlay_manifest)
    if spec.get("schema") != OVERLAY_SCHEMA:
        raise ValueError("OVERLAY_SCHEMA_INVALID")
    overlays = spec.get("overlays") or []
    if not isinstance(overlays, list) or not overlays:
        raise ValueError("OVERLAY_LIST_EMPTY")
    if sandbox.exists():
        raise ValueError("SANDBOX_ALREADY_EXISTS")
    sandbox.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="." + sandbox.name + ".tmp-", dir=str(sandbox.parent)))
    overlay_rows: list[dict[str, str]] = []
    try:
        run(["git", "clone", "--quiet", "--no-hardlinks", str(source), str(staging)])
        run(["git", "checkout", "--quiet", "--detach", source_head], staging)
        run(["git", "config", "user.name", "ChaCha DEV Sentinel Sandbox"], staging)
        run(["git", "config", "user.email", "chacha-dev@local.invalid"], staging)
        copy_authoritative_tree(source, staging)
        run(["git", "add", "-A"], staging)
        if run(["git", "status", "--porcelain"], staging):
            run(["git", "commit", "--quiet", "-m", "materialize authoritative Sentinel source bundle"], staging)
        bundle_base_head = run(["git", "rev-parse", "HEAD"], staging)
        targets: list[str] = []
        for row in overlays:
            if not isinstance(row, dict):
                raise ValueError("OVERLAY_ENTRY_INVALID")
            src = Path(str(row.get("source") or "")).resolve()
            target = safe_target(str(row.get("target") or ""))
            expected = str(row.get("sha256") or "").removeprefix("sha256:")
            if not src.is_file():
                raise ValueError("OVERLAY_SOURCE_MISSING:" + str(src))
            observed = sha256(src)
            if expected and observed != expected:
                raise ValueError("OVERLAY_DIGEST_MISMATCH:" + str(src))
            dst = staging / target
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            targets.append(str(target))
            overlay_rows.append({"source": str(src), "target": str(target), "sha256": observed})
        run(["git", "add", "--"] + targets, staging)
        if not run(["git", "status", "--porcelain"], staging):
            raise ValueError("OVERLAY_PRODUCED_NO_DELTA")
        run(["git", "commit", "--quiet", "-m", "apply exact Sentinel candidate overlay"], staging)
        candidate_head = run(["git", "rev-parse", "HEAD"], staging)
        changed = sorted(x for x in run(["git", "diff", "--name-only", bundle_base_head, candidate_head], staging).splitlines() if x)
        if changed != sorted(targets):
            raise ValueError("OVERLAY_DELTA_NOT_EXACT:" + json.dumps(changed))
        os.replace(staging, sandbox)
        out = {
            "schema": RECEIPT_SCHEMA,
            "status": "PASS",
            "source_root": str(source),
            "source_head": source_head,
            "sandbox": str(sandbox),
            "bundle_base_head": bundle_base_head,
            "candidate_head": candidate_head,
            "candidate_delta": changed,
            "overlays": overlay_rows,
            "sandbox_only": True,
            "production_mutation": False,
            "automatic_external_spend_eur": 0,
        }
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return out
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description="Materialize an atomic Sentinel sandbox from one authoritative source bundle")
    ap.add_argument("--source-root", required=True, type=Path)
    ap.add_argument("--sandbox", required=True, type=Path)
    ap.add_argument("--overlay-manifest", required=True, type=Path)
    ap.add_argument("--receipt", required=True, type=Path)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("EXPLICIT_APPLY_REQUIRED")
    out = materialize(args.source_root, args.sandbox, args.overlay_manifest, args.receipt)
    print("CHACHA_DEV_SENTINEL_SANDBOX_MATERIALIZER=PASS")
    print("SOURCE_HEAD=" + out["source_head"])
    print("BUNDLE_BASE_HEAD=" + out["bundle_base_head"])
    print("CANDIDATE_HEAD=" + out["candidate_head"])
    print("CANDIDATE_DELTA_COUNT=" + str(len(out["candidate_delta"])))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
