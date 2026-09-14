#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import bpy


def main() -> int:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) < 3:
        print("WFGG_ASSEMBLE_ERROR usage: <mesh_dir> <blend_out> <glb_out>", flush=True)
        return 2

    mesh_dir = Path(args[0]).resolve()
    blend_out = Path(args[1]).resolve()
    glb_out = Path(args[2]).resolve()
    objs = sorted(mesh_dir.glob("*.obj"))
    if not objs:
        print(f"WFGG_ASSEMBLE_ERROR no_obj:{mesh_dir}", flush=True)
        return 3

    bpy.ops.wm.read_factory_settings(use_empty=True)
    imported = []

    for src in objs:
        before = {o.name for o in bpy.data.objects}
        bpy.ops.wm.obj_import(filepath=str(src))
        new_objects = [o for o in bpy.data.objects if o.name not in before]
        for obj in new_objects:
            obj["wfgg_source_obj"] = src.name
            imported.append(obj)

    mesh_objects = [o for o in imported if o.type == "MESH"]
    vertices = sum(len(o.data.vertices) for o in mesh_objects)
    faces = sum(len(o.data.polygons) for o in mesh_objects)

    blend_out.parent.mkdir(parents=True, exist_ok=True)
    glb_out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_out))

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(glb_out),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
    )

    summary = {
        "schema": "wfgg.blender.assemble.v1",
        "source_obj_count": len(objs),
        "imported_object_count": len(imported),
        "mesh_object_count": len(mesh_objects),
        "vertices": vertices,
        "faces": faces,
        "blend": str(blend_out),
        "glb": str(glb_out),
    }
    summary_path = blend_out.with_suffix(".assemble.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("WFGG_ASSEMBLE_OK", flush=True)
    print(f"WFGG_SOURCE_OBJS={len(objs)}", flush=True)
    print(f"WFGG_MESH_OBJECTS={len(mesh_objects)}", flush=True)
    print(f"WFGG_VERTICES={vertices}", flush=True)
    print(f"WFGG_FACES={faces}", flush=True)
    print(f"WFGG_BLEND={blend_out}", flush=True)
    print(f"WFGG_GLB={glb_out}", flush=True)
    print(f"WFGG_ASSEMBLE_SUMMARY={summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
