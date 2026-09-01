#!/usr/bin/env python3
from __future__ import annotations

"""Unified WfGg LAB V33 runtime for Android.

Goals:
- one entrypoint only;
- exact local bundle resolution and exact dependency graph from V33;
- robust Unity TextureFormat normalization when UnityPy exposes a raw int/string;
- Android-safe Texture2D decoding;
- exact Sprite backing-texture resolution by loading selected bundle + exact local dependencies together;
- exact MeshHandler 3D pipeline inherited from the V33 exact server;
- no generated substitute artwork and no name-similarity replacement.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
import gc
import importlib.util
import json
import re
import shutil
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
EXACT_PATH = ROOT / "scripts/lastwar-global-graphics-server-v33-exact.py"
CACHE = Path.home() / ".cache/wfgg-lastwar-v31"
CLOSURE_CACHE = CACHE / "closure-v33-unified"
CLOSURE_CACHE.mkdir(parents=True, exist_ok=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exact = _load("wfgg_v33_exact", EXACT_PATH)
core = exact.core
codec = exact.codec

UNITY_TEXTURE_FORMAT_NAMES = {
    1:"Alpha8",2:"ARGB4444",3:"RGB24",4:"RGBA32",5:"ARGB32",6:"ARGBFloat",7:"RGB565",8:"BGR24",9:"R16",
    10:"DXT1",11:"DXT3",12:"DXT5",13:"RGBA4444",14:"BGRA32",15:"RHalf",16:"RGHalf",17:"RGBAHalf",18:"RFloat",
    19:"RGFloat",20:"RGBAFloat",21:"YUY2",22:"RGB9e5Float",23:"RGBFloat",24:"BC6H",25:"BC7",26:"BC4",27:"BC5",
    28:"DXT1Crunched",29:"DXT5Crunched",30:"PVRTC_RGB2",31:"PVRTC_RGBA2",32:"PVRTC_RGB4",33:"PVRTC_RGBA4",34:"ETC_RGB4",
    35:"ATC_RGB4",36:"ATC_RGBA8",41:"EAC_R",42:"EAC_R_SIGNED",43:"EAC_RG",44:"EAC_RG_SIGNED",45:"ETC2_RGB",
    46:"ETC2_RGBA1",47:"ETC2_RGBA8",48:"ASTC_RGB_4x4",49:"ASTC_RGB_5x5",50:"ASTC_RGB_6x6",51:"ASTC_RGB_8x8",
    52:"ASTC_RGB_10x10",53:"ASTC_RGB_12x12",54:"ASTC_RGBA_4x4",55:"ASTC_RGBA_5x5",56:"ASTC_RGBA_6x6",
    57:"ASTC_RGBA_8x8",58:"ASTC_RGBA_10x10",59:"ASTC_RGBA_12x12",60:"ETC_RGB4_3DS",61:"ETC_RGBA8_3DS",62:"RG16",
    63:"R8",64:"ETC_RGB4Crunched",65:"ETC2_RGBA8Crunched",66:"ASTC_HDR_4x4",67:"ASTC_HDR_5x5",68:"ASTC_HDR_6x6",
    69:"ASTC_HDR_8x8",70:"ASTC_HDR_10x10",71:"ASTC_HDR_12x12",72:"RG32",73:"RGB48",74:"RGBA64",75:"R8_SIGNED",
    76:"RG16_SIGNED",77:"RGB24_SIGNED",78:"RGBA32_SIGNED",79:"R16_SIGNED",80:"RG32_SIGNED",81:"RGB48_SIGNED",82:"RGBA64_SIGNED",
}


def _int_texture_format(value):
    candidates = [value, getattr(value, "value", None), getattr(value, "m_Value", None)]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return int(candidate)
        except Exception:
            m = re.fullmatch(r"\s*(-?\d+)\s*", str(candidate))
            if m:
                return int(m.group(1))
    return None


def fixed_texture_format_name(tex) -> str:
    value = getattr(tex, "m_TextureFormat", None)
    name = getattr(value, "name", None)
    if name and not str(name).isdigit():
        return str(name)
    ivalue = _int_texture_format(value)
    if ivalue is not None:
        try:
            from UnityPy.enums.TextureFormat import TextureFormat
            return TextureFormat(ivalue).name
        except Exception:
            return UNITY_TEXTURE_FORMAT_NAMES.get(ivalue, str(ivalue))
    text = str(value or "UNKNOWN")
    if text.isdigit():
        return UNITY_TEXTURE_FORMAT_NAMES.get(int(text), text)
    return text


codec.texture_format_name = fixed_texture_format_name


class _Probe49:
    m_TextureFormat = 49
class _Probe50:
    m_TextureFormat = "50"
class _Wrapped:
    value = 51
class _Probe51:
    m_TextureFormat = _Wrapped()

assert fixed_texture_format_name(_Probe49()) == "ASTC_RGB_5x5"
assert fixed_texture_format_name(_Probe50()) == "ASTC_RGB_6x6"
assert fixed_texture_format_name(_Probe51()) == "ASTC_RGB_8x8"


def _sprite_texture(sprite):
    rd = getattr(sprite, "m_RD", None) or getattr(sprite, "m_RenderData", None)
    if rd is None:
        return None, ""
    for key in ("texture", "m_Texture", "alphaTexture", "m_AlphaTexture"):
        ptr = getattr(rd, key, None)
        if ptr is None:
            continue
        try:
            tex = ptr.read() if hasattr(ptr, "read") else ptr
            if tex is not None and hasattr(tex, "m_Width"):
                return tex, key
        except Exception:
            continue
    return None, ""


def _is_atlas_asset(a):
    path = str(a.get("asset_path") or "").lower()
    return path.endswith(".spriteatlas") or a.get("visual_role") == "sprite-atlas" or a.get("tech_kind") == "atlas"


def _materialize_closure(a, max_deps=18):
    """Copy selected bundle + exact local dependency bundles before UnityPy opens them.

    The normal mobile bundle cache is deliberately tiny.  Copying each proven slice to a
    per-request closure directory prevents the LRU from deleting earlier dependencies and
    lets one UnityPy Environment resolve external PPtrs by the serialized CAB names.
    """
    sid = a["stable_id"]
    base = CLOSURE_CACHE / sid
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)

    rows = [a] + exact.dependency_rows(a, max_bundles=max_deps, max_depth=2)
    seen = set()
    paths = []
    sources = []
    for row in rows:
        try:
            bid = int(row.get("bundle_id"))
        except Exception:
            continue
        if bid in seen:
            continue
        seen.add(bid)
        try:
            src, source = core.v31.materialize_bundle(row)
        except Exception as exc:
            sources.append({"bundleId":bid,"ok":False,"error":str(exc)[:300]})
            continue
        dst = base / f"bundle-{bid}.bundle"
        try:
            shutil.copy2(src, dst)
        except Exception as exc:
            sources.append({"bundleId":bid,"ok":False,"error":"copy:"+str(exc)[:300]})
            continue
        paths.append(dst)
        sources.append({"bundleId":bid,"ok":True,"source":source,"dependencyDepth":row.get("_dependency_depth",0)})
    return paths, sources


def _object_name(obj):
    try:
        n = obj.peek_name()
        if n:
            return str(n)
    except Exception:
        pass
    try:
        return str(getattr(obj.read(), "m_Name", "") or "")
    except Exception:
        return ""


def render_asset_unified(a):
    sid = a["stable_id"]
    cached = core.v31.RENDER_CACHE / (sid + "-unified.png")
    if cached.is_file() and cached.stat().st_size > 64:
        return cached, {"source":"render-cache-v33-unified","stableId":sid}

    try:
        import UnityPy
    except Exception as exc:
        raise RuntimeError("RUNTIME_UNITYPY_MISSING: " + str(exc)) from exc

    paths, closure_sources = _materialize_closure(a)
    if not paths:
        raise RuntimeError("RUNTIME_NO_LOCAL_BUNDLE: aucun bundle exact de la fermeture locale n'est matérialisable")

    env = None
    terms = core.target_terms(a)
    errors = []
    try:
        env = UnityPy.load(*[str(p) for p in paths])
        sprites = []
        textures = []
        object_counts = {}
        for obj in env.objects:
            typ = getattr(obj.type, "name", str(obj.type))
            object_counts[typ] = object_counts.get(typ, 0) + 1
            if typ not in {"Sprite", "Texture2D"}:
                continue
            name = _object_name(obj)
            score = core.score_name(name, terms)
            if typ == "Sprite":
                sprites.append((score + 8, name, obj))
            else:
                textures.append((score, name, obj))
        sprites.sort(key=lambda x:(x[0],len(x[1])), reverse=True)
        textures.sort(key=lambda x:(x[0],len(x[1])), reverse=True)

        # First choice: exact Sprite PPtr now that exact dependency bundles coexist.
        for score, name, obj in sprites[:80]:
            try:
                sprite = obj.read()
                tex, pointer = _sprite_texture(sprite)
                if tex is None:
                    raise ValueError("backing Texture2D unresolved in exact closure")
                img, fmt = codec.decode_texture2d(tex)
                img = exact.crop_sprite(img, sprite)
                cached.parent.mkdir(parents=True, exist_ok=True)
                img.save(cached, "PNG")
                return cached, {
                    "mode":"exact-closure-sprite","stableId":sid,"objectName":name,"objectType":"Sprite",
                    "matchScore":score,"textureFormat":fmt,"spritePointer":pointer,
                    "closureBundles":len(paths),"closureSources":closure_sources[:12],"objects":object_counts,
                }
            except Exception as exc:
                errors.append("Sprite:"+name+":"+type(exc).__name__+":"+str(exc))

        # Texture2D is an exact render for Texture/Atlas assets.  For a .spriteatlas this
        # correctly shows the real atlas image rather than inventing a crop.
        if _is_atlas_asset(a) or str(a.get("tech_kind") or "").lower() in {"texture2d","texture","atlas"}:
            for score, name, obj in textures[:80]:
                try:
                    tex = obj.read()
                    img, fmt = codec.decode_texture2d(tex)
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    img.save(cached, "PNG")
                    return cached, {
                        "mode":"exact-closure-texture","stableId":sid,"objectName":name,"objectType":"Texture2D",
                        "matchScore":score,"textureFormat":fmt,"closureBundles":len(paths),
                        "closureSources":closure_sources[:12],"objects":object_counts,
                    }
                except Exception as exc:
                    errors.append("Texture2D:"+name+":"+type(exc).__name__+":"+str(exc))

        # For a Sprite asset, do NOT substitute an arbitrary dependency texture.
        summary = " | ".join(errors[:8]) or "aucun Sprite/Texture2D correspondant"
        raise RuntimeError(
            "RUNTIME_EXACT_RASTER_UNRESOLVED: fermeture="+str(len(paths))+" bundles; "+summary
        )
    finally:
        try:
            del env
        except Exception:
            pass
        gc.collect()


core.v31.render_asset = render_asset_unified
# 3D stays on the exact dependency + Android MeshHandler pipeline installed by exact.py.


if __name__ == "__main__":
    con = core.dbcon()
    dep_edges = con.execute("SELECT count(*) FROM bundle_dependencies_v33").fetchone()[0]
    con.close()
    url = f"http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html"
    print("=== WFGG LAST WAR GLOBAL GRAPHICS V33 — UNIFIED EXACT ANDROID ===", flush=True)
    print("V33_TEXTURE_FORMAT 49=ASTC_RGB_5x5 50=ASTC_RGB_6x6 51=ASTC_RGB_8x8", flush=True)
    print("V33_SPRITE_RESOLVER selected+exact-dependencies multi-file-environment=ON", flush=True)
    print("V33_EXACT_DEP_EDGES", dep_edges, flush=True)
    print(url, flush=True)
    ThreadingHTTPServer(("127.0.0.1", core.PORT), core.Handler).serve_forever()
