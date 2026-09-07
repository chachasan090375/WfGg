#!/usr/bin/env python3
from __future__ import annotations

"""Fast staged wrapper for the exact PTR3D V34 assembler.

The first attempt keeps the Unity dependency closure deliberately small so common prefabs can
appear quickly on Android. Only if that exact PPtr walk cannot resolve the root/mesh graph do we
retry with the deeper V34 closure. The legacy strict-name renderer remains the final fallback.
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


def install(core,correlated,model_cache,dependency_rows):
    model_cache=Path(model_cache);model_cache.mkdir(parents=True,exist_ok=True)
    fallback=core.build_model
    failed=set()
    core.MODEL_CACHE=model_cache
    try:correlated.exact.MODEL_CACHE=model_cache
    except Exception:pass

    def build(a):
        sid=a['stable_id']
        if sid not in failed:
            try:
                m=_attempt(a,core,correlated,dependency_rows,model_cache,6,1,16,'fast-exact')
                print('V34_PTR3D_FAST_OK',sid,'meshes='+str(len(m.get('objects') or [])),'root='+str(m.get('rootGameObject') or ''),flush=True)
                return m
            except PtrGraphUnavailable as exc:
                print('V34_PTR3D_FAST_MISS',sid,str(exc)[:320],flush=True)
            except Exception as exc:
                print('V34_PTR3D_FAST_ERROR',sid,type(exc).__name__,str(exc)[:320],flush=True)

            try:
                m=_attempt(a,core,correlated,dependency_rows,model_cache,16,3,32,'deep-exact')
                print('V34_PTR3D_DEEP_OK',sid,'meshes='+str(len(m.get('objects') or [])),'root='+str(m.get('rootGameObject') or ''),flush=True)
                return m
            except PtrGraphUnavailable as exc:
                failed.add(sid);print('V34_PTR3D_FALLBACK',sid,str(exc)[:500],flush=True)
            except Exception as exc:
                failed.add(sid);print('V34_PTR3D_ERROR',sid,type(exc).__name__,str(exc)[:500],flush=True)
        return fallback(a)

    core.build_model=build
    print('V34_PTR3D_FAST_INSTALLED fast=6xdepth1/16meshes deep=16xdepth3/32meshes cache='+model_cache.name,flush=True)
    return build
