#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import importlib.util
_resolver_path=Path(__file__).resolve().parent/"canonical-route-resolver.py"
_spec=importlib.util.spec_from_file_location("canonical_route_resolver",_resolver_path)
_mod=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
resolve=_mod.resolve
RouteResolutionError=_mod.RouteResolutionError

SCHEMA="chacha.dev/canonical-route-materializer/v1"

def materialize_value(value, registry):
    if isinstance(value, dict):
        if set(value.keys()) <= {"$route","allow_external_fallback"} and "$route" in value:
            return resolve(
                str(value["$route"]),
                registry_path=registry,
                allow_external_fallback=bool(value.get("allow_external_fallback",False))
            )
        return {
            k:materialize_value(v,registry)
            for k,v in value.items()
        }

    if isinstance(value,list):
        return [
            materialize_value(v,registry)
            for v in value
        ]

    if isinstance(value,str) and value.startswith("chacha-route://"):
        capability=value[len("chacha-route://"):]
        return resolve(capability,registry_path=registry)

    return value

def materialize_json(source, output, registry):
    data=json.loads(source.read_text(encoding="utf-8"))
    out=materialize_value(data,registry)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(
        json.dumps(out,indent=2,ensure_ascii=False)+"\n",
        encoding="utf-8"
    )

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--registry",type=Path,required=True)
    a=ap.parse_args()

    if a.source.suffix.lower()!=".json":
        raise SystemExit("UNSUPPORTED_SOURCE_FORMAT")

    try:
        materialize_json(a.source,a.output,a.registry)
    except RouteResolutionError as exc:
        print(str(exc))
        return 20

    print("MATERIALIZE=PASS")
    print("SOURCE="+str(a.source))
    print("OUTPUT="+str(a.output))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
