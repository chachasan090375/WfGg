#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import bpy


def role_for(name: str) -> str:
    n = name.lower()
    if "shadow" in n:
        return "shadow"
    if "bullet" in n:
        return "accessory_bullet"
    if "lvdai" in n and "high" in n:
        return "lvdai_high"
    if "lvdai" in n:
        return "lvdai"
    if "high" in n:
        return "high"
    return "base"


def main() -> int:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) < 2:
        print("WFGG_VARIANTS_ERROR usage: <mesh_dir> <json_out>", flush=True)
        return 2

    mesh_dir = Path(args[0]).resolve()
    json_out = Path(args[1]).resolve()
    objs = sorted(mesh_dir.glob("*.obj"))
    if not objs:
        print(f"WFGG_VARIANTS_ERROR no_obj:{mesh_dir}", flush=True)
        return 3

    rows = []
    for src in objs:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        before = {o.name for o in bpy.data.objects}
        bpy.ops.wm.obj_import(filepath=str(src))
        new_objects = [o for o in bpy.data.objects if o.name not in before]
        meshes = [o for o in new_objects if o.type == "MESH"]
        vertices = sum(len(o.data.vertices) for o in meshes)
        faces = sum(len(o.data.polygons) for o in meshes)
        dims = [0.0, 0.0, 0.0]
        if meshes:
            xs=[]; ys=[]; zs=[]
            for o in meshes:
                for c in o.bound_box:
                    v = o.matrix_world @ __import__('mathutils').Vector(c)
                    xs.append(v.x); ys.append(v.y); zs.append(v.z)
            if xs:
                dims = [max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)]
        rows.append({
            "file": src.name,
            "bytes": src.stat().st_size,
            "role": role_for(src.name),
            "mesh_objects": len(meshes),
            "vertices": vertices,
            "faces": faces,
            "dimensions": [round(float(x), 6) for x in dims],
        })

    candidates = [r for r in rows if r["role"] not in ("shadow", "accessory_bullet")]
    candidates.sort(key=lambda r: (r["faces"], r["vertices"], r["bytes"]), reverse=True)
    best = candidates[0]["file"] if candidates else None

    out = {
        "schema": "wfgg.blender.variants.v1",
        "source_obj_count": len(rows),
        "suggested_primary_by_complexity": best,
        "objects": rows,
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print("WFGG_VARIANTS_OK", flush=True)
    print(f"WFGG_VARIANTS_COUNT={len(rows)}", flush=True)
    print(f"WFGG_SUGGESTED_PRIMARY={best}", flush=True)
    for r in sorted(rows, key=lambda x: (x["role"], -x["faces"], x["file"])):
        print(f"WFGG_OBJ file={r['file']} role={r['role']} faces={r['faces']} verts={r['vertices']} dims={r['dimensions']}", flush=True)
    print(f"WFGG_VARIANTS_JSON={json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
