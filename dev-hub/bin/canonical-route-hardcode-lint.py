#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PATTERNS={
    "HTTP_URL":re.compile(r'https?://[^"\'\s<>]+',re.I),
    "LOOPBACK":re.compile(r'(?:127\.0\.0\.1|localhost)(?::\d+)?',re.I),
    "NAS_PATH":re.compile(r'/share/[A-Za-z0-9._/\-{}]+'),
}

DEFAULT_EXTENSIONS={
    ".py",".sh",".json",".js",".mjs",".cjs",".ts",
    ".yaml",".yml",".toml",".ini",".conf",".service"
}

def scan(root,registry):
    findings=[]

    allowed_exact={
        registry.resolve(),
    }

    skip_parts={
        ".git","__pycache__","node_modules"
    }

    for p in root.rglob("*"):
        if not p.is_file():
            continue

        if any(x in skip_parts for x in p.parts):
            continue

        if p.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue

        if p.resolve() in allowed_exact:
            continue

        rel=str(p.relative_to(root))

        low="/"+rel.lower()+"/"
        if any(x in low for x in (
            "/tests/",
            "/fixtures/",
            "/testdata/",
            "/examples/"
        )):
            continue

        try:
            text=p.read_text(encoding="utf-8",errors="ignore")
        except Exception:
            continue

        for n,line in enumerate(text.splitlines(),1):
            # Logical references are allowed.
            if "chacha-route://" in line or '"$route"' in line:
                continue

            seen=set()

            for kind,rx in PATTERNS.items():
                for m in rx.finditer(line):
                    value=m.group(0)

                    key=(kind,value)
                    if key in seen:
                        continue
                    seen.add(key)

                    # Documentation/schema identifiers are not operational routes.
                    if value.startswith(("http://json-schema.org","https://json-schema.org")):
                        continue

                    findings.append({
                        "file":rel,
                        "line":n,
                        "kind":kind,
                        "value":value
                    })

    return findings

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--registry",type=Path,required=True)
    ap.add_argument("--json-output",type=Path)
    ap.add_argument("--require-zero",action="store_true")
    a=ap.parse_args()

    findings=scan(a.root,a.registry)

    payload={
        "schema":"chacha.dev/canonical-route-hardcode-lint/v1",
        "root":str(a.root),
        "finding_count":len(findings),
        "findings":findings
    }

    if a.json_output:
        a.json_output.write_text(
            json.dumps(payload,indent=2,ensure_ascii=False)+"\n",
            encoding="utf-8"
        )

    print("HARDCODE_FINDINGS="+str(len(findings)))

    if a.require_zero and findings:
        print("HARDcoded_ROUTE_GATE=BLOCK")
        return 20

    print("HARDCODE_ROUTE_SCAN=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
