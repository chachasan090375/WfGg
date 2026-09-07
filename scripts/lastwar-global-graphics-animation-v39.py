#!/usr/bin/env python3
from __future__ import annotations

"""Exact Unity animation diagnostics for the WfGg Last War graphics LAB (V39).

The scanner is deliberately conservative. It reports animation evidence found in the exact
AssetBundle/PPtr closure of the selected catalogue asset and extracts only transform curves that
UnityPy exposes losslessly. It never invents motion. Modern/compressed Mecanim data, scripts and
shader-driven movement are reported as evidence but remain diagnostic-only until decoded.
"""

from pathlib import Path
import gc, json, math, re, time

SCHEMA = 3901
MAX_NODES = 480
MAX_COMPONENTS = 1800
MAX_CLIPS = 160
MAX_CURVE_KEYS = 24000
ANIMATION_SCRIPT_TOKENS = (
    'anim', 'rotate', 'rotation', 'rotator', 'spin', 'spinner', 'orbit', 'turn',
    'move', 'moving', 'motion', 'loop', 'float', 'bob', 'swing', 'revolve', 'roll'
)
TRANSFORM_CURVE_FIELDS = (
    ('rotation', 'm_RotationCurves'),
    ('euler', 'm_EulerCurves'),
    ('position', 'm_PositionCurves'),
    ('scale', 'm_ScaleCurves'),
)
OTHER_CURVE_FIELDS = (
    ('compressedRotation', 'm_CompressedRotationCurves'),
    ('float', 'm_FloatCurves'),
    ('pptr', 'm_PPtrCurves'),
)


def _type_name(reader):
    try:
        return str(getattr(reader.type, 'name', reader.type))
    except Exception:
        return ''


def _path_id(reader):
    try:
        return int(getattr(reader, 'path_id'))
    except Exception:
        return None


def _file_name(reader):
    try:
        return str(getattr(getattr(reader, 'assets_file', None), 'name', '') or '')
    except Exception:
        return ''


def _name(reader):
    try:
        n = reader.peek_name()
        if n:
            return str(n)
    except Exception:
        pass
    try:
        data = reader.read()
        return str(getattr(data, 'm_Name', '') or getattr(data, 'name', '') or '')
    except Exception:
        return ''


def _json_number(v):
    try:
        f = float(v)
        if math.isfinite(f):
            return f
    except Exception:
        pass
    return None


def _json_value(v, depth=0):
    if depth > 4:
        return None
    if v is None or isinstance(v, (str, bool, int)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        out = {}
        for k, x in list(v.items())[:32]:
            y = _json_value(x, depth + 1)
            if y is not None:
                out[str(k)] = y
        return out
    if isinstance(v, (list, tuple)):
        return [_json_value(x, depth + 1) for x in list(v)[:32]]
    coords = []
    for key in ('x', 'y', 'z', 'w'):
        if hasattr(v, key):
            n = _json_number(getattr(v, key, None))
            if n is not None:
                coords.append((key, n))
    if coords:
        return {k: n for k, n in coords}
    n = _json_number(v)
    return n


def _vec3(v, default=(0.0, 0.0, 0.0)):
    if v is None:
        return list(default)
    try:
        return [float(v.x), float(v.y), float(v.z)]
    except Exception:
        pass
    if isinstance(v, (tuple, list)) and len(v) >= 3:
        try:
            return [float(v[0]), float(v[1]), float(v[2])]
        except Exception:
            pass
    return list(default)


def _quat(v):
    if v is None:
        return [0.0, 0.0, 0.0, 1.0]
    try:
        return [float(v.x), float(v.y), float(v.z), float(v.w)]
    except Exception:
        pass
    if isinstance(v, (tuple, list)) and len(v) >= 4:
        try:
            return [float(v[0]), float(v[1]), float(v[2]), float(v[3])]
        except Exception:
            pass
    return [0.0, 0.0, 0.0, 1.0]


def _reader_from(value, ptr):
    try:
        return ptr._reader_from(value)
    except Exception:
        return None


def _read_tree(reader):
    try:
        tree = reader.read_typetree()
        if isinstance(tree, dict):
            return tree, 'typetree'
    except Exception:
        pass
    try:
        data = reader.read()
        if hasattr(data, 'read_typetree'):
            tree = data.read_typetree()
            if isinstance(tree, dict):
                return tree, 'typetree-data'
    except Exception:
        pass
    return {}, 'unavailable'


def _tree_get(d, key, default=None):
    if isinstance(d, dict):
        if key in d:
            return d[key]
        lk = key.lower()
        for k, v in d.items():
            if str(k).lower() == lk:
                return v
    return default


def _curve_keys(curve):
    if not isinstance(curve, dict):
        return []
    body = _tree_get(curve, 'curve', curve)
    if not isinstance(body, dict):
        return []
    keys = _tree_get(body, 'm_Curve', []) or _tree_get(body, 'curve', []) or []
    return keys if isinstance(keys, list) else []


def _serialize_key(k):
    if not isinstance(k, dict):
        return None
    t = _json_number(_tree_get(k, 'time'))
    if t is None:
        return None
    out = {'time': t}
    for field in ('value', 'inSlope', 'outSlope', 'weightedMode', 'inWeight', 'outWeight'):
        value = _tree_get(k, field)
        if value is not None:
            sv = _json_value(value)
            if sv is not None:
                out[field] = sv
    return out


def _clip_summary(reader):
    tree, tree_mode = _read_tree(reader)
    name = str(_tree_get(tree, 'm_Name', '') or _name(reader) or '')
    sample = _json_number(_tree_get(tree, 'm_SampleRate'))
    legacy = bool(_tree_get(tree, 'm_Legacy', False))
    wrap = _tree_get(tree, 'm_WrapMode')
    tracks = []
    curve_counts = {}
    key_budget = MAX_CURVE_KEYS
    max_time = 0.0

    for kind, field in TRANSFORM_CURVE_FIELDS:
        curves = _tree_get(tree, field, []) or []
        if not isinstance(curves, list):
            curves = []
        curve_counts[kind] = len(curves)
        for c in curves:
            if key_budget <= 0 or not isinstance(c, dict):
                break
            path = str(_tree_get(c, 'path', '') or _tree_get(c, 'm_Path', '') or '')
            raw_keys = _curve_keys(c)
            keys = []
            for raw in raw_keys[:key_budget]:
                sk = _serialize_key(raw)
                if sk is not None:
                    keys.append(sk)
                    max_time = max(max_time, float(sk['time']))
            key_budget -= len(raw_keys)
            if keys:
                tracks.append({'kind': kind, 'path': path, 'keys': keys})

    for kind, field in OTHER_CURVE_FIELDS:
        curves = _tree_get(tree, field, []) or []
        curve_counts[kind] = len(curves) if isinstance(curves, list) else 0

    muscle = _tree_get(tree, 'm_MuscleClip') or {}
    stop = None
    if isinstance(muscle, dict):
        stop = _json_number(_tree_get(muscle, 'm_StopTime'))
        if stop is None:
            stop = _json_number(_tree_get(muscle, 'm_StopTimeInSeconds'))
    duration = max([x for x in (max_time, stop) if isinstance(x, (int, float))], default=0.0)
    simple_key_count = sum(len(t['keys']) for t in tracks)
    compressed = bool(curve_counts.get('compressedRotation')) or (not tracks and bool(muscle))
    return {
        'name': name,
        'pathId': _path_id(reader),
        'assetsFile': _file_name(reader),
        'treeMode': tree_mode,
        'sampleRate': sample,
        'legacy': legacy,
        'wrapMode': _json_value(wrap),
        'duration': duration or None,
        'curveCounts': curve_counts,
        'simpleTransformKeyCount': simple_key_count,
        'simpleTransformTracks': tracks,
        'compressedOrMecanim': compressed,
        'exactSimpleCurvesDecoded': bool(tracks),
    }


def _linked_clip_readers(component_reader, ptr):
    """Resolve only direct serialized PPtr links; do not name-guess clips."""
    out = []
    seen = set()
    try:
        data = component_reader.read()
    except Exception:
        return out

    def add(v, evidence):
        r = _reader_from(v, ptr)
        if r is None:
            return
        typ = _type_name(r)
        key = (_file_name(r), _path_id(r), typ)
        if key in seen:
            return
        seen.add(key)
        if typ == 'AnimationClip':
            out.append((r, evidence))
        elif typ in {'AnimatorController', 'AnimatorOverrideController'}:
            try:
                ctrl = r.read()
            except Exception:
                return
            for fld in ('m_AnimationClips', 'm_Clips', 'm_AnimationClip', 'm_Clip', 'm_Motions', 'm_Motion'):
                vals = getattr(ctrl, fld, None)
                if vals is None:
                    continue
                if not isinstance(vals, (list, tuple)):
                    vals = [vals]
                for i, x in enumerate(vals):
                    rr = _reader_from(x, ptr)
                    if rr is not None and _type_name(rr) == 'AnimationClip':
                        k2 = (_file_name(rr), _path_id(rr), 'AnimationClip')
                        if k2 not in seen:
                            seen.add(k2)
                            out.append((rr, evidence + f'->{typ}.{fld}[{i}]'))

    for fld in ('m_Animation', 'm_Animations', 'm_AnimationClips', 'm_Clips', 'm_AnimationClip', 'm_Clip', 'm_Motion', 'm_Controller'):
        vals = getattr(data, fld, None)
        if vals is None:
            continue
        if not isinstance(vals, (list, tuple)):
            vals = [vals]
        for i, x in enumerate(vals):
            add(x, f'{_type_name(component_reader)}.{fld}[{i}]')
    return out


def _script_info(reader, ptr):
    try:
        data = reader.read()
    except Exception:
        return {'pathId': _path_id(reader), 'className': '', 'scriptName': '', 'animationHint': False}
    script_reader = _reader_from(getattr(data, 'm_Script', None), ptr)
    class_name = script_name = namespace = assembly = ''
    if script_reader is not None:
        try:
            s = script_reader.read()
            class_name = str(getattr(s, 'm_ClassName', '') or '')
            script_name = str(getattr(s, 'm_Name', '') or _name(script_reader) or '')
            namespace = str(getattr(s, 'm_Namespace', '') or '')
            assembly = str(getattr(s, 'm_AssemblyName', '') or '')
        except Exception:
            script_name = _name(script_reader)
    hay = ' '.join((class_name, script_name, namespace)).lower()
    hint = any(tok in hay for tok in ANIMATION_SCRIPT_TOKENS)
    return {
        'pathId': _path_id(reader), 'className': class_name, 'scriptName': script_name,
        'namespace': namespace, 'assembly': assembly, 'animationHint': hint,
    }


def _hierarchy(root_go, ptr):
    root_name = _name(root_go) or 'Root'
    queue = [(root_go, '', None)]
    visited = set()
    nodes = []
    components = []
    linked_clips = []
    particles = []
    scripts = []
    animators = []

    while queue and len(nodes) < MAX_NODES and len(components) < MAX_COMPONENTS:
        go_reader, rel_path, parent_path = queue.pop(0)
        key = (_file_name(go_reader), _path_id(go_reader))
        if key in visited:
            continue
        visited.add(key)
        try:
            go = go_reader.read()
        except Exception:
            continue
        name = _name(go_reader) or (rel_path.rsplit('/', 1)[-1] if rel_path else root_name)
        tr_reader, tr = ptr._go_transform(go_reader)
        local = {
            'position': _vec3(getattr(tr, 'm_LocalPosition', None), (0.0, 0.0, 0.0)),
            'rotation': _quat(getattr(tr, 'm_LocalRotation', None)),
            'scale': _vec3(getattr(tr, 'm_LocalScale', None), (1.0, 1.0, 1.0)),
        }
        comp_types = []
        for comp_reader in ptr._component_ptrs(go):
            typ = _type_name(comp_reader)
            comp_types.append(typ)
            rec = {'type': typ, 'pathId': _path_id(comp_reader), 'assetsFile': _file_name(comp_reader), 'nodePath': rel_path, 'gameObject': name}
            components.append(rec)
            if typ in {'Animation', 'Animator'}:
                animators.append(rec)
                for clip_reader, evidence in _linked_clip_readers(comp_reader, ptr):
                    linked_clips.append((clip_reader, evidence, rel_path))
            elif typ == 'ParticleSystem':
                particles.append(rec)
            elif typ == 'MonoBehaviour':
                si = _script_info(comp_reader, ptr)
                si.update({'nodePath': rel_path, 'gameObject': name})
                scripts.append(si)
        nodes.append({
            'path': rel_path, 'parentPath': parent_path, 'name': name,
            'gameObjectPathId': _path_id(go_reader),
            'transformPathId': _path_id(tr_reader) if tr_reader is not None else None,
            'localTransform': local, 'components': comp_types,
        })
        if tr is None:
            continue
        for ptr_child in getattr(tr, 'm_Children', None) or []:
            child_tr_reader = _reader_from(ptr_child, ptr)
            if child_tr_reader is None:
                continue
            try:
                child_tr = child_tr_reader.read()
            except Exception:
                continue
            child_go = _reader_from(getattr(child_tr, 'm_GameObject', None), ptr)
            if child_go is None or _type_name(child_go) != 'GameObject':
                continue
            child_name = _name(child_go) or ('child-' + str(len(queue)))
            child_path = child_name if not rel_path else rel_path + '/' + child_name
            queue.append((child_go, child_path, rel_path))

    return {
        'rootName': root_name,
        'nodes': nodes,
        'components': components,
        'animators': animators,
        'linkedClips': linked_clips,
        'particles': particles,
        'scripts': scripts,
        'truncated': bool(queue),
    }


def _cache_signature(a, sources):
    payload = {
        'schema': SCHEMA,
        'stableId': a.get('stable_id'),
        'bundleId': a.get('bundle_id'),
        'fragmentEntry': a.get('fragment_entry'),
        'tableFragment': a.get('table_fragment'),
        'sources': [(x.get('bundleId'), x.get('source'), x.get('ok')) for x in sources],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def scan_animation(a, core, ptr, dependency_rows, cache_root):
    sid = str(a.get('stable_id') or '')
    if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
        raise ValueError('invalid stable id')
    cache_root = Path(cache_root)
    outdir = cache_root / 'animations-v39' / sid
    cache_file = outdir / 'animation.json'
    work_cache = cache_root / 'animations-v39-work'
    outdir.mkdir(parents=True, exist_ok=True)

    paths, sources = ptr._materialize(core, dependency_rows, a, work_cache)
    if not paths:
        raise RuntimeError('V39_ANIMATION_NO_LOCAL_CLOSURE')

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
        raise RuntimeError('V39_ANIMATION_UNITYPY_MISSING: ' + str(exc)) from exc

    env = None
    started = time.time()
    try:
        env = UnityPy.load(*[str(p) for p in paths])
        anchor, anchor_mode = ptr._container_reader(env, a, core)
        if anchor is None:
            raise RuntimeError('V39_ANIMATION_ROOT_NOT_FOUND: ' + str(anchor_mode))
        root = ptr._root_gameobject(anchor)
        if root is None:
            raise RuntimeError('V39_ANIMATION_ROOT_NOT_GAMEOBJECT: ' + _type_name(anchor))
        h = _hierarchy(root, ptr)

        linked = {}
        for reader, evidence, node_path in h['linkedClips']:
            key = (_file_name(reader), _path_id(reader))
            rec = linked.get(key)
            if rec is None:
                rec = _clip_summary(reader)
                rec['linkage'] = 'exact-component-ptr'
                rec['evidence'] = []
                rec['componentNodePaths'] = []
                linked[key] = rec
            if evidence not in rec['evidence']:
                rec['evidence'].append(evidence)
            if node_path not in rec['componentNodePaths']:
                rec['componentNodePaths'].append(node_path)

        closure_clips = []
        linked_keys = set(linked)
        for obj in getattr(env, 'objects', []) or []:
            if len(closure_clips) >= MAX_CLIPS:
                break
            if _type_name(obj) != 'AnimationClip':
                continue
            key = (_file_name(obj), _path_id(obj))
            if key in linked_keys:
                continue
            rec = _clip_summary(obj)
            rec['linkage'] = 'closure-candidate'
            rec['evidence'] = ['AnimationClip object present in exact materialized dependency closure; not directly linked to anchored prefab']
            closure_clips.append(rec)

        clips = list(linked.values()) + closure_clips
        exact_tracks = [t for c in linked.values() for t in c.get('simpleTransformTracks') or []]
        exact_key_count = sum(len(t.get('keys') or []) for t in exact_tracks)
        hinted_scripts = [s for s in h['scripts'] if s.get('animationHint')]
        animator_count = len(h['animators'])
        particle_count = len(h['particles'])

        if exact_tracks:
            status = 'ANIMÉ — TRANSFORM'
            status_code = 'animated-transform'
        elif linked or animator_count:
            status = 'ANIMÉ — CLIP'
            status_code = 'animated-clip'
        elif particle_count:
            status = 'ANIMÉ — PARTICULES'
            status_code = 'animated-particles'
        elif hinted_scripts:
            status = 'ANIMÉ — SCRIPT'
            status_code = 'animated-script'
        else:
            status = 'STATIQUE / ANIMATION NON DÉTECTÉE'
            status_code = 'static-or-undetected'

        unresolved_reasons = []
        if animator_count and not linked:
            unresolved_reasons.append('Animator/Animation component found but no AnimationClip PPtr was resolved directly from the anchored prefab.')
        if any(c.get('compressedOrMecanim') and not c.get('exactSimpleCurvesDecoded') for c in linked.values()):
            unresolved_reasons.append('One or more linked clips use compressed/Mecanim data not decoded into simple transform curves yet.')
        if hinted_scripts:
            unresolved_reasons.append('Animation-like MonoBehaviour detected; runtime script motion is not executed by the viewer.')
        if particle_count:
            unresolved_reasons.append('ParticleSystem detected; particle runtime playback is not implemented in V39 phase 1.')

        tracks_decodable = bool(exact_tracks)
        payload = {
            'schemaVersion': SCHEMA,
            'stableId': sid,
            'scannedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'scanSeconds': round(time.time() - started, 3),
            'cacheSignature': signature,
            'cacheHit': False,
            'rootAnchor': anchor_mode,
            'rootGameObject': h['rootName'],
            'bundleSources': sources,
            'classification': {
                'status': status, 'code': status_code,
                'detectionExact': bool(animator_count or particle_count or hinted_scripts or linked),
                'hasAnimatorOrAnimation': bool(animator_count),
                'hasDirectLinkedClip': bool(linked),
                'hasParticles': bool(particle_count),
                'hasAnimationHintScript': bool(hinted_scripts),
            },
            'playback': {
                'supported': False,
                'mode': 'diagnostic-only',
                'label': 'ANIMATION DÉTECTÉE — LECTURE NON ENCORE BRANCHÉE' if status_code != 'static-or-undetected' else 'AUCUNE ANIMATION DÉTECTÉE',
                'tracksDecodable': tracks_decodable,
                'exactTransformTrackCount': len(exact_tracks),
                'exactTransformKeyCount': exact_key_count,
                'reason': 'Exact transform curves are exposed, but the current OBJ renderer still uses world-baked vertices.' if tracks_decodable else 'No lossless simple transform track is currently available for runtime playback.',
                'unresolvedReasons': unresolved_reasons,
            },
            'hierarchy': {
                'nodeCount': len(h['nodes']),
                'componentCount': len(h['components']),
                'truncated': h['truncated'],
                'nodes': h['nodes'],
            },
            'components': {
                'animatorOrAnimationCount': animator_count,
                'particleSystemCount': particle_count,
                'monoBehaviourCount': len(h['scripts']),
                'animationHintScriptCount': len(hinted_scripts),
                'animators': h['animators'],
                'particles': h['particles'],
                'scripts': h['scripts'],
            },
            'clips': {
                'directLinkedCount': len(linked),
                'closureCandidateCount': len(closure_clips),
                'items': clips,
            },
            'policy': 'Exact bundle/PPtr evidence only. Closure-only AnimationClips are candidates, never asserted as prefab-linked. No synthetic animation is generated.',
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), 'utf-8')
        return payload
    finally:
        try:
            del env
        except Exception:
            pass
        gc.collect()
