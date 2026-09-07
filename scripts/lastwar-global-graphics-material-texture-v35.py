#!/usr/bin/env python3
from __future__ import annotations

"""V35 exact Material -> Texture2D enrichment for WfGg PTR3D manifests.

The V34 PTR3D builder already resolves the selected prefab through Unity PPtrs and exports the
referenced Mesh objects.  This module wraps that builder and follows the renderer/material graph on
the *same GameObjects* so the viewer can recover the texture sheets that the game actually binds to
those meshes.

Important properties:
- no filename-only substitution is used for the "exact" bindings;
- material slots are preserved so a model with several submeshes can use different texture sheets;
- every exported Texture2D is kept next to the OBJ files and served by the existing /model-file API;
- failures are non-fatal: a perfectly valid 3D mesh still opens even when one mobile texture format
  cannot be converted by the local UnityPy build.
"""

from pathlib import Path
from urllib.parse import quote
import gc
import importlib.util
import json
import re
import threading

HERE = Path(__file__).resolve().parent
BASE = HERE / 'lastwar-global-graphics-ptrmodel-v34.py'

spec = importlib.util.spec_from_file_location('wfgg_ptrmodel_v34_texture_helpers', BASE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

TEXTURE_BINDING_SCHEMA = 3501
MAX_GAMEOBJECTS = 360
MAX_TEXTURES = 72
LOCK = threading.RLock()


def _safe(s):
    return re.sub(r'[^a-zA-Z0-9_.-]+', '_', str(s or ''))[:96] or 'texture'


def _reader_key(reader):
    try:
        af = str(getattr(getattr(reader, 'assets_file', None), 'name', '') or '')
    except Exception:
        af = ''
    return (af, getattr(reader, 'path_id', id(reader)))


def _ptr_list(value):
    if value is None:
        return []
    try:
        return list(value)
    except Exception:
        return []


def _material_readers(component):
    vals = getattr(component, 'm_Materials', None)
    if vals is None:
        vals = getattr(component, 'materials', None)
    out = []
    for slot, ptr in enumerate(_ptr_list(vals)):
        reader = p._reader_from(ptr)
        if reader is not None and p._type_name(reader) == 'Material':
            out.append((slot, reader))
    return out


def _pair(entry):
    if isinstance(entry, (tuple, list)) and len(entry) >= 2:
        return entry[0], entry[1]
    for ka, va in (('first', 'second'), ('key', 'value'), ('Key', 'Value')):
        try:
            k = getattr(entry, ka)
            v = getattr(entry, va)
            return k, v
        except Exception:
            pass
    if isinstance(entry, dict):
        if len(entry) == 1:
            return next(iter(entry.items()))
        for ka, va in (('first', 'second'), ('key', 'value'), ('Key', 'Value')):
            if ka in entry and va in entry:
                return entry[ka], entry[va]
    return None, None


def _texenv_items(material):
    saved = getattr(material, 'm_SavedProperties', None)
    if saved is None:
        saved = getattr(material, 'savedProperties', None)
    if saved is None:
        return []
    envs = getattr(saved, 'm_TexEnvs', None)
    if envs is None:
        envs = getattr(saved, 'TexEnvs', None)
    if envs is None:
        return []
    if isinstance(envs, dict):
        return list(envs.items())
    out = []
    for entry in _ptr_list(envs):
        k, v = _pair(entry)
        if k is not None:
            out.append((k, v))
    return out


def _semantic(prop, tex_name=''):
    s = (str(prop or '') + ' ' + str(tex_name or '')).lower()
    if any(x in s for x in ('normal', 'bump', '_n ', '_n.', '_n_')):
        return 'normal'
    if any(x in s for x in ('emission', 'emissive', 'glow')):
        return 'emission'
    if any(x in s for x in ('metal', 'rough', 'smooth', 'spec', 'mask', 'occlusion', 'ambientocclusion', '_ao')):
        return 'material'
    if any(x in s for x in ('basecolor', 'base_map', 'basemap', 'maintex', 'albedo', 'diffuse', 'color', '_d ', '_d.', '_d_')):
        return 'color'
    return 'unknown'


def _image_from_texture(tex):
    # UnityPy Texture2D objects normally expose a Pillow image property.  Keep several guarded
    # fallbacks because Android installs may carry slightly different UnityPy revisions.
    for name in ('image', 'get_image'):
        try:
            value = getattr(tex, name, None)
            if value is None:
                continue
            img = value() if callable(value) else value
            if img is not None and hasattr(img, 'save'):
                return img
        except Exception:
            pass
    try:
        from UnityPy.export import Texture2DConverter
        for name in ('get_image_from_texture2d', 'parse_image'):
            fn = getattr(Texture2DConverter, name, None)
            if callable(fn):
                try:
                    img = fn(tex)
                    if img is not None and hasattr(img, 'save'):
                        return img
                except Exception:
                    pass
    except Exception:
        pass
    return None


def _texture_reader_from_env(env):
    if env is None:
        return None
    for name in ('m_Texture', 'texture', 'Texture'):
        try:
            reader = p._reader_from(getattr(env, name, None))
            if reader is not None:
                return reader
        except Exception:
            pass
    if isinstance(env, dict):
        for name in ('m_Texture', 'texture', 'Texture'):
            if name in env:
                reader = p._reader_from(env.get(name))
                if reader is not None:
                    return reader
    return None


def _export_texture(reader, outdir, sid, export_cache, errors):
    key = _reader_key(reader)
    if key in export_cache:
        return export_cache[key]
    if len(export_cache) >= MAX_TEXTURES:
        return None
    typ = p._type_name(reader)
    if typ not in {'Texture2D', 'Texture'}:
        return None
    name = p._obj_name(reader) or ('texture-' + str(getattr(reader, 'path_id', 'unknown')))
    try:
        tex = reader.read()
        img = _image_from_texture(tex)
        if img is None:
            raise RuntimeError('UnityPy image converter unavailable')
        pid = getattr(reader, 'path_id', len(export_cache))
        fn = f'texture-ptr-{len(export_cache):02d}-{_safe(name)}-{pid}.png'
        fp = outdir / fn
        # Force a browser-friendly mode; Pillow may otherwise preserve uncommon channel layouts.
        try:
            if getattr(img, 'mode', '') not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
        except Exception:
            pass
        img.save(fp, 'PNG')
        rec = {
            'path': fn,
            'kind': 'png',
            'bytes': fp.stat().st_size,
            'url': '/api/v33/model-file?id=' + quote(sid) + '&file=' + quote(fn, safe='/'),
            'textureName': name,
            'texturePathId': pid,
            'exact': True,
        }
        export_cache[key] = rec
        return rec
    except Exception as exc:
        errors.append('Texture2D ' + name + ': ' + type(exc).__name__ + ': ' + str(exc)[:220])
        export_cache[key] = None
        return None


def _mesh_material_records(root_go):
    """Return exact mesh PPtr -> renderer material slots reached from the prefab graph."""
    queue = [(root_go, 'root')]
    visited = set()
    records = []
    nodes = 0
    while queue and nodes < MAX_GAMEOBJECTS:
        go_reader, route = queue.pop(0)
        key = _reader_key(go_reader)
        if key in visited:
            continue
        visited.add(key)
        nodes += 1
        try:
            go = go_reader.read()
        except Exception:
            continue
        go_name = p._obj_name(go_reader)
        components = list(p._component_ptrs(go))
        decoded = []
        for cr in components:
            typ = p._type_name(cr)
            if typ in {'Transform', 'RectTransform'}:
                continue
            try:
                comp = cr.read()
            except Exception:
                continue
            decoded.append((cr, typ, comp))

        renderer_materials = []
        for cr, typ, comp in decoded:
            mats = _material_readers(comp)
            if mats and ('Renderer' in typ or typ in {'MeshRenderer', 'SkinnedMeshRenderer'}):
                renderer_materials.append((typ, mats))

        for cr, typ, comp in decoded:
            meshes = list(p._mesh_ptrs(comp))
            if not meshes:
                continue
            own_mats = _material_readers(comp)
            if own_mats:
                mats = own_mats
                renderer_type = typ
            elif renderer_materials:
                renderer_type, mats = renderer_materials[0]
            else:
                renderer_type, mats = '', []
            for mesh_reader, field in meshes:
                records.append({
                    'meshKey': _reader_key(mesh_reader),
                    'meshPathId': getattr(mesh_reader, 'path_id', None),
                    'gameObject': go_name,
                    'meshComponent': typ,
                    'rendererType': renderer_type,
                    'route': route + '/' + typ + '.' + field,
                    'materials': mats,
                })

        tr_reader, tr = p._go_transform(go_reader)
        if tr is None:
            continue
        for i, ptr in enumerate(getattr(tr, 'm_Children', None) or []):
            child_tr_reader = p._reader_from(ptr)
            if child_tr_reader is None:
                continue
            try:
                child_tr = child_tr_reader.read()
            except Exception:
                continue
            child_go = p._reader_from(getattr(child_tr, 'm_GameObject', None))
            if child_go is not None and p._type_name(child_go) == 'GameObject':
                queue.append((child_go, route + f'/child[{i}]'))
    return records, nodes


def _material_bindings(material_reader, slot, outdir, sid, export_cache, errors, context):
    out = []
    mat_name = p._obj_name(material_reader) or ('Material ' + str(slot))
    mat_pid = getattr(material_reader, 'path_id', None)
    try:
        material = material_reader.read()
    except Exception as exc:
        errors.append('Material ' + mat_name + ': ' + str(exc)[:180])
        return out
    for prop, env in _texenv_items(material):
        tex_reader = _texture_reader_from_env(env)
        if tex_reader is None:
            continue
        rec = _export_texture(tex_reader, outdir, sid, export_cache, errors)
        if not rec:
            continue
        binding = dict(rec)
        binding.update({
            'materialSlot': int(slot),
            'materialName': mat_name,
            'materialPathId': mat_pid,
            'property': str(prop or ''),
            'semantic': _semantic(prop, rec.get('textureName')),
            'rendererType': context.get('rendererType') or '',
            'gameObject': context.get('gameObject') or '',
            'meshPathId': context.get('meshPathId'),
            'exact': True,
        })
        out.append(binding)
    return out


def enrich_manifest(a, manifest, core, model_cache, dependency_rows):
    sid = str(a.get('stable_id') or manifest.get('stableId') or '')
    if not sid or not manifest.get('objects'):
        return manifest
    if manifest.get('textureBindingsSchema') == TEXTURE_BINDING_SCHEMA:
        return manifest

    outdir = Path(model_cache) / sid
    outdir.mkdir(parents=True, exist_ok=True)
    closure = Path(model_cache) / 'closure' / sid
    paths = sorted(closure.glob('bundle-*.bundle')) if closure.is_dir() else []
    sources = []
    if not paths:
        try:
            paths, sources = p._materialize(core, dependency_rows, a, Path(model_cache))
        except Exception as exc:
            m = dict(manifest)
            m['textureBindingsSchema'] = TEXTURE_BINDING_SCHEMA
            m['textureBindingStatus'] = 'closure-unavailable'
            m['textureBindingErrors'] = [str(exc)[:300]]
            return m
    if not paths:
        m = dict(manifest)
        m['textureBindingsSchema'] = TEXTURE_BINDING_SCHEMA
        m['textureBindingStatus'] = 'no-local-closure'
        return m

    try:
        import UnityPy
    except Exception as exc:
        m = dict(manifest)
        m['textureBindingsSchema'] = TEXTURE_BINDING_SCHEMA
        m['textureBindingStatus'] = 'unitypy-missing'
        m['textureBindingErrors'] = [str(exc)[:240]]
        return m

    env = None
    errors = []
    export_cache = {}
    try:
        env = UnityPy.load(*[str(x) for x in paths])
        anchor, anchor_mode = p._container_reader(env, a, core)
        if anchor is None:
            raise RuntimeError('TEXTURE_ROOT_NOT_FOUND: ' + str(anchor_mode))
        root = p._root_gameobject(anchor)
        if root is None:
            raise RuntimeError('TEXTURE_ROOT_NOT_GAMEOBJECT')
        mesh_records, graph_nodes = _mesh_material_records(root)

        by_pid = {}
        for rec in mesh_records:
            by_pid.setdefault(rec.get('meshPathId'), []).append(rec)

        object_textures = {}
        exact_count = 0
        exported_objects = list(manifest.get('exportedObjects') or [])
        objects = list(manifest.get('objects') or [])
        for i, obj in enumerate(objects):
            meta = exported_objects[i] if i < len(exported_objects) else {}
            pid = meta.get('pathId')
            candidates = by_pid.get(pid) or []
            if len(candidates) > 1 and meta.get('gameObject'):
                same = [x for x in candidates if x.get('gameObject') == meta.get('gameObject')]
                if same:
                    candidates = same
            if not candidates:
                continue
            rec = candidates[0]
            bindings = []
            for slot, mat_reader in rec.get('materials') or []:
                bindings.extend(_material_bindings(mat_reader, slot, outdir, sid, export_cache, errors, rec))
            if bindings:
                object_textures[str(obj.get('path') or ('object-' + str(i)))] = bindings
                exact_count += len(bindings)

        m = dict(manifest)
        files = list(m.get('files') or [])
        existing = {str(x.get('path')) for x in files if isinstance(x, dict)}
        for rec in export_cache.values():
            if rec and rec.get('path') not in existing:
                files.append(dict(rec))
                existing.add(rec.get('path'))
        m['files'] = files
        m['objectTextures'] = object_textures
        m['textureBindingsSchema'] = TEXTURE_BINDING_SCHEMA
        m['textureBindingStatus'] = 'exact-material-ptr' if object_textures else 'no-texture-ptr'
        m['textureBindingCount'] = exact_count
        m['textureFileCount'] = sum(1 for x in export_cache.values() if x)
        m['textureGraphNodes'] = graph_nodes
        m['textureRootAnchor'] = anchor_mode
        if sources:
            m['textureBundleSources'] = sources
        m['textureBindingErrors'] = errors[:40]
        try:
            (outdir / 'manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2), 'utf-8')
        except Exception as exc:
            errors.append('manifest-write: ' + str(exc)[:180])
        return m
    except Exception as exc:
        m = dict(manifest)
        m['textureBindingsSchema'] = TEXTURE_BINDING_SCHEMA
        m['textureBindingStatus'] = 'enrich-failed'
        m['textureBindingErrors'] = (errors + [type(exc).__name__ + ': ' + str(exc)])[:40]
        return m
    finally:
        try:
            del env
        except Exception:
            pass
        gc.collect()


def install(core, model_cache, dependency_rows):
    """Wrap the already-installed PTR3D builder with exact material/texture enrichment."""
    model_cache = Path(model_cache)
    previous = core.build_model

    def build(a):
        with LOCK:
            manifest = previous(a)
            try:
                enriched = enrich_manifest(a, manifest, core, model_cache, dependency_rows)
                print(
                    'V35_TEXTURE_BINDINGS', a.get('stable_id'),
                    'status=' + str(enriched.get('textureBindingStatus')),
                    'bindings=' + str(enriched.get('textureBindingCount', 0)),
                    'files=' + str(enriched.get('textureFileCount', 0)),
                    flush=True,
                )
                return enriched
            except Exception as exc:
                print('V35_TEXTURE_BINDINGS_ERROR', a.get('stable_id'), type(exc).__name__, str(exc)[:400], flush=True)
                return manifest

    core.build_model = build
    print('V35_TEXTURE_BINDINGS_INSTALLED exact-material-ptr=ON material-slots=ON uv-viewer-ready=ON', flush=True)
    return build
