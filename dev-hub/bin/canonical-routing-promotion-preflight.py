#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
DEV=HERE.parent
CFG=DEV/"config"

REGISTRY=CFG/"canonical-route-registry.v1.json"
CATALOG=CFG/"sovereign-capability-catalog.v1.json"
PROJECTION_GATE=HERE/"canonical-route-projection-gate.py"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--candidate-root",type=Path,required=True)
    ap.add_argument("--receipt",type=Path,required=True)
    a=ap.parse_args()

    catalog=json.loads(
        CATALOG.read_text(encoding="utf-8")
    )

    services=catalog.get("services",{})

    required={
        name:svc
        for name,svc in services.items()
        if svc.get("required") is True
    }

    gaps=[]

    for name,svc in sorted(required.items()):
        state=svc.get("sovereign_state")

        if state!="LOCAL_PRIMARY":
            gaps.append({
                "service":name,
                "reason":state
            })

    projection_receipt=a.receipt.with_suffix(
        ".projection.json"
    )

    p=subprocess.run(
        [
            sys.executable,
            str(PROJECTION_GATE),
            "--root",str(a.candidate_root),
            "--registry",str(REGISTRY),
            "--receipt",str(projection_receipt)
        ],
        text=True,
        capture_output=True
    )

    projection=json.loads(
        projection_receipt.read_text()
    )

    status=(
        "PASS"
        if p.returncode==0 and not gaps
        else "BLOCK"
    )

    receipt={
        "schema":
            "chacha.dev/canonical-routing-promotion-preflight/v2",

        "status":status,

        "candidate_root":str(a.candidate_root),

        "projection_gate_status":
            projection.get("status"),

        "unknown_projections":
            projection.get("unknown_route_count"),

        "ambiguous_projections":
            projection.get("ambiguous_route_count"),

        "required_sovereign_services":
            sorted(required),

        "sovereign_gaps":
            gaps,

        "inventory_source":
            "CANONICAL_ROUTE_REGISTRY",

        "fixed_component_inventory":
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

    print("ROUTING_PROMOTION_PREFLIGHT="+status)
    print("REQUIRED_SOVEREIGN_SERVICES="+str(len(required)))
    print("SOVEREIGN_GAPS="+str(len(gaps)))

    for gap in gaps:
        print(
            "GAP="
            +gap["service"]
            +":"
            +str(gap["reason"])
        )

    return 0 if status=="PASS" else 20

if __name__=="__main__":
    raise SystemExit(main())
