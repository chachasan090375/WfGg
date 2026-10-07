#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os
from pathlib import Path

SCHEMA="chacha.dev/canonical-route-registry/v1"

class RouteResolutionError(RuntimeError):
    pass

def default_registry():
    p=os.environ.get("CHACHA_ROUTE_REGISTRY")
    if p:
        return Path(p)
    return Path(__file__).resolve().parents[1]/"config"/"canonical-route-registry.v1.json"

def load_registry(path=None):
    p=path or default_registry()
    d=json.loads(p.read_text(encoding="utf-8"))
    if d.get("schema")!=SCHEMA:
        raise RouteResolutionError("CANONICAL_ROUTE_REGISTRY_SCHEMA_MISMATCH")
    return d

def resolve(capability,registry_path=None,allow_external_fallback=False):
    route=load_registry(registry_path).get("routes",{}).get(capability)

    if route is None:
        raise RouteResolutionError("ROUTE_CAPABILITY_NOT_REGISTERED")

    status=route.get("status")

    if status=="QUARANTINED_UNCLASSIFIED":
        raise RouteResolutionError("ROUTE_UNCLASSIFIED_BLOCKED")

    if status=="BLOCKED_SOVEREIGN_GAP":
        raise RouteResolutionError("SOVEREIGN_ROUTE_UNRESOLVED")

    if route.get("primary"):
        return str(route["primary"])

    if allow_external_fallback and route.get("external_fallback_allowed"):
        for item in route.get("candidates",[]):
            if item.get("role")=="EXTERNAL":
                return str(item["value"])

    raise RouteResolutionError("ROUTE_NO_SELECTABLE_ENDPOINT")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("capability")
    ap.add_argument("--registry",type=Path)
    ap.add_argument("--allow-external-fallback",action="store_true")
    a=ap.parse_args()

    try:
        print(resolve(a.capability,a.registry,a.allow_external_fallback))
        return 0
    except RouteResolutionError as exc:
        print(str(exc))
        return 20

if __name__=="__main__":
    raise SystemExit(main())
