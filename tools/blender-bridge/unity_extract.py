#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import UnityPy


def safe_name(value: str, fallback: str) -> str:
    value = (value or fallback).strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._")
    return value or fallback


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    p = directory / f"{stem}{suffix}"
    if not p.exists():
        return p
    i = 2
    while True:
        p = directory / f"{stem}_{i}{suffix}"
        if not p.exists():
            return p
        i += 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract Unity mesh/texture assets for the WfGg Blender LAB bridge")
    ap.add_argument("bundle", help="Unity bundle/asset file")
    ap.add_argument("outdir", help="Output directory")
    args = ap.parse_args()

    src = Path(args.bundle).expanduser().resolve()
    out = Path(args.outdir).expanduser().resolve()
    mesh_dir = out / "meshes"
    tex_dir = out / "textures"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    tex_dir.mkdir(parents=True, exist_ok=True)

    if not src.is_file():
        print(f"WFGG_UNITY_EXTRACT_ERROR file_not_found:{src}", flush=True)
        return 2

    summary = {
        "schema": "wfgg.unity.extract.v1",
        "source": {"path": str(src), "size_bytes": src.stat().st_size},
        "unitypy_version": getattr(UnityPy, "__version__", "unknown"),
        "object_types": {},
        "meshes": [],
        "textures": [],
        "animations": [],
        "errors": [],
    }

    try:
        env = UnityPy.load(str(src))
    except Exception as exc:
        print(f"WFGG_UNITY_EXTRACT_ERROR load_failed:{type(exc).__name__}:{exc}", flush=True)
        return 3

    objects = list(env.objects)
    counts = Counter(obj.type.name for obj in objects)
    summary["object_types"] = dict(sorted(counts.items()))

    for obj in objects:
        typ = obj.type.name
        if typ == "Mesh":
            try:
                data = obj.parse_as_object()
                name = safe_name(getattr(data, "m_Name", ""), f"Mesh_{obj.path_id}")
                dst = unique_path(mesh_dir, name, ".obj")
                dst.write_text(data.export(), encoding="utf-8", newline="")
                summary["meshes"].append({
                    "name": name,
                    "path_id": obj.path_id,
                    "file": str(dst),
                    "size_bytes": dst.stat().st_size,
                })
            except Exception as exc:
                summary["errors"].append({"type": typ, "path_id": obj.path_id, "error": f"{type(exc).__name__}: {exc}"})

        elif typ == "Texture2D":
            try:
                data = obj.parse_as_object()
                name = safe_name(getattr(data, "m_Name", ""), f"Texture2D_{obj.path_id}")
                dst = unique_path(tex_dir, name, ".png")
                image = data.image
                image.save(dst)
                summary["textures"].append({
                    "name": name,
                    "path_id": obj.path_id,
                    "file": str(dst),
                    "width": int(getattr(data, "m_Width", 0) or 0),
                    "height": int(getattr(data, "m_Height", 0) or 0),
                    "size_bytes": dst.stat().st_size,
                })
            except Exception as exc:
                summary["errors"].append({"type": typ, "path_id": obj.path_id, "error": f"{type(exc).__name__}: {exc}"})

        elif typ == "AnimationClip":
            try:
                data = obj.parse_as_object()
                summary["animations"].append({
                    "name": getattr(data, "m_Name", f"AnimationClip_{obj.path_id}"),
                    "path_id": obj.path_id,
                })
            except Exception as exc:
                summary["errors"].append({"type": typ, "path_id": obj.path_id, "error": f"{type(exc).__name__}: {exc}"})

    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("WFGG_UNITY_EXTRACT_OK", flush=True)
    print(f"WFGG_UNITY_OBJECTS={len(objects)}", flush=True)
    print(f"WFGG_UNITY_MESHES={len(summary['meshes'])}", flush=True)
    print(f"WFGG_UNITY_TEXTURES={len(summary['textures'])}", flush=True)
    print(f"WFGG_UNITY_ANIMATIONS={len(summary['animations'])}", flush=True)
    print(f"WFGG_UNITY_ERRORS={len(summary['errors'])}", flush=True)
    print(f"WFGG_UNITY_SUMMARY={summary_path}", flush=True)

    if not summary["meshes"]:
        print("WFGG_UNITY_NO_MESH_EXPORTED", flush=True)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
