#!/usr/bin/env python3
from __future__ import annotations

"""Exact mesh<->Transform bindings for WfGg V39 animation playback.

The V34 exporter bakes world transforms into OBJ vertices. This module reconstructs the same exact
PPtr traversal route and records the rest Transform hierarchy so a browser can apply an animated
world/rest-world delta to those baked vertices. No name-based mesh substitution is permitted.
"""

from pathlib import Path
import gc, json, re, time

SCHEMA = 3911
MAX_NODES = 480
MAX_MESHES = 96


def _type(reader, ptr):
    try:
        return ptr._type_name(reader)
    except Exception:
        return ''


def _name(reader, ptr):
    try:
        return ptr._obj_name(reader)
    except Exception:
        return ''


def _matrix_list(m):
    return [[float(x) for x in row] for row in m]


def _vec3(v, default):
    try:
        return [float(v.x), float(v.y), float(v.z)]
    except Exception:
        pass
    return list(default)


def _quat(v):
    try:
        return [float(v.x), float(v.y), float(v.z), float(v.w)]
    except Exception:
        return [0.0, 0.0, 0.0, 1.0]


def _cache_signature(a, sources):
    return json.dumps({
        'schema': SCHEMA,
        'stableId': a.get('stable_id'),
        'bundleId': a.get('bundle_id'),
        'fragmentEntry': a.get('fragment_entry'),
        'sources': [(x.get('bundleId'), x.get('source'), x.get('ok')) for x in sources],
    }, sort_keys=True, ensure_ascii=False)


def build_bindings(a, core, ptr, dependency_rows, cache_root):
    sid = str(a.get('stable_id') or '')
    if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
        raise ValueError('invalid stable id')
    cache_root = Path(cache_root)
    outdir = cache_root / 'animation-bindings-v39' / sid
    cache_file = outdir / 'bindings.json'
    work_cache = cache_root / 'animation-bindings-v39-work'
    outdir.mkdir(parents=True, exist_ok=True)

    paths, sources = ptr._materialize(core, dependency_rows, a, work_cache)
    if not paths:
        raise RuntimeError('V39_BINDINGS_NO_LOCAL_CLOSURE')
    signature = _cache_signature(a, sources)
    if cache_file.is_file():
        try:
            old = json.loads(cache_file.read_text('utf-8'))
            if old.get('schemaVersion') == SCHEMA and old.get('cacheSignature') == signature:
                old['cacheHit'] = True
                return old
        except Exception:
            pass

    try:
        import UnityPy
    except Exception as exc:
        raise RuntimeError('V39_BINDINGS_UNITYPY_MISSING: ' + str(exc)) from exc

    env = None
    started = time.time()
    try:
        env = UnityPy.load(*[str(p) for p in paths])
        anchor, anchor_mode = ptr._container_reader(env, a, core)
        if anchor is None:
            raise RuntimeError('V39_BINDINGS_ROOT_NOT_FOUND: ' + str(anchor_mode))
        root = ptr._root_gameobject(anchor)
        if root is None:
            raise RuntimeError('V39_BINDINGS_ROOT_NOT_GAMEOBJECT')

        queue = [(root, ptr._identity(), 'root', '', None)]
        visited = set()
        nodes = []
        meshes = []
        while queue and len(nodes) < MAX_NODES and len(meshes) < MAX_MESHES:
            go_reader, parent_world, route, node_path, parent_route = queue.pop(0)
            key = (str(getattr(getattr(go_reader, 'assets_file', None), 'name', '')), getattr(go_reader, 'path_id', id(go_reader)))
            if key in visited:
                continue
            visited.add(key)
            try:
                go = go_reader.read()
            except Exception:
                continue
            go_name = _name(go_reader, ptr) or (node_path.rsplit('/', 1)[-1] if node_path else 'Root')
            tr_reader, tr = ptr._go_transform(go_reader)
            local_matrix = ptr._local_matrix(tr) if tr is not None else ptr._identity()
            world = ptr._mul(parent_world, local_matrix)
            local = {
                'position': _vec3(getattr(tr, 'm_LocalPosition', None), (0.0, 0.0, 0.0)) if tr is not None else [0.0, 0.0, 0.0],
                'rotation': _quat(getattr(tr, 'm_LocalRotation', None)) if tr is not None else [0.0, 0.0, 0.0, 1.0],
                'scale': _vec3(getattr(tr, 'm_LocalScale', None), (1.0, 1.0, 1.0)) if tr is not None else [1.0, 1.0, 1.0],
            }
            component_types = []
            for comp_reader in ptr._component_ptrs(go):
                typ = _type(comp_reader, ptr)
                component_types.append(typ)
                if typ in {'Transform', 'RectTransform'}:
                    continue
                try:
                    comp = comp_reader.read()
                except Exception:
                    continue
                for mesh_reader, field in ptr._mesh_ptrs(comp):
                    meshes.append({
                        'pointerRoute': route + '/' + typ + '.' + field,
                        'nodeRoute': route,
                        'nodePath': node_path,
                        'gameObject': go_name,
                        'meshPathId': getattr(mesh_reader, 'path_id', None),
                        'meshName': _name(mesh_reader, ptr),
                        'restWorldMatrix': _matrix_list(world),
                    })
                    if len(meshes) >= MAX_MESHES:
                        break
            nodes.append({
                'route': route,
                'parentRoute': parent_route,
                'path': node_path,
                'name': go_name,
                'localTransform': local,
                'restLocalMatrix': _matrix_list(local_matrix),
                'restWorldMatrix': _matrix_list(world),
                'components': component_types,
            })
            if tr is None:
                continue
            for i, child_ptr in enumerate(getattr(tr, 'm_Children', None) or []):
                child_tr_reader = ptr._reader_from(child_ptr)
                if child_tr_reader is None:
                    continue
                try:
                    child_tr = child_tr_reader.read()
                except Exception:
                    continue
                child_go = ptr._reader_from(getattr(child_tr, 'm_GameObject', None))
                if child_go is None or _type(child_go, ptr) != 'GameObject':
                    continue
                child_name = _name(child_go, ptr) or ('child-' + str(i))
                child_path = child_name if not node_path else node_path + '/' + child_name
                queue.append((child_go, world, route + f'/child[{i}]', child_path, route))

        path_counts = {}
        for n in nodes:
            path_counts[n['path']] = path_counts.get(n['path'], 0) + 1
        duplicate_paths = sorted([p for p, count in path_counts.items() if count > 1])
        payload = {
            'schemaVersion': SCHEMA,
            'stableId': sid,
            'cacheSignature': signature,
            'cacheHit': False,
            'scanSeconds': round(time.time() - started, 3),
            'rootAnchor': anchor_mode,
            'rootGameObject': _name(root, ptr),
            'nodeCount': len(nodes),
            'meshBindingCount': len(meshes),
            'truncated': bool(queue),
            'duplicateAnimationPaths': duplicate_paths,
            'nodes': nodes,
            'meshBindings': meshes,
            'policy': 'Bindings are generated from the exact same Transform/component PPtr route semantics as V34 PTR3D; no mesh name fallback is used.',
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), 'utf-8')
        return payload
    finally:
        try:
            del env
        except Exception:
            pass
        gc.collect()
