import bpy
import json
import os
import sys
from mathutils import Vector


def _op(path, **kwargs):
    cur = bpy.ops
    for part in path.split('.'):
        cur = getattr(cur, part)
    return cur(**kwargs)


def _has_op(path):
    cur = bpy.ops
    try:
        for part in path.split('.'):
            cur = getattr(cur, part)
        return True
    except Exception:
        return False


def _reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _load_asset(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.blend':
        bpy.ops.wm.open_mainfile(filepath=path)
        return 'wm.open_mainfile'

    _reset()
    candidates = {
        '.glb': ['import_scene.gltf'],
        '.gltf': ['import_scene.gltf'],
        '.fbx': ['wm.fbx_import', 'import_scene.fbx'],
        '.obj': ['wm.obj_import', 'import_scene.obj'],
        '.stl': ['wm.stl_import', 'import_mesh.stl'],
        '.ply': ['wm.ply_import', 'import_mesh.ply'],
        '.dae': ['wm.collada_import'],
        '.usd': ['wm.usd_import'],
        '.usda': ['wm.usd_import'],
        '.usdc': ['wm.usd_import'],
        '.abc': ['wm.alembic_import'],
    }
    if ext not in candidates:
        raise RuntimeError(f'unsupported_extension:{ext}')

    errors = []
    for name in candidates[ext]:
        if not _has_op(name):
            errors.append(f'{name}:missing')
            continue
        try:
            _op(name, filepath=path)
            return name
        except Exception as exc:
            errors.append(f'{name}:{type(exc).__name__}')
    raise RuntimeError('import_failed:' + '|'.join(errors))


def _bounds_world(objects):
    pts = []
    for obj in objects:
        try:
            for corner in obj.bound_box:
                pts.append(obj.matrix_world @ Vector(corner))
        except Exception:
            pass
    if not pts:
        return None
    mins = [min(p[i] for p in pts) for i in range(3)]
    maxs = [max(p[i] for p in pts) for i in range(3)]
    return {
        'min': mins,
        'max': maxs,
        'dimensions': [maxs[i] - mins[i] for i in range(3)],
    }


def _build_report(path, importer):
    scene = bpy.context.scene
    objects = list(scene.objects)
    counts = {}
    for obj in objects:
        counts[obj.type] = counts.get(obj.type, 0) + 1

    meshes = []
    armatures = []
    for obj in objects:
        if obj.type == 'MESH':
            mesh = obj.data
            meshes.append({
                'object': obj.name,
                'mesh': mesh.name,
                'vertices': len(mesh.vertices),
                'edges': len(mesh.edges),
                'faces': len(mesh.polygons),
                'uv_layers': len(mesh.uv_layers),
                'material_slots': len(obj.material_slots),
                'shape_keys': 0 if not mesh.shape_keys else len(mesh.shape_keys.key_blocks),
            })
        elif obj.type == 'ARMATURE':
            armatures.append({
                'object': obj.name,
                'armature': obj.data.name,
                'bones': len(obj.data.bones),
            })

    materials = []
    for mat in bpy.data.materials:
        materials.append({
            'name': mat.name,
            'use_nodes': bool(mat.use_nodes),
            'node_count': len(mat.node_tree.nodes) if mat.use_nodes and mat.node_tree else 0,
        })

    images = []
    for image in bpy.data.images:
        images.append({
            'name': image.name,
            'size': [int(image.size[0]), int(image.size[1])],
            'source': image.source,
            'filepath': image.filepath,
            'packed': bool(image.packed_file),
        })

    actions = []
    for action in bpy.data.actions:
        try:
            frame_range = [float(action.frame_range[0]), float(action.frame_range[1])]
        except Exception:
            frame_range = None
        actions.append({'name': action.name, 'frame_range': frame_range})

    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    return {
        'schema': 'wfgg.blender.inspect.v1',
        'source': {
            'path': os.path.abspath(path),
            'size_bytes': os.path.getsize(path),
            'extension': os.path.splitext(path)[1].lower(),
            'importer': importer,
        },
        'blender': {'version': bpy.app.version_string, 'background': bpy.app.background},
        'scene': {
            'name': scene.name,
            'frame_start': int(scene.frame_start),
            'frame_end': int(scene.frame_end),
            'fps': fps,
            'object_count': len(objects),
            'object_types': counts,
            'bounds_world': _bounds_world(objects),
        },
        'meshes': meshes,
        'armatures': armatures,
        'materials': materials,
        'images': images,
        'actions': actions,
        'collections': [c.name for c in bpy.data.collections],
    }


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if not args:
        print('WFGG_BRIDGE_ERROR missing_asset', flush=True)
        return 2

    path = os.path.abspath(args[0])
    out = args[1] if len(args) > 1 else None
    if not os.path.isfile(path):
        print('WFGG_BRIDGE_ERROR file_not_found:' + path, flush=True)
        return 3

    try:
        importer = _load_asset(path)
        report = _build_report(path, importer)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if out:
            out = os.path.abspath(out)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'w', encoding='utf-8') as fh:
                fh.write(text + '\n')
        print('WFGG_BRIDGE_OK', flush=True)
        print(text, flush=True)
        return 0
    except Exception as exc:
        print(f'WFGG_BRIDGE_ERROR {type(exc).__name__}: {exc}', flush=True)
        raise


raise SystemExit(main())
