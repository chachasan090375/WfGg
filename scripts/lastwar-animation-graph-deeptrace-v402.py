#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.2 — recursive CLR call-graph trace for animation scripts.

This layer augments the deterministic V40 graph. It follows validated MethodDef calls from
MonoBehaviour lifecycle/control roots, classifies evidence by execution phase, and prevents one-shot
initialization rotations from being presented as continuous animation. No movement is synthesized.
"""

import re

FRAME_ROOTS = {'update','lateupdate','fixedupdate'}
INIT_ROOTS = {'awake','start','onenable','onspawncomplete','onspawned','initialize','init'}
CONTROL_ROOT_RX = re.compile(r'^(play|stop|refresh|set|switch|change|show|hide|build|work|idle|open|close)', re.I)
MAX_DEPTH = 6
MAX_METHODS_PER_SCRIPT = 180
MAX_SIGNALS_PER_SCRIPT = 120


def _phase(root_name: str) -> str:
    n = str(root_name or '').casefold()
    if n in FRAME_ROOTS:
        return 'per-frame'
    if n in INIT_ROOTS:
        return 'initialization'
    return 'event/control'


def _roots_for_type(ty):
    methods = list(ty.get('methods') or [])
    preferred = []
    secondary = []
    for m in methods:
        n = str(m.get('name') or '')
        low = n.casefold()
        if low in FRAME_ROOTS or low in INIT_ROOTS:
            preferred.append(m)
        elif CONTROL_ROOT_RX.search(n):
            secondary.append(m)
    # Frame roots first because they can prove continuous motion.
    preferred.sort(key=lambda m: (0 if str(m.get('name','')).casefold() in FRAME_ROOTS else 1, str(m.get('name',''))))
    secondary.sort(key=lambda m: str(m.get('name','')))
    roots = preferred + secondary
    if not roots:
        roots = methods[:24]
    return roots[:40]


def _call_methoddef(idx, call):
    tok = str(call.get('token') or '')
    try:
        value = int(tok, 16)
    except Exception:
        return None
    table = (value >> 24) & 0xff
    rid = value & 0x00ffffff
    if table == 0x06 and 0 < rid < len(idx.methods):
        return idx.methods[rid]
    return None


def _adjust_signal(kind, base_conf, phase, root, path, call, fields):
    conf = float(base_conf or 0)
    out_kind = kind
    continuous = False
    if phase == 'per-frame':
        if kind in {'continuous-rotation','rotation-assignment','rotation-math','tween'}:
            continuous = True
            conf = max(conf, 0.985)
        elif kind in {'animator-state','legacy-animation'}:
            conf = max(conf, 0.97)
    elif phase == 'initialization' and kind in {'rotation-assignment','rotation-math'}:
        # A rotation set during spawn/start proves orientation setup, not an ongoing animation.
        out_kind = 'initial-orientation'
        conf = min(conf, 0.86)
    elif phase == 'initialization' and kind == 'continuous-rotation':
        conf = min(conf, 0.90)
    return {
        'kind': out_kind,
        'rawKind': kind,
        'confidence': round(conf, 3),
        'phase': phase,
        'continuous': continuous,
        'rootMethod': root,
        'method': ' → '.join(path),
        'call': call.get('full'),
        'token': call.get('token'),
        'fields': [f.get('full') for f in (fields or [])[:24] if f.get('full')],
    }


def trace_script(idx, base_agent, script_evidence):
    cls = str(script_evidence.get('className') or '').strip()
    result = {
        'className': cls,
        'gameObject': script_evidence.get('gameObject'),
        'roots': [],
        'signals': [],
        'methodsVisited': 0,
    }
    if not cls:
        return result

    global_seen_signals = set()
    visited_budget = 0

    for ty in idx.find_types(cls)[:4]:
        for root in _roots_for_type(ty):
            if visited_budget >= MAX_METHODS_PER_SCRIPT:
                break
            root_name = str(root.get('name') or '')
            phase = _phase(root_name)
            root_rec = {'type': ty.get('full'), 'rootMethod': root_name, 'phase': phase, 'paths': 0, 'signals': 0}
            result['roots'].append(root_rec)
            stack = [(root, [root_name], 0)]
            seen_methods = set()
            while stack and visited_budget < MAX_METHODS_PER_SCRIPT and len(result['signals']) < MAX_SIGNALS_PER_SCRIPT:
                method, path, depth = stack.pop()
                rid = int(method.get('rid') or 0)
                key = (rid, tuple(path[:2]))
                if key in seen_methods:
                    continue
                seen_methods.add(key)
                visited_budget += 1
                result['methodsVisited'] += 1
                ma = idx.analyze_method(method)
                root_rec['paths'] += 1
                for call in ma.get('calls') or []:
                    kind, conf = base_agent._signal_from_call(call.get('full'))
                    if kind:
                        sig = _adjust_signal(kind, conf, phase, root_name, path, call, ma.get('fields') or [])
                        sk = (sig['kind'], sig['phase'], sig['method'], sig['call'])
                        if sk not in global_seen_signals:
                            global_seen_signals.add(sk)
                            result['signals'].append(sig)
                            root_rec['signals'] += 1
                    if depth < MAX_DEPTH:
                        target = _call_methoddef(idx, call)
                        if target:
                            owner = str(target.get('owner') or '')
                            # Stay in Assembly-CSharp. MethodDef tokens are exact local methods.
                            next_name = str(target.get('name') or ('MethodDef#'+str(target.get('rid'))))
                            stack.append((target, path + [next_name], depth + 1))

    result['signals'].sort(key=lambda s: (
        0 if s.get('continuous') else 1,
        0 if s.get('phase') == 'per-frame' else 1 if s.get('phase') == 'event/control' else 2,
        -float(s.get('confidence') or 0),
        s.get('method') or ''
    ))
    return result


def augment(payload: dict, base_agent) -> dict:
    idx = base_agent.clr_index(False)
    traces = []
    for script in payload.get('scriptCodeEvidence') or []:
        traces.append(trace_script(idx, base_agent, script))

    deep_signals = []
    for t in traces:
        for s in t.get('signals') or []:
            rec = dict(s)
            rec['className'] = t.get('className')
            rec['gameObject'] = t.get('gameObject')
            deep_signals.append(rec)

    deep_signals.sort(key=lambda s: (
        0 if s.get('continuous') else 1,
        0 if s.get('phase') == 'per-frame' else 1 if s.get('phase') == 'event/control' else 2,
        -float(s.get('confidence') or 0)
    ))

    old_recipe = list(payload.get('motionRecipe') or [])
    recipe = []
    seen = set()
    for s in deep_signals:
        k = (s.get('kind'), s.get('phase'), s.get('className'))
        if k in seen:
            continue
        seen.add(k)
        recipe.append({
            'type': s.get('kind'),
            'confidence': s.get('confidence'),
            'phase': s.get('phase'),
            'continuous': bool(s.get('continuous')),
            'evidence': {
                'className': s.get('className'),
                'gameObject': s.get('gameObject'),
                'method': s.get('method'),
                'call': s.get('call'),
                'rootMethod': s.get('rootMethod'),
                'phase': s.get('phase'),
                'fields': s.get('fields'),
            }
        })
        if len(recipe) >= 12:
            break

    # If recursive tracing finds nothing, keep V40 evidence but explicitly mark it as shallow.
    if not recipe:
        recipe = old_recipe
        for r in recipe:
            r.setdefault('phase', 'unknown')
            r.setdefault('continuous', False)
            if isinstance(r.get('evidence'), dict):
                r['evidence'].setdefault('phase', 'unknown')

    continuous = [r for r in recipe if r.get('continuous')]
    per_frame = [r for r in recipe if r.get('phase') == 'per-frame']
    init_only = bool(recipe) and not per_frame and all(r.get('phase') in {'initialization','unknown'} for r in recipe)

    payload['version'] = '40.2'
    payload['motionRecipeV400'] = old_recipe
    payload['motionRecipe'] = recipe
    payload['deepRuntimeTrace'] = {
        'version': '40.2',
        'scripts': traces,
        'signals': deep_signals[:240],
        'continuousSignals': len([x for x in deep_signals if x.get('continuous')]),
        'perFrameSignals': len([x for x in deep_signals if x.get('phase') == 'per-frame']),
        'methodsVisited': sum(int(x.get('methodsVisited') or 0) for x in traces),
        'policy': 'Validated MethodDef recursion only; frame roots distinguish continuous runtime motion from one-shot initialization.'
    }
    summary = payload.setdefault('summary', {})
    if continuous:
        summary['status'] = 'continuous-motion-proved'
    elif per_frame:
        summary['status'] = 'per-frame-runtime-code-found'
    elif init_only:
        summary['status'] = 'initialization-motion-only-no-continuous-proof-yet'
    elif recipe:
        summary['status'] = 'runtime-motion-evidence-found-no-frame-proof-yet'
    else:
        summary['status'] = 'runtime-graph-built-no-motion-api-yet'
    summary['continuousMotionSignals'] = len(continuous)
    summary['perFrameSignals'] = len(per_frame)
    summary['deepMethodsVisited'] = payload['deepRuntimeTrace']['methodsVisited']
    summary['bestMotion'] = recipe[0] if recipe else None
    payload['policy'] = (payload.get('policy') or '') + ' V40.2 recursively follows exact Assembly-CSharp MethodDef calls and separates per-frame motion from initialization.'
    return payload
