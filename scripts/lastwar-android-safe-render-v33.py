#!/usr/bin/env python3
"""Android-safe Last War render helpers for WfGg LAB V33.

No generated geometry and no similarity substitute:
- Texture2D -> raw image bytes -> texture2ddecoder/Pillow
- Mesh -> UnityPy MeshHandler -> manual OBJ
- Sprite -> backing Texture2D when its exact PPtr resolves

This deliberately avoids UnityPy's high-level .image/.export wrappers on Android.
"""
from __future__ import annotations

from pathlib import Path
import json, re


def _typename(obj) -> str:
    try:
        return getattr(obj.type, "name", str(obj.type))
    except Exception:
        return type(obj).__name__


def _obj_name(obj, data=None) -> str:
    try:
        n = obj.peek_name()
        if n:
            return str(n)
    except Exception:
        pass
    try:
        if data is None:
            data = obj.read()
        return str(getattr(data, "m_Name", "") or "")
    except Exception:
        return ""


def _fmt_name(tex) -> str:
    f = getattr(tex, "m_TextureFormat", None)
    return getattr(f, "name", str(f))


def _decoder_call(module, names, *args):
    for name in names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn(*args)
    raise AttributeError("texture2ddecoder function absent: " + "/".join(names))


def _rgba_from_decoder(raw: bytes, width: int, height: int, fmt: str):
    from PIL import Image
    import texture2ddecoder as t2d

    f = fmt.upper()
    decoded = None
    if f.startswith("ASTC_"):
        m = re.search(r"_(\d+)X(\d+)$", f)
        if not m:
            raise ValueError("ASTC block size absent: " + fmt)
        bw, bh = map(int, m.groups())
        decoded = _decoder_call(t2d, ("decode_astc",), raw, width, height, bw, bh)
    elif f in {"ETC_RGB4", "ETC_RGB4_3DS"}:
        decoded = _decoder_call(t2d, ("decode_etc1",), raw, width, height)
    elif f == "ETC2_RGB":
        decoded = _decoder_call(t2d, ("decode_etc2",), raw, width, height)
    elif f == "ETC2_RGBA1":
        decoded = _decoder_call(t2d, ("decode_etc2a1",), raw, width, height)
    elif f == "ETC2_RGBA8":
        decoded = _decoder_call(t2d, ("decode_etc2a8", "decode_etc2_rgba8"), raw, width, height)
    elif f in {"DXT1", "DXT1CRUNCHED"}:
        decoded = _decoder_call(t2d, ("decode_bc1",), raw, width, height)
    elif f in {"DXT5", "DXT5CRUNCHED"}:
        decoded = _decoder_call(t2d, ("decode_bc3",), raw, width, height)
    elif f == "BC4":
        decoded = _decoder_call(t2d, ("decode_bc4",), raw, width, height)
    elif f == "BC5":
        decoded = _decoder_call(t2d, ("decode_bc5",), raw, width, height)
    elif f == "BC6H":
        decoded = _decoder_call(t2d, ("decode_bc6",), raw, width, height)
    elif f == "BC7":
        decoded = _decoder_call(t2d, ("decode_bc7",), raw, width, height)
    elif f == "ATC_RGB4":
        decoded = _decoder_call(t2d, ("decode_atc_rgb4",), raw, width, height)
    elif f == "ATC_RGBA8":
        decoded = _decoder_call(t2d, ("decode_atc_rgba8",), raw, width, height)

    if decoded is not None:
        # texture2ddecoder's four-channel decoders expose BGRA bytes.
        return Image.frombytes("RGBA", (width, height), decoded, "raw", "BGRA")

    # Common uncompressed Unity formats.
    if f == "RGBA32":
        return Image.frombytes("RGBA", (width, height), raw[: width * height * 4], "raw", "RGBA")
    if f == "ARGB32":
        return Image.frombytes("RGBA", (width, height), raw[: width * height * 4], "raw", "ARGB")
    if f == "BGRA32":
        return Image.frombytes("RGBA", (width, height), raw[: width * height * 4], "raw", "BGRA")
    if f == "RGB24":
        return Image.frombytes("RGB", (width, height), raw[: width * height * 3], "raw", "RGB").convert("RGBA")
    if f == "ALPHA8":
        alpha = Image.frombytes("L", (width, height), raw[: width * height], "raw", "L")
        rgba = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        rgba.putalpha(alpha)
        return rgba
    if f == "R8":
        r = Image.frombytes("L", (width, height), raw[: width * height], "raw", "L")
        return Image.merge("RGBA", (r, r, r, Image.new("L", (width, height), 255)))

    raise NotImplementedError("direct decoder unsupported texture format: " + fmt)


def decode_texture2d(tex):
    """Return (PIL image, metadata) without Texture2D.image."""
    width = int(getattr(tex, "m_Width", 0) or 0)
    height = int(getattr(tex, "m_Height", 0) or 0)
    fmt = _fmt_name(tex)
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid texture size {width}x{height}")

    getter = getattr(tex, "get_image_data", None)
    if callable(getter):
        raw = getter()
    else:
        raw = getattr(tex, "image_data", None) or getattr(tex, "m_ImageData", None)
    if not raw:
        raise ValueError("Texture2D image bytes absent/unresolvable")
    raw = bytes(raw)

    try:
        img = _rgba_from_decoder(raw, width, height, fmt)
        mode = "texture2ddecoder-direct"
    except Exception as direct_error:
        # Explicit converter fallback remains below the high-level .image wrapper.
        try:
            from UnityPy.export.Texture2DConverter import parse_image_data
            reader = getattr(tex, "object_reader", None)
            platform = getattr(reader, "platform", 0)
            version = getattr(reader, "version", (0, 0, 0, 0))
            blob = getattr(tex, "m_PlatformBlob", None)
            img = parse_image_data(raw, width, height, getattr(tex, "m_TextureFormat"), version, platform, blob, False)
            mode = "unitypy-parse-image-data"
        except Exception as fallback_error:
            raise RuntimeError(f"direct={direct_error}; converter={fallback_error}") from fallback_error

    try:
        from PIL import Image
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    except Exception:
        pass
    return img, {"mode": mode, "width": width, "height": height, "format": fmt, "bytes": len(raw)}


def sprite_backing_texture(sprite):
    rd = getattr(sprite, "m_RD", None) or getattr(sprite, "m_RenderData", None)
    if rd is None:
        return None, ""
    for key in ("texture", "alphaTexture", "m_Texture", "m_AlphaTexture"):
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


def crop_sprite(img, sprite):
    rect = getattr(sprite, "m_Rect", None)
    if rect is None:
        return img, False
    try:
        x = int(round(float(rect.x)))
        y = int(round(float(rect.y)))
        w = int(round(float(rect.width)))
        h = int(round(float(rect.height)))
        if w <= 0 or h <= 0:
            return img, False
        left = max(0, x)
        top = max(0, img.height - (y + h))
        right = min(img.width, left + w)
        bottom = min(img.height, top + h)
        if right > left and bottom > top:
            return img.crop((left, top, right, bottom)), True
    except Exception:
        pass
    return img, False


def write_mesh_obj(mesh, output: Path):
    """Direct MeshHandler path; never Mesh.export()/Renderer.export()."""
    from UnityPy.helpers.MeshHelper import MeshHandler

    handler = MeshHandler(mesh)
    handler.process()
    verts = handler.m_Vertices or []
    if not verts:
        raise ValueError("MeshHandler produced no vertices")
    uvs = handler.m_UV0 or []
    norms = handler.m_Normals or []
    name = str(getattr(mesh, "m_Name", "") or output.stem)

    lines = [f"g {name}\n"]
    lines += ["v {:.9G} {:.9G} {:.9G}\n".format(-p[0], p[1], p[2]).replace("nan", "0") for p in verts]
    lines += ["vt {:.9G} {:.9G}\n".format(uv[0], uv[1]).replace("nan", "0") for uv in uvs]
    lines += ["vn {:.9G} {:.9G} {:.9G}\n".format(-n[0], n[1], n[2]).replace("nan", "0") for n in norms]

    tri_count = 0
    for sub_i, triangles in enumerate(handler.get_triangles()):
        lines.append(f"g {name}_{sub_i}\n")
        for a, b, c in triangles:
            c1, b1, a1 = c + 1, b + 1, a + 1
            if uvs and norms:
                lines.append(f"f {c1}/{c1}/{c1} {b1}/{b1}/{b1} {a1}/{a1}/{a1}\n")
            elif uvs:
                lines.append(f"f {c1}/{c1} {b1}/{b1} {a1}/{a1}\n")
            elif norms:
                lines.append(f"f {c1}//{c1} {b1}//{b1} {a1}//{a1}\n")
            else:
                lines.append(f"f {c1} {b1} {a1}\n")
            tri_count += 1
    if tri_count == 0:
        raise ValueError("MeshHandler produced no triangles")
    output.write_text("".join(lines), encoding="utf-8", newline="")
    return {"mode": "android-safe-mesh-handler", "vertices": len(verts), "triangles": tri_count, "uv": len(uvs), "normals": len(norms)}


def scan_bundle(UnityPy, bundle: Path, outdir: Path, bundle_index: int, terms, score_name, safe_name,
                max_meshes=48, max_textures=96):
    """Decode real objects from one bundle and immediately release the environment."""
    env = None
    result = {"loaded": False, "objects": {}, "meshes": [], "textures": [], "errors": []}
    try:
        env = UnityPy.load(str(bundle))
        result["loaded"] = True
        candidates = []
        for obj in env.objects:
            typ = _typename(obj)
            result["objects"][typ] = result["objects"].get(typ, 0) + 1
            if typ not in {"Mesh", "Texture2D", "Sprite"}:
                continue
            name = _obj_name(obj)
            candidates.append((score_name(name, terms), name, typ, obj))
        candidates.sort(key=lambda x: (x[0], len(x[1])), reverse=True)

        mesh_i = tex_i = 0
        texdir = outdir / "textures"
        texdir.mkdir(parents=True, exist_ok=True)
        for score, name, typ, obj in candidates:
            if typ == "Mesh" and mesh_i < max_meshes:
                try:
                    data = obj.read()
                    fp = outdir / f"mesh-b{bundle_index}-{mesh_i}-{safe_name(name or 'mesh')}.obj"
                    meta = write_mesh_obj(data, fp)
                    meta.update({"type": "Mesh", "name": name, "score": score, "sourceBundle": bundle.name, "path": fp.name})
                    result["meshes"].append(meta)
                    mesh_i += 1
                except Exception as exc:
                    result["errors"].append(f"Mesh:{name}:{type(exc).__name__}:{exc}")
            elif typ in {"Texture2D", "Sprite"} and tex_i < max_textures:
                try:
                    data = obj.read()
                    if typ == "Sprite":
                        tex, pointer = sprite_backing_texture(data)
                        if tex is None:
                            raise ValueError("Sprite backing Texture2D unresolved")
                        img, meta = decode_texture2d(tex)
                        img, cropped = crop_sprite(img, data)
                        meta["spritePointer"] = pointer
                        meta["spriteCrop"] = cropped
                    else:
                        img, meta = decode_texture2d(data)
                    fp = texdir / f"b{bundle_index}-{tex_i}-{safe_name(name or typ)}.png"
                    img.save(fp, "PNG")
                    meta.update({"type": typ, "name": name, "score": score, "sourceBundle": bundle.name,
                                 "path": fp.relative_to(outdir).as_posix()})
                    result["textures"].append(meta)
                    tex_i += 1
                except Exception as exc:
                    result["errors"].append(f"{typ}:{name}:{type(exc).__name__}:{exc}")
        return result
    except Exception as exc:
        result["errors"].append(f"load:{bundle.name}:{type(exc).__name__}:{exc}")
        return result
    finally:
        try:
            del env
        except Exception:
            pass
        try:
            import gc
            gc.collect()
        except Exception:
            pass


def best_raster_from_bundle(UnityPy, bundle: Path, out_png: Path, terms, score_name):
    """Pick the best real Sprite/Texture2D in a bundle via the direct decoder."""
    env = None
    diag = {"objects": {}, "errors": []}
    try:
        env = UnityPy.load(str(bundle))
        candidates = []
        for obj in env.objects:
            typ = _typename(obj)
            diag["objects"][typ] = diag["objects"].get(typ, 0) + 1
            if typ not in {"Sprite", "Texture2D"}:
                continue
            name = _obj_name(obj)
            score = score_name(name, terms)
            candidates.append((score + (2 if typ == "Sprite" else 0), name, typ, obj))
        candidates.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        for score, name, typ, obj in candidates[:64]:
            try:
                data = obj.read()
                if typ == "Sprite":
                    tex, pointer = sprite_backing_texture(data)
                    if tex is None:
                        raise ValueError("Sprite backing Texture2D unresolved")
                    img, meta = decode_texture2d(tex)
                    img, cropped = crop_sprite(img, data)
                    meta["spritePointer"] = pointer
                    meta["spriteCrop"] = cropped
                else:
                    img, meta = decode_texture2d(data)
                out_png.parent.mkdir(parents=True, exist_ok=True)
                img.save(out_png, "PNG")
                meta.update({"type": typ, "objectName": name, "score": score, "sourceBundle": bundle.name,
                             "diagnostics": diag})
                return out_png, meta
            except Exception as exc:
                diag["errors"].append(f"{typ}:{name}:{type(exc).__name__}:{exc}")
        raise RuntimeError("direct decoder: no decodable Sprite/Texture2D; " + json.dumps(diag, ensure_ascii=False)[:3000])
    finally:
        try:
            del env
        except Exception:
            pass
        try:
            import gc
            gc.collect()
        except Exception:
            pass
