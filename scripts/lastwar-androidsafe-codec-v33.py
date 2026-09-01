#!/usr/bin/env python3
from __future__ import annotations

"""Android-safe Last War render codec for WfGg LAB V33.

Avoid UnityPy high-level Texture2D.image, Mesh.export and Renderer.export paths
on Android. Use exact bundle slices, direct Texture2D payload decoding and
MeshHandler + a small OBJ writer. 3D assembly is expanded through the exact
bundle dependency IDs already present in the canonical graphics TSV.
"""

from pathlib import Path
from collections import defaultdict, deque
import csv
import gc
import json
import re

_DEP_INDEX = None
_INSTALLED = False


def _safe_name(value):
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or ""))
    return s[:110] or "asset"


def _object_name(obj):
    try:
        name = obj.peek_name()
        if name:
            return str(name)
    except Exception:
        pass
    try:
        data = obj.read()
        return str(getattr(data, "m_Name", "") or getattr(data, "name", "") or "")
    except Exception:
        return ""


def _score_name(name, terms):
    n = str(name or "").lower()
    score = 0
    nw = set(re.findall(r"[a-z0-9]+", n))
    for term in terms:
        t = str(term or "").lower()
        if not t:
            continue
        if n == t:
            score = max(score, 100)
        elif n and (n in t or t in n):
            score = max(score, 75)
        else:
            tw = set(re.findall(r"[a-z0-9]+", t))
            score = max(score, 10 * len(nw & tw))
    return score


def _read_texture_payload(tex):
    raw = getattr(tex, "image_data", None)
    if raw:
        return bytes(raw)
    stream = getattr(tex, "m_StreamData", None)
    if stream is not None and getattr(stream, "path", ""):
        reader = getattr(tex, "object_reader", None)
        assets_file = getattr(reader, "assets_file", None)
        if assets_file is None:
            raise ValueError("Texture2D stream externe sans assets_file")
        from UnityPy.helpers.ResourceReader import get_resource_data
        return bytes(get_resource_data(
            stream.path, assets_file,
            int(getattr(stream, "offset", 0) or 0),
            int(getattr(stream, "size", 0) or 0),
        ))
    getter = getattr(tex, "get_image_data", None)
    if callable(getter):
        return bytes(getter())
    raise ValueError("Texture2D sans payload image")


def _texture_format_name(tex):
    fmt = getattr(tex, "m_TextureFormat", "")
    name = getattr(fmt, "name", "")
    return str(name or str(fmt).rsplit(".", 1)[-1])


def _bgra_image(decoded, width, height):
    from PIL import Image
    return Image.frombytes("RGBA", (width, height), bytes(decoded), "raw", "BGRA")


def direct_texture_image(tex, flip=True):
    """Decode Texture2D without Texture2D.image/Texture2DConverter."""
    from PIL import Image
    raw = _read_texture_payload(tex)
    width = int(getattr(tex, "m_Width", 0) or 0)
    height = int(getattr(tex, "m_Height", 0) or 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"Texture2D dimensions invalides: {width}x{height}")
    fmt = _texture_format_name(tex)
    upper = fmt.upper()

    if upper == "RGBA32":
        img = Image.frombytes("RGBA", (width, height), raw, "raw", "RGBA")
    elif upper == "BGRA32":
        img = Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
    elif upper == "ARGB32":
        img = Image.frombytes("RGBA", (width, height), raw, "raw", "ARGB")
    elif upper in {"RGB24", "BGR24"}:
        img = Image.frombytes("RGB", (width, height), raw, "raw", "BGR" if upper == "BGR24" else "RGB").convert("RGBA")
    elif upper in {"ALPHA8", "R8"}:
        img = Image.frombytes("L", (width, height), raw, "raw", "L").convert("RGBA")
    else:
        try:
            import texture2ddecoder
        except Exception as exc:
            raise RuntimeError("texture2ddecoder indisponible dans Termux") from exc
        decoded = None
        if upper.startswith("ASTC"):
            m = re.search(r"(\d+)X(\d+)$", upper)
            if not m:
                raise ValueError(f"Bloc ASTC non reconnu: {fmt}")
            decoded = texture2ddecoder.decode_astc(raw, width, height, int(m.group(1)), int(m.group(2)))
        elif upper in {"ETC_RGB4", "ETC_RGB4_3DS"}:
            decoded = texture2ddecoder.decode_etc1(raw, width, height)
        elif upper == "ETC2_RGB":
            decoded = texture2ddecoder.decode_etc2(raw, width, height)
        elif upper in {"ETC2_RGBA8", "ETC2_RGBA8CRUNCHED"}:
            payload = raw
            if "CRUNCHED" in upper:
                unpack = getattr(texture2ddecoder, "unpack_unity_crunch", None)
                if not unpack:
                    raise ValueError("Unity Crunch decoder unavailable")
                payload = unpack(payload)
            decoded = texture2ddecoder.decode_etc2a8(payload, width, height)
        elif upper == "ETC2_RGBA1":
            decoded = texture2ddecoder.decode_etc2a1(raw, width, height)
        elif upper in {"DXT1", "DXT1CRUNCHED"}:
            payload = raw
            if "CRUNCHED" in upper:
                unpack = getattr(texture2ddecoder, "unpack_unity_crunch", None)
                if not unpack:
                    raise ValueError("Unity Crunch decoder unavailable")
                payload = unpack(payload)
            decoded = texture2ddecoder.decode_bc1(payload, width, height)
        elif upper in {"DXT5", "DXT5CRUNCHED"}:
            payload = raw
            if "CRUNCHED" in upper:
                unpack = getattr(texture2ddecoder, "unpack_unity_crunch", None)
                if not unpack:
                    raise ValueError("Unity Crunch decoder unavailable")
                payload = unpack(payload)
            decoded = texture2ddecoder.decode_bc3(payload, width, height)
        elif upper == "BC4":
            decoded = texture2ddecoder.decode_bc4(raw, width, height)
        elif upper == "BC5":
            decoded = texture2ddecoder.decode_bc5(raw, width, height)
        elif upper == "BC7":
            decoded = texture2ddecoder.decode_bc7(raw, width, height)
        else:
            raise NotImplementedError(f"Format Texture2D Android-safe non pris en charge: {fmt}")
        img = _bgra_image(decoded, width, height)

    if flip:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img, fmt


def _pptr_read(ptr):
    if ptr is None:
        return None
    for method in ("read", "deref_parse_as_object"):
        fn = getattr(ptr, method, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    obj = getattr(ptr, "object", None)
    if obj is not None:
        try:
            return obj.read()
        except Exception:
            return obj
    return None


def direct_sprite_image(sprite):
    """Best-effort exact Sprite crop from its real Texture2D payload."""
    from PIL import Image
    rd = getattr(sprite, "m_RD", None)
    if rd is None:
        raise ValueError("Sprite sans m_RD")
    tex_ptr = getattr(rd, "texture", None) or getattr(rd, "m_Texture", None)
    tex = _pptr_read(tex_ptr)
    if tex is None:
        raise ValueError("Sprite sans Texture2D directe")
    img, fmt = direct_texture_image(tex, flip=False)

    alpha_ptr = getattr(rd, "alphaTexture", None) or getattr(rd, "m_AlphaTexture", None)
    alpha = _pptr_read(alpha_ptr)
    if alpha is not None:
        try:
            aimg, _ = direct_texture_image(alpha, flip=False)
            img = Image.merge("RGBA", (*img.convert("RGBA").split()[:3], aimg.convert("RGBA").split()[0]))
        except Exception:
            pass

    rect = getattr(rd, "textureRect", None) or getattr(rd, "m_TextureRect", None)
    if rect is not None:
        x = int(round(float(getattr(rect, "x", 0) or 0)))
        y = int(round(float(getattr(rect, "y", 0) or 0)))
        w = int(round(float(getattr(rect, "width", 0) or 0)))
        h = int(round(float(getattr(rect, "height", 0) or 0)))
        if w > 0 and h > 0:
            img = img.crop((x, y, x + w, y + h))

    settings = int(getattr(rd, "settingsRaw", 0) or getattr(rd, "m_SettingsRaw", 0) or 0)
    if settings & 1:
        rotation = (settings >> 2) & 0xF
        if rotation == 1:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif rotation == 2:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif rotation == 3:
            img = img.transpose(Image.Transpose.ROTATE_180)
        elif rotation == 4:
            img = img.transpose(Image.Transpose.ROTATE_270)
    return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM), fmt


def _mesh_triangles(handler, mesh):
    indices = list(getattr(handler, "m_IndexBuffer", None) or [])
    if not indices:
        return []
    index_size = 2 if bool(getattr(handler, "m_Use16BitIndices", True)) else 4
    submeshes = list(getattr(mesh, "m_SubMeshes", None) or [])
    groups = []
    if submeshes:
        for sm in submeshes:
            topology = int(getattr(sm, "topology", getattr(sm, "m_Topology", 0)) or 0)
            if topology != 0:
                continue
            first_byte = int(getattr(sm, "firstByte", getattr(sm, "m_FirstByte", 0)) or 0)
            index_count = int(getattr(sm, "indexCount", getattr(sm, "m_IndexCount", 0)) or 0)
            base_vertex = int(getattr(sm, "baseVertex", getattr(sm, "m_BaseVertex", 0)) or 0)
            start = max(0, first_byte // index_size)
            local = indices[start:min(len(indices), start + index_count)]
            tris = [(int(local[i]) + base_vertex, int(local[i+1]) + base_vertex, int(local[i+2]) + base_vertex)
                    for i in range(0, len(local) - 2, 3)]
            if tris:
                groups.append(tris)
    if groups:
        return groups
    return [[(int(indices[i]), int(indices[i+1]), int(indices[i+2])) for i in range(0, len(indices) - 2, 3)]]


def write_mesh_obj(mesh, path):
    """Write real Unity mesh geometry using MeshHandler, without Mesh.export."""
    from UnityPy.helpers.MeshHelper import MeshHandler
    handler = MeshHandler(mesh)
    handler.process()
    verts = list(getattr(handler, "m_Vertices", None) or [])
    if not verts:
        raise ValueError("Mesh sans vertices")
    uvs = list(getattr(handler, "m_UV0", None) or [])
    normals = list(getattr(handler, "m_Normals", None) or [])
    groups = _mesh_triangles(handler, mesh)
    if not groups or not any(groups):
        raise ValueError("Mesh sans triangles")
    has_uv = len(uvs) >= len(verts)
    has_n = len(normals) >= len(verts)
    lines = ["# WfGg Android-safe exact Unity Mesh\n"]
    for v in verts:
        lines.append(f"v {float(v[0]):.9g} {float(v[1]):.9g} {float(v[2]):.9g}\n")
    if has_uv:
        for uv in uvs[:len(verts)]:
            lines.append(f"vt {float(uv[0]):.9g} {float(uv[1]):.9g}\n")
    if has_n:
        for n in normals[:len(verts)]:
            lines.append(f"vn {float(n[0]):.9g} {float(n[1]):.9g} {float(n[2]):.9g}\n")

    def face_index(idx):
        vi = idx + 1
        if vi <= 0 or vi > len(verts):
            return None
        if has_uv and has_n:
            return f"{vi}/{vi}/{vi}"
        if has_uv:
            return f"{vi}/{vi}"
        if has_n:
            return f"{vi}//{vi}"
        return str(vi)

    written = 0
    for gi, tris in enumerate(groups):
        lines.append(f"g submesh_{gi}\n")
        for tri in tris:
            face = [face_index(x) for x in tri]
            if any(x is None for x in face):
                continue
            lines.append("f " + " ".join(face) + "\n")
            written += 1
    if not written:
        raise ValueError("Mesh triangles hors limites")
    Path(path).write_text("".join(lines), encoding="utf-8", newline="")
    return {"vertices": len(verts), "triangles": written, "uv": has_uv, "normals": has_n}


def _load_dependency_index(root):
    global _DEP_INDEX
    if _DEP_INDEX is not None:
        return _DEP_INDEX
    path = Path(root) / "frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv"
    deps = defaultdict(set)
    if path.is_file():
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    bid = int(str(row.get("bundleId", "")).strip())
                except Exception:
                    continue
                raw = str(row.get("dependencies", "") or "")
                for token in re.findall(r"(?<!\d)\d{1,7}(?!\d)", raw):
                    dep = int(token)
                    if dep >= 0 and dep != bid:
                        deps[bid].add(dep)
    _DEP_INDEX = {k: tuple(sorted(v)) for k, v in deps.items()}
    print("V33_ANDROID_DEP_INDEX", f"bundles={len(_DEP_INDEX)}", f"edges={sum(len(v) for v in _DEP_INDEX.values())}", flush=True)
    return _DEP_INDEX


def _dependency_closure(root, bundle_id, depth=2, limit=48):
    idx = _load_dependency_index(root)
    try:
        start = int(bundle_id)
    except Exception:
        return []
    out, seen = [], {start}
    queue = deque([(start, 0)])
    while queue and len(out) < limit:
        bid, d = queue.popleft()
        if d >= depth:
            continue
        for dep in idx.get(bid, ()):
            if dep in seen:
                continue
            seen.add(dep)
            out.append(dep)
            queue.append((dep, d + 1))
            if len(out) >= limit:
                break
    return out


def _dependency_representatives(core, root, asset, base_items):
    deps = _dependency_closure(root, asset.get("bundle_id"), depth=2, limit=max(48, core.MAX_MODEL_BUNDLES * 3))
    if not deps:
        return base_items
    con = core.dbcon()
    cols = {r[1] for r in con.execute("PRAGMA table_info(assets)")}
    has_avail = "render_availability" in cols
    out = list(base_items)
    seen_sids = {x.get("stable_id") for x in out}
    seen_bids = set()
    for x in out:
        try:
            seen_bids.add(int(x.get("bundle_id")))
        except Exception:
            pass
    placeholders = ",".join("?" for _ in deps)
    avail_order = "CASE render_availability WHEN 'local-exact' THEN 0 WHEN 'local-resolved' THEN 1 ELSE 2 END," if has_avail else ""
    sql = f"""SELECT * FROM assets WHERE bundle_id IN ({placeholders})
      ORDER BY {avail_order}
        CASE model_role WHEN 'geometry' THEN 0 WHEN 'geometry-candidate' THEN 1 WHEN 'prefab' THEN 2
          WHEN 'material' THEN 3 WHEN 'texture' THEN 4 WHEN 'shader' THEN 5 WHEN 'animation' THEN 6 ELSE 7 END,
        confidence DESC,row_no"""
    rows = con.execute(sql, deps).fetchall()
    con.close()
    for row in rows:
        d = core.rowdict(row)
        try:
            bid = int(d.get("bundle_id"))
        except Exception:
            continue
        if bid in seen_bids or d.get("stable_id") in seen_sids:
            continue
        if has_avail and d.get("render_availability") == "global-index-only":
            continue
        seen_bids.add(bid)
        seen_sids.add(d.get("stable_id"))
        d["_wfgg_dependency_of"] = asset.get("bundle_id")
        out.append(d)
        if len(seen_bids) >= core.MAX_MODEL_BUNDLES:
            break
    return out


def _export_bundle_objects(core, UnityPy, bundle, outdir, bi, terms, exported, errors):
    env = None
    try:
        env = UnityPy.load(str(bundle))
        meshes, textures, sprites = [], [], []
        seen_types = defaultdict(int)
        for obj in env.objects:
            typ = getattr(obj.type, "name", str(obj.type))
            seen_types[typ] += 1
            if typ not in {"Mesh", "Texture2D", "Sprite"}:
                continue
            name = _object_name(obj)
            rec = (_score_name(name, terms), name, typ, obj)
            if typ == "Mesh":
                meshes.append(rec)
            elif typ == "Sprite":
                sprites.append(rec)
            else:
                textures.append(rec)
        meshes.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        sprites.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        textures.sort(key=lambda x: (x[0], len(x[1])), reverse=True)

        for oi, (score, name, typ, obj) in enumerate(meshes[:core.MAX_MESHES]):
            try:
                data = obj.read()
                fp = outdir / f"mesh-b{bi}-{oi}-{_safe_name(name or 'mesh')}.obj"
                stats = write_mesh_obj(data, fp)
                exported.append({"type":"Mesh","name":name,"score":score,"sourceBundle":bundle.name,
                                 "mode":"android-safe-meshhandler-obj", **stats})
            except Exception as exc:
                errors.append(f"Mesh:{name}: {type(exc).__name__}:{exc}")

        texdir = outdir / "textures"
        texdir.mkdir(exist_ok=True)
        for oi, (score, name, typ, obj) in enumerate(textures[:core.MAX_TEXTURES]):
            try:
                data = obj.read()
                image, fmt = direct_texture_image(data)
                fp = texdir / f"b{bi}-{oi}-{_safe_name(name or typ)}.png"
                image.save(fp)
                exported.append({"type":"Texture2D","name":name,"score":score,"sourceBundle":bundle.name,
                                 "mode":"android-safe-direct-texture","format":fmt,"size":[image.width,image.height]})
            except Exception as exc:
                errors.append(f"Texture2D:{name}: {type(exc).__name__}:{exc}")

        sprdir = outdir / "sprites"
        sprdir.mkdir(exist_ok=True)
        for oi, (score, name, typ, obj) in enumerate(sprites[:min(core.MAX_TEXTURES, 32)]):
            try:
                data = obj.read()
                image, fmt = direct_sprite_image(data)
                fp = sprdir / f"b{bi}-{oi}-{_safe_name(name or typ)}.png"
                image.save(fp)
                exported.append({"type":"Sprite","name":name,"score":score,"sourceBundle":bundle.name,
                                 "mode":"android-safe-direct-sprite","format":fmt,"size":[image.width,image.height]})
            except Exception as exc:
                errors.append(f"Sprite:{name}: {type(exc).__name__}:{exc}")

        exported.append({"type":"BundleScan","name":bundle.name,"sourceBundle":bundle.name,
                         "mode":"android-safe-object-scan","objectTypes":dict(seen_types)})
        return True
    except Exception as exc:
        errors.append(f"load {bundle.name}: {type(exc).__name__}:{exc}")
        return False
    finally:
        try:
            del env
        except Exception:
            pass
        gc.collect()


def _render_asset(core, asset):
    sid = asset["stable_id"]
    cached = core.v31.RENDER_CACHE / (sid + ".png")
    if cached.is_file() and cached.stat().st_size > 32:
        core.v31.RENDER_LRU[sid] = str(cached)
        core.v31.RENDER_LRU.move_to_end(sid)
        core.v31.trim_lru(core.v31.RENDER_LRU, core.v31.MAX_RENDERS, True)
        return cached, {"source":"render-cache","decoder":"android-safe-direct"}
    bundle, source = core.v31.materialize_bundle(asset)
    try:
        import UnityPy
    except Exception as exc:
        raise RuntimeError("UnityPy indisponible dans Termux: " + str(exc)) from exc
    env = None
    terms = core.v31.target_terms(asset)
    candidates, errors = [], []
    try:
        env = UnityPy.load(str(bundle))
        for obj in env.objects:
            typ = getattr(obj.type, "name", str(obj.type))
            if typ not in {"Sprite", "Texture2D"}:
                continue
            name = _object_name(obj)
            candidates.append((_score_name(name, terms) + (5 if typ == "Sprite" else 0), name, typ, obj))
        if not candidates:
            raise RuntimeError("Aucun Sprite/Texture2D dans ce bundle exact")
        candidates.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        for score, name, typ, obj in candidates[:30]:
            try:
                data = obj.read()
                image, fmt = direct_sprite_image(data) if typ == "Sprite" else direct_texture_image(data)
                image.save(cached)
                if cached.is_file() and cached.stat().st_size > 32:
                    meta = {"source":source,"objectName":name,"objectType":typ,"matchScore":score,
                            "bundleId":asset.get("bundle_id"),"decoder":"android-safe-direct","textureFormat":fmt}
                    core.v31.RENDER_LRU[sid] = str(cached)
                    core.v31.RENDER_LRU.move_to_end(sid)
                    core.v31.trim_lru(core.v31.RENDER_LRU, core.v31.MAX_RENDERS, True)
                    return cached, meta
            except Exception as exc:
                errors.append(f"{typ}:{name}:{type(exc).__name__}:{exc}")
        detail = " | ".join(errors[:6])
        raise RuntimeError("Objets raster trouvés mais décodage Android-safe impossible" + (": " + detail if detail else ""))
    finally:
        try:
            del env
        except Exception:
            pass
        gc.collect()


def install(core, root):
    """Install Android-safe render hooks into the already-loaded V33 server."""
    global _INSTALLED
    if _INSTALLED:
        return
    root = Path(root)
    original_assembly = core.assembly_assets
    original_build_model = core.build_model
    core.MAX_MODEL_BUNDLES = max(int(getattr(core, "MAX_MODEL_BUNDLES", 12)), 24)

    def assembly_with_dependencies(asset):
        return _dependency_representatives(core, root, asset, original_assembly(asset))

    def export_androidsafe(UnityPy, bundle, outdir, bi, terms, exported, errors):
        return _export_bundle_objects(core, UnityPy, bundle, outdir, bi, terms, exported, errors)

    def render_androidsafe(asset):
        return _render_asset(core, asset)

    core.assembly_assets = assembly_with_dependencies
    core.export_bundle_objects = export_androidsafe
    core.v31.render_asset = render_androidsafe

    def build_model_androidsafe(asset):
        sid = asset["stable_id"]
        manifest = core.MODEL_CACHE / sid / "manifest.json"
        if manifest.is_file():
            try:
                old = json.loads(manifest.read_text("utf-8"))
                if old.get("decoderMode") != "android-safe-direct":
                    manifest.unlink(missing_ok=True)
            except Exception:
                manifest.unlink(missing_ok=True)
        model = original_build_model(asset)
        model["decoderMode"] = "android-safe-direct"
        model["dependencyPolicy"] = "exact TSV bundle dependencies, depth<=2; no similarity fallback"
        try:
            manifest.write_text(json.dumps(model, ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass
        return model

    core.build_model = build_model_androidsafe
    _load_dependency_index(root)
    _INSTALLED = True
    print("V33_ANDROID_SAFE_CODEC", "installed=1", "texture=direct-payload", "mesh=MeshHandler-OBJ",
          f"maxModelBundles={core.MAX_MODEL_BUNDLES}", flush=True)
