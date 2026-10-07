#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

TEXT_SUFFIXES={
    ".py",".sh",".js",".mjs",".cjs",
    ".json",".service",".timer",
    ".yaml",".yml",".toml",".ini",
    ".conf",".md"
}

REFERENCE_DIRS={
    "tests",
    "test",
    "docs",
    "documentation",
    "evidence",
    "fixtures",
    "fixture",
    "archive",
    "archives",
    "historical",
}

def sha(path:pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path:pathlib.Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

def is_reference_only(path:pathlib.Path) -> bool:
    return any(
        part.lower() in REFERENCE_DIRS
        for part in path.parts
    )

def collect_literals(entries:dict[str,Any]) -> list[dict[str,str]]:
    rows=[]

    for route_key,entry in entries.items():
        backend=entry.get("backend",{})

        if (
            isinstance(backend,dict)
            and isinstance(backend.get("value"),str)
            and backend.get("value")
        ):
            rows.append({
                "route":route_key,
                "binding":"backend",
                "value":backend["value"]
            })

        args=entry.get("arguments",{})

        if not isinstance(args,dict):
            continue

        for name,spec in args.items():
            if not isinstance(spec,dict):
                continue

            source=spec.get("source")
            value=spec.get("value")

            if source not in {
                "CANONICAL_COMPONENT_PATH",
                "RUNTIME_TEMPLATE"
            }:
                continue

            if not isinstance(value,str) or not value:
                continue

            rows.append({
                "route":route_key,
                "binding":name,
                "value":value
            })

    return rows


def _canonical_projection_gate():
    """
    Universal canonical materialization invariant.

    The canonical route registry is the sole authority.
    Generated JSON/systemd artifacts are materialized before
    anti-residue validation and must reproduce byte-identically
    in projector CHECK mode.

    Fail closed on any projection or drift error.
    """
    import pathlib
    import subprocess
    import sys

    dev_root=pathlib.Path(__file__).resolve().parents[1]

    projector=dev_root/"bin/canonical-route-projector.py"
    manifest=dev_root/"config/canonical-route-projections.v1.json"
    registry=dev_root/"config/canonical-route-registry.v1.json"

    required=(projector,manifest,registry)

    missing=[
        str(p)
        for p in required
        if not p.is_file()
    ]

    if missing:
        raise RuntimeError(
            "CANONICAL_PROJECTION_REQUIRED_FILE_MISSING:"
            +",".join(missing)
        )

    write_cmd=[
        sys.executable,
        str(projector),
        "--manifest",
        str(manifest),
    ]

    write_run=subprocess.run(
        write_cmd,
        text=True,
        capture_output=True,
    )

    if write_run.returncode != 0:
        raise RuntimeError(
            "CANONICAL_PROJECTION_WRITE_FAILED:"
            +write_run.stderr.strip()
        )

    check_cmd=[
        sys.executable,
        str(projector),
        "--manifest",
        str(manifest),
        "--check",
    ]

    check_run=subprocess.run(
        check_cmd,
        text=True,
        capture_output=True,
    )

    if check_run.returncode != 0:
        raise RuntimeError(
            "CANONICAL_PROJECTION_CHECK_FAILED:"
            +check_run.stderr.strip()
        )

    return {
        "status":"PASS",
        "authority":"CANONICAL_ROUTE_REGISTRY",
        "manifest":str(manifest),
        "projector":str(projector),
        "write_stdout":write_run.stdout.strip(),
        "check_stdout":check_run.stdout.strip(),
    }


def main() -> int:
    ap=argparse.ArgumentParser()

    ap.add_argument(
        "--dev-root",
        type=pathlib.Path,
        required=True
    )

    ap.add_argument(
        "--registry",
        type=pathlib.Path,
        required=True
    )

    ap.add_argument(
        "--output",
        type=pathlib.Path,
        required=True
    )

    a=ap.parse_args()
    projection_gate = _canonical_projection_gate()

    dev=a.dev_root.resolve()
    registry_path=a.registry.resolve()

    registry=load(registry_path)

    block=registry.get("materialization_bindings",{})
    entries=block.get("entries",{})

    if not isinstance(entries,dict):
        raise SystemExit(
            "MATERIALIZATION_ENTRIES_MISSING"
        )

    literals=collect_literals(entries)

    own_files={
        registry_path,
        pathlib.Path(__file__).resolve()
    }

    resolver=(
        pathlib.Path(__file__).resolve().parent
        / "canonical-materialization-resolver.py"
    ).resolve()

    own_files.add(resolver)

    findings=[]

    for path in dev.rglob("*"):
        if not path.is_file():
            continue

        resolved=path.resolve()

        if resolved in own_files:
            continue

        try:
            rel=resolved.relative_to(dev)
        except ValueError:
            continue

        if is_reference_only(rel):
            continue

        if (
            path.suffix.lower() not in TEXT_SUFFIXES
            and path.name not in {
                "Dockerfile",
                "Makefile"
            }
        ):
            continue

        try:
            if path.stat().st_size > 2_000_000:
                continue

            text=path.read_text(
                encoding="utf-8",
                errors="ignore"
            )
        except Exception:
            continue

        lines=text.splitlines()

        for literal in literals:
            value=literal["value"]

            for lineno,line in enumerate(lines,1):
                if value not in line:
                    continue

                findings.append({
                    "file":str(rel),
                    "line":lineno,
                    "route":literal["route"],
                    "binding":literal["binding"],
                    "literal":value,
                    "text":line.strip()[:500]
                })

    network_blob=json.dumps(
        block,
        ensure_ascii=False
    ).lower()

    network_literals=[
        x
        for x in (
            "http://",
            "https://",
            "127.0.0.1",
            "localhost:",
            "workers.dev",
        )
        if x in network_blob
    ]

    status=(
        "PASS"
        if not findings and not network_literals
        else "BLOCK"
    )

    receipt={
        "schema":
            "chacha.dev/canonical-materialization-gate/v1",

        "status":
            status,

        "registry_sha256":
            sha(registry_path),

        "materialization_routes":
            sorted(entries),

        "canonical_literal_count":
            len(literals),

        "blocking_residue_count":
            len(findings),

        "network_literals_in_registry":
            network_literals,

        "blocking_residues":
            findings,

        "policy":{
            "canonical_registry_only":True,
            "reference_directories_excluded":True,
            "operational_literals_forbidden":True,
            "network_endpoints_in_materialization_forbidden":True
        }
    }

    a.output.write_text(
        json.dumps(
            receipt,
            indent=2,
            ensure_ascii=False
        )+"\n",
        encoding="utf-8"
    )

    print("===== MATERIALIZATION ANTI-RESIDUE GATE =====")
    print("STATUS="+status)
    print(
        "CANONICAL_LITERALS="
        +str(len(literals))
    )
    print(
        "BLOCKING_RESIDUES="
        +str(len(findings))
    )
    print(
        "NETWORK_LITERALS_IN_REGISTRY="
        +str(len(network_literals))
    )

    for row in findings[:100]:
        print(
            "RESIDUE="
            +row["file"]
            +":"
            +str(row["line"])
            +" | "
            +row["route"]
            +"."
            +row["binding"]
            +" | "
            +row["literal"]
        )

    print("RECEIPT="+str(a.output))
    print("RECEIPT_SHA256="+sha(a.output))

    return 0 if status=="PASS" else 23

if __name__=="__main__":
    raise SystemExit(main())
