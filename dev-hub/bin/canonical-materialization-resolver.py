#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

def registry_path() -> Path:
    override=os.environ.get("CHACHA_CANONICAL_ROUTE_REGISTRY")
    if override:
        return Path(override).expanduser().resolve()

    return (
        Path(__file__).resolve().parents[1]
        / "config"
        / "canonical-route-registry.v1.json"
    )

def load_registry() -> dict[str,Any]:
    path=registry_path()

    with path.open("r",encoding="utf-8") as f:
        data=json.load(f)

    if not isinstance(data,dict):
        raise RuntimeError("CANONICAL_REGISTRY_INVALID")

    return data

def entries() -> dict[str,Any]:
    root=load_registry()

    block=root.get("materialization_bindings")
    if not isinstance(block,dict):
        raise RuntimeError("MATERIALIZATION_BINDINGS_MISSING")

    values=block.get("entries")
    if not isinstance(values,dict):
        raise RuntimeError("MATERIALIZATION_ENTRIES_MISSING")

    return values

def route(route_key:str) -> dict[str,Any]:
    values=entries()

    if route_key not in values:
        raise KeyError(
            "UNKNOWN_MATERIALIZATION_ROUTE:"+route_key
        )

    value=values[route_key]

    if not isinstance(value,dict):
        raise RuntimeError(
            "MATERIALIZATION_ROUTE_INVALID:"+route_key
        )

    return value

def backend(route_key:str) -> str:
    value=route(route_key).get("backend")

    if not isinstance(value,dict):
        raise RuntimeError(
            "BACKEND_BINDING_MISSING:"+route_key
        )

    result=value.get("value")

    if not isinstance(result,str) or not result:
        raise RuntimeError(
            "BACKEND_VALUE_MISSING:"+route_key
        )

    return result

def argument(route_key:str,name:str) -> dict[str,Any]:
    args=route(route_key).get("arguments")

    if not isinstance(args,dict):
        raise RuntimeError(
            "ARGUMENT_BINDINGS_MISSING:"+route_key
        )

    if name not in args:
        raise KeyError(
            "UNKNOWN_MATERIALIZATION_ARGUMENT:"
            +route_key+":"+name
        )

    result=args[name]

    if not isinstance(result,dict):
        raise RuntimeError(
            "ARGUMENT_BINDING_INVALID:"
            +route_key+":"+name
        )

    return result

def main() -> int:
    ap=argparse.ArgumentParser()

    ap.add_argument(
        "--route",
        required=True
    )

    ap.add_argument(
        "--backend",
        action="store_true"
    )

    ap.add_argument(
        "--pattern",
        action="store_true"
    )

    ap.add_argument(
        "--argument"
    )

    ap.add_argument(
        "--field",
        choices=("source","value")
    )

    ap.add_argument(
        "--json",
        action="store_true"
    )

    a=ap.parse_args()

    if a.backend:
        value=backend(a.route)

    elif a.pattern:
        value=route(a.route).get("pattern")

    elif a.argument:
        value=argument(a.route,a.argument)

        if a.field:
            value=value.get(a.field)

    else:
        value=route(a.route)

    if a.json or isinstance(value,(dict,list)):
        print(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True
            )
        )
    elif value is None:
        return 4
    else:
        print(value)

    return 0

if __name__=="__main__":
    raise SystemExit(main())
