#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

DEV=Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def resolve(resolver,route,binding):
    if binding=="backend":
        cmd=[
            sys.executable,
            str(resolver),
            "--route",route,
            "--backend",
            "--field","value",
        ]
    else:
        cmd=[
            sys.executable,
            str(resolver),
            "--route",route,
            "--argument",binding,
            "--field","value",
        ]

    p=subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )

    if p.returncode != 0:
        raise RuntimeError(
            "CANONICAL_RESOLVER_FAILED:"
            +route+":"+binding+":"
            +p.stderr.strip()
        )

    value=p.stdout.strip()

    try:
        decoded=json.loads(value)
        if isinstance(decoded,str):
            value=decoded
        elif isinstance(decoded,dict):
            value=decoded.get("value",value)
    except Exception:
        pass

    if not isinstance(value,str) or not value:
        raise RuntimeError(
            "CANONICAL_RESOLVER_EMPTY:"
            +route+":"+binding
        )

    return value

def atomic(path,text):
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(text,encoding="utf-8")
    os.replace(tmp,path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument(
        "--manifest",
        default=str(
            DEV/"config/canonical-route-projections.v1.json"
        )
    )
    ap.add_argument(
        "--check",
        action="store_true"
    )
    ap.add_argument(
        "--provenance"
    )
    args=ap.parse_args()

    manifest_path=Path(args.manifest)
    manifest=json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    resolver=DEV/manifest["resolver"]

    resolved={}
    rendered={}

    for entry in manifest["entries"]:
        template=DEV/entry["template"]
        target=DEV/entry["target"]

        text=template.read_text(
            encoding="utf-8"
        )

        for binding in entry["bindings"]:
            key=(
                binding["route"],
                binding["binding"]
            )

            if key not in resolved:
                resolved[key]=resolve(
                    resolver,
                    key[0],
                    key[1]
                )

            token=binding["token"]

            if token not in text:
                raise RuntimeError(
                    "TOKEN_NOT_FOUND:"
                    +entry["target"]+":"
                    +key[0]+":"+key[1]
                )

            text=text.replace(
                token,
                resolved[key]
            )

        if "@@CHACHA_ROUTE:" in text:
            raise RuntimeError(
                "UNRESOLVED_TOKEN:"
                +entry["target"]
            )

        if entry["kind"]=="JSON":
            json.loads(text)

        rendered[entry["target"]]=text

        if args.check:
            if not target.is_file():
                raise RuntimeError(
                    "PROJECTED_TARGET_MISSING:"
                    +entry["target"]
                )

            current=target.read_text(
                encoding="utf-8"
            )

            if current != text:
                raise RuntimeError(
                    "PROJECTION_DRIFT:"
                    +entry["target"]
                )
        else:
            atomic(
                target,
                text
            )

    provenance={
        "schema":
            "chacha.dev/canonical-route-projection-provenance/v1",
        "manifest_sha256":
            sha(manifest_path),
        "resolver_sha256":
            sha(resolver),
        "targets":{},
    }

    for entry in manifest["entries"]:
        target=DEV/entry["target"]
        template=DEV/entry["template"]

        provenance["targets"][
            entry["target"]
        ]={
            "template":
                entry["template"],
            "template_sha256":
                sha(template),
            "projected_sha256":
                sha(target),
            "authority":
                "CANONICAL_ROUTE_REGISTRY",
        }

    if args.provenance:
        path=Path(args.provenance)
        atomic(
            path,
            json.dumps(
                provenance,
                indent=2,
                ensure_ascii=False
            )+"\n"
        )

    print(
        "PROJECTED_TARGETS="
        +str(len(rendered))
    )
    print(
        "RESOLVED_BINDINGS="
        +str(len(resolved))
    )
    print(
        "MODE="
        +("CHECK" if args.check else "WRITE")
    )

    return 0

if __name__=="__main__":
    raise SystemExit(main())
