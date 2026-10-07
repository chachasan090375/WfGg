#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

HERE=Path(__file__).resolve().parent

resolver_path=HERE/"canonical-route-resolver.py"

spec=importlib.util.spec_from_file_location(
    "canonical_route_resolver",
    resolver_path
)

mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

resolve=mod.resolve
RouteResolutionError=mod.RouteResolutionError

TOKEN=re.compile(
    r"chacha-route://([A-Za-z0-9_.:-]+)"
)

TEXT_EXTENSIONS={
    ".py",".sh",".json",".js",".mjs",".cjs",".ts",
    ".yaml",".yml",".toml",".ini",".conf",".service",
    ".md",".txt"
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()

    ap.add_argument(
        "--source",
        type=Path,
        required=True
    )

    ap.add_argument(
        "--output",
        type=Path,
        required=True
    )

    ap.add_argument(
        "--registry",
        type=Path,
        required=True
    )

    ap.add_argument(
        "--manifest",
        type=Path,
        required=True
    )

    a=ap.parse_args()

    registry_sha=sha(a.registry)

    if a.output.exists():
        shutil.rmtree(a.output)

    a.output.mkdir(
        parents=True,
        exist_ok=True
    )

    projections=[]

    try:
        for src in a.source.rglob("*"):
            if ".git" in src.parts:
                continue

            rel=src.relative_to(a.source)
            dst=a.output/rel

            if src.is_dir():
                dst.mkdir(
                    parents=True,
                    exist_ok=True
                )
                continue

            dst.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            if src.suffix.lower() not in TEXT_EXTENSIONS:
                shutil.copy2(src,dst)
                continue

            text=src.read_text(
                encoding="utf-8",
                errors="ignore"
            )

            occurrences=[]

            def repl(match):
                capability=match.group(1)

                resolved=resolve(
                    capability,
                    registry_path=a.registry
                )

                occurrences.append({
                    "route_key":capability,
                    "resolved_value":resolved
                })

                return resolved

            compiled=TOKEN.sub(
                repl,
                text
            )

            dst.write_text(
                compiled,
                encoding="utf-8"
            )

            if occurrences:
                projections.append({
                    "file":str(rel),
                    "routes":occurrences
                })

    except RouteResolutionError as exc:
        print("ROUTE_COMPILER=BLOCK")
        print("REASON="+str(exc))
        return 20

    manifest={
        "schema":
            "chacha.dev/canonical-route-materialization-manifest/v1",

        "registry_sha256":
            registry_sha,

        "source_root":
            str(a.source),

        "output_root":
            str(a.output),

        "projections":
            projections
    }

    a.manifest.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False
        )+"\n",
        encoding="utf-8"
    )

    print("ROUTE_COMPILER=PASS")
    print(
        "PROJECTED_FILES="
        +str(len(projections))
    )

    print(
        "PROJECTED_ROUTES="
        +str(sum(
            len(x["routes"])
            for x in projections
        ))
    )

    print(
        "REGISTRY_SHA256="
        +registry_sha
    )

    return 0

if __name__=="__main__":
    raise SystemExit(main())
