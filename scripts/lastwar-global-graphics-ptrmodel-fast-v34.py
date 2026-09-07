#!/usr/bin/env python3
from __future__ import annotations

"""Fast staged wrapper for the exact PTR3D V34 assembler.

The first attempt keeps the Unity dependency closure deliberately small so common prefabs can
appear quickly on Android. Only if that exact PPtr walk cannot resolve the root/mesh graph do we
retry with the deeper V34 closure. The legacy strict-name renderer remains a final compatibility
fallback only when the exact graph is genuinely inconclusive. If the exact prefab graph is found
and contains no Mesh pointer, that is treated as a valid non-autonomous/VFX component instead of
falling back to name guessing and emitting RUNTIME_3D_OBJECT_MISMATCH.
"""

from pathlib import Path
import importlib.util

HERE=Path(__file__).resolve().parent
BASE=HERE/'lastwar-global-graphics-ptrmodel-v34.py'

spec=importlib.util.spec_from_file_location('wfgg_ptrmodel_v34_base',BASE)
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

PtrGraphUnavailable=p.PtrGraphUnavailable


def _attempt(a,core,correlated,dependency_rows,model_cache,bundles,depth,meshes,label):
    old_bundles,old_depth,old_meshes=p.MAX_DEP_BUNDLES,p.MAX_DEPTH,p.MAX_MESHES
    p.MAX_DEP_BUNDLES=int(bundles);p.MAX_DEPTH=int(depth);p.MAX_MESHES=int(meshes)
    try:
        m=p.build_ptr_model(a,core,correlated.exact,dependency_rows,model_cache)
        m=dict(m)
        m['assemblySpeed']=label
        m['dependencyBudget']={'bundles':bundles,'depth':depth,'meshes':meshes}
        m['assemblyAssetCount']=m.get('assemblyAssetCount') or m.get('graphNodes') or len(m.get('objects') or [])
        return m
    finally:
        p.MAX_DEP_BUNDLES, p.MAX_DEPTH, p.MAX_MESHES = old_bundles,old_depth,old_meshes


def _looks_effect_prefab(a):
    text=' '.join(str(a.get(k) or '') for k in ('asset_path','logical_name','alias_name','subject','family','subfamily','context')).replace('\\','/').lower()
    tail=str(a.get('asset_path') or a.get('logical_name') or '').replace('\\','/').rsplit('/',1)[-1].lower()
    return (
        '/effect/' in text or '/effects/' in text or '/vfx/' in text or
        tail.startswith(('eff_','fx_','vfx_')) or
        any(tok in text for tok in ('particle','particlesystem','visualeffect'))
    )


def _no_standalone(sid,reason):
    return RuntimeError(
        'RUNTIME_3D_NO_STANDALONE_MESH: asset='+str(sid)+'; '
        'le graphe Unity exact ne référence aucune géométrie Mesh autonome pour ce prefab/composant; '
        'reason='+str(reason)[:420]
    )


def install(core,correlated,model_cache,dependency_rows):
    model_cache=Path(model_cache);model_cache.mkdir(parents=True,exist_ok=True)
    fallback=core.build_model
    failed=set()
    core.MODEL_CACHE=model_cache
    try:correlated.exact.MODEL_CACHE=model_cache
    except Exception:pass

    def build(a):
        sid=a['stable_id']
        exact_reason=''
        if sid not in failed:
            try:
                m=_attempt(a,core,correlated,dependency_rows,model_cache,6,1,16,'fast-exact')
                print('V34_PTR3D_FAST_OK',sid,'meshes='+str(len(m.get('objects') or [])),'root='+str(m.get('rootGameObject') or ''),flush=True)
                return m
            except PtrGraphUnavailable as exc:
                exact_reason=str(exc)
                print('V34_PTR3D_FAST_MISS',sid,exact_reason[:320],flush=True)
            except Exception as exc:
                exact_reason=type(exc).__name__+': '+str(exc)
                print('V34_PTR3D_FAST_ERROR',sid,type(exc).__name__,str(exc)[:320],flush=True)

            try:
                m=_attempt(a,core,correlated,dependency_rows,model_cache,16,3,32,'deep-exact')
                print('V34_PTR3D_DEEP_OK',sid,'meshes='+str(len(m.get('objects') or [])),'root='+str(m.get('rootGameObject') or ''),flush=True)
                return m
            except PtrGraphUnavailable as exc:
                exact_reason=str(exc)
                failed.add(sid);print('V34_PTR3D_FALLBACK',sid,exact_reason[:500],flush=True)
                # Root was found and traversed: no Mesh pointer is definitive. Never ask the old
                # name-correlator to guess a Mesh afterwards, because that only produces a false
                # RUNTIME_3D_OBJECT_MISMATCH for VFX/particle prefabs.
                if 'PTR3D_NO_MESH_POINTER' in exact_reason:
                    print('V34_PTR3D_NONAUTONOMOUS',sid,'exact-no-mesh',flush=True)
                    raise _no_standalone(sid,exact_reason) from exc
            except Exception as exc:
                exact_reason=type(exc).__name__+': '+str(exc)
                failed.add(sid);print('V34_PTR3D_ERROR',sid,type(exc).__name__,str(exc)[:500],flush=True)

        try:
            return fallback(a)
        except RuntimeError as exc:
            old=str(exc)
            # Effect prefabs are frequently particle/material graphs with no standalone mesh.
            # Translate the old strict-name mismatch into the correct semantic result instead of
            # surfacing a scary, misleading assembly failure in the viewer.
            if 'RUNTIME_3D_OBJECT_MISMATCH' in old and _looks_effect_prefab(a):
                reason=exact_reason or old
                print('V34_PTR3D_NONAUTONOMOUS',sid,'effect-prefab-legacy-mismatch',flush=True)
                raise _no_standalone(sid,reason) from exc
            raise

    core.build_model=build
    print('V34_PTR3D_FAST_INSTALLED fast=6xdepth1/16meshes deep=16xdepth3/32meshes no-mesh-legacy-guess=OFF cache='+model_cache.name,flush=True)
    return build
