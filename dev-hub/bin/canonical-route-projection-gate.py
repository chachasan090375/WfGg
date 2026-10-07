#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HTTP=re.compile(
    r'https?://[^"\'\s<>]+',
    re.I
)

LOOPBACK=re.compile(
    r'(?:127\.0\.0\.1|localhost)(?::[A-Za-z0-9_{}$.-]+)?',
    re.I
)

NAS=re.compile(
    r'/share/[A-Za-z0-9._/{}$-]+'
)

TEXT_EXTENSIONS={
    ".py",".sh",".json",".js",".mjs",".cjs",".ts",
    ".yaml",".yml",".toml",".ini",".conf",".service",
    ".md",".txt"
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def overlaps(start,end,spans):
    return any(
        not (end <= a or start >= b)
        for a,b,_ in spans
    )

def extract_routes(line):
    """
    Extraction precedence:
      1. full HTTP(S) URLs
      2. NAS paths
      3. standalone loopbacks

    A loopback contained inside an HTTP URL MUST NOT
    become a second route candidate.
    """
    spans=[]

    for rx in (HTTP,NAS,LOOPBACK):
        for m in rx.finditer(line):
            start,end=m.span()

            if overlaps(start,end,spans):
                continue

            spans.append(
                (start,end,m.group(0))
            )

    spans.sort(key=lambda x:x[0])

    seen=set()
    out=[]

    for _,_,value in spans:
        if value in seen:
            continue

        seen.add(value)
        out.append(value)

    return out

def main():
    ap=argparse.ArgumentParser()

    ap.add_argument(
        "--root",
        type=Path,
        required=True
    )

    ap.add_argument(
        "--registry",
        type=Path,
        required=True
    )

    ap.add_argument(
        "--receipt",
        type=Path,
        required=True
    )

    a=ap.parse_args()

    registry=json.loads(
        a.registry.read_text(
            encoding="utf-8"
        )
    )

    registry_sha=sha(a.registry)

    value_to_keys={}

    for key,route in registry.get(
        "routes",{}
    ).items():

        values=set()

        primary=route.get("primary")

        if primary:
            values.add(str(primary))

        for item in route.get(
            "candidates",[]
        ):
            value=item.get("value")

            if value:
                values.add(str(value))

        for value in values:
            value_to_keys.setdefault(
                value,set()
            ).add(key)

    provenance=[]
    unknown=[]
    ambiguous=[]

    skip_parts={
        ".git",
        "__pycache__",
        "node_modules"
    }

    for p in a.root.rglob("*"):
        if not p.is_file():
            continue

        if any(
            part in skip_parts
            for part in p.parts
        ):
            continue

        if p.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        try:
            text=p.read_text(
                encoding="utf-8",
                errors="ignore"
            )
        except Exception:
            continue

        rel=str(
            p.relative_to(a.root)
        )

        for lineno,line in enumerate(
            text.splitlines(),1
        ):
            for value in extract_routes(line):

                if value.startswith(
                    (
                        "http://json-schema.org",
                        "https://json-schema.org"
                    )
                ):
                    continue

                keys=sorted(
                    value_to_keys.get(
                        value,set()
                    )
                )

                item={
                    "file":rel,
                    "line":lineno,
                    "value":value,
                    "route_keys":keys,
                    "registry_sha256":
                        registry_sha
                }

                if len(keys)==1:
                    provenance.append(item)

                elif len(keys)==0:
                    unknown.append(item)

                else:
                    ambiguous.append(item)

    status=(
        "PASS"
        if not unknown
        and not ambiguous
        else "BLOCK"
    )

    receipt={
        "schema":
            "chacha.dev/canonical-route-projection-gate-receipt/v1",

        "status":
            status,

        "registry_sha256":
            registry_sha,

        "staged_root":
            str(a.root),

        "registered_projections":
            provenance,

        "registered_projection_count":
            len(provenance),

        "unknown_routes":
            unknown,

        "unknown_route_count":
            len(unknown),

        "ambiguous_routes":
            ambiguous,

        "ambiguous_route_count":
            len(ambiguous),

        "authority":
            "CANONICAL_ROUTE_REGISTRY",

        "generated_routes_authoritative":
            False
    }

    a.receipt.write_text(
        json.dumps(
            receipt,
            indent=2,
            ensure_ascii=False
        )+"\n",
        encoding="utf-8"
    )

    print(
        "ROUTE_PROJECTION_GATE="
        +status
    )

    print(
        "REGISTERED_PROJECTIONS="
        +str(len(provenance))
    )

    print(
        "UNKNOWN_PROJECTIONS="
        +str(len(unknown))
    )

    print(
        "AMBIGUOUS_PROJECTIONS="
        +str(len(ambiguous))
    )

    print(
        "REGISTRY_SHA256="
        +registry_sha
    )

    return 0 if status=="PASS" else 20

if __name__=="__main__":
    raise SystemExit(main())
