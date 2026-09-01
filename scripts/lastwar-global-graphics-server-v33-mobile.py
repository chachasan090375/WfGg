#!/usr/bin/env python3
from __future__ import annotations

"""Mobile runtime for the V33 LAB.

Keeps exact-only rendering, but separates two budgets:
- 3D preview: deliberately small to stay interactive on Android;
- 2D Sprite resolution: deeper exact dependency closure to recover backing textures.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
import importlib.util, shutil, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
UNIFIED=ROOT/'scripts/lastwar-global-graphics-server-v33-unified.py'
CACHE=Path.home()/'.cache/wfgg-lastwar-v31'


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

u=load_module('wfgg_v33_unified_mobile',UNIFIED)
core=u.core
exact=u.exact

# -------- 3D: mobile preview budget --------
# build_model_exact reads these globals at request time.  Keep only enough exact bundles
# to create an interactive preview; the catalogue retains the complete dependency graph.
ORIGINAL_DEPENDENCY_ROWS=exact.dependency_rows
exact.MAX_DEP_BUNDLES=10
exact.MAX_MESHES=12
exact.MAX_TEXTURES=18
exact.MODEL_CACHE=CACHE/'models-v33-mobile-3304'
exact.MODEL_CACHE.mkdir(parents=True,exist_ok=True)


def mobile_dependency_rows(a,max_bundles=10,max_depth=2):
    return ORIGINAL_DEPENDENCY_ROWS(a,max_bundles=min(int(max_bundles or 10),10),max_depth=min(int(max_depth or 2),2))

exact.dependency_rows=mobile_dependency_rows
core.build_model=exact.build_model_exact

# -------- 2D: deeper exact closure, independent of the 3D cap --------
# Sprite PPtrs can point several dependency hops away.  We still accept exact dependency
# edges only; candidate/name-similarity edges remain excluded.
MOBILE_CLOSURE=CACHE/'closure-v33-mobile'
MOBILE_CLOSURE.mkdir(parents=True,exist_ok=True)


def materialize_raster_closure(a,max_deps=28):
    sid=a['stable_id'];base=MOBILE_CLOSURE/sid
    if base.exists():shutil.rmtree(base,ignore_errors=True)
    base.mkdir(parents=True,exist_ok=True)
    rows=[a]+ORIGINAL_DEPENDENCY_ROWS(a,max_bundles=max_deps,max_depth=3)
    seen=set();paths=[];sources=[]
    for row in rows:
        try:bid=int(row.get('bundle_id'))
        except Exception:continue
        if bid in seen:continue
        seen.add(bid)
        try:src,source=core.v31.materialize_bundle(row)
        except Exception as exc:
            sources.append({'bundleId':bid,'ok':False,'error':str(exc)[:220]});continue
        dst=base/f'bundle-{bid}.bundle'
        try:shutil.copy2(src,dst)
        except Exception as exc:
            sources.append({'bundleId':bid,'ok':False,'error':'copy:'+str(exc)[:220]});continue
        paths.append(dst)
        sources.append({'bundleId':bid,'ok':True,'source':source,'dependencyDepth':row.get('_dependency_depth',0)})
    return paths,sources

u._materialize_closure=materialize_raster_closure
# render_asset_unified resolves _materialize_closure dynamically from module globals.
core.v31.render_asset=u.render_asset_unified

if __name__=='__main__':
    con=core.dbcon();edges=con.execute('SELECT count(*) FROM bundle_dependencies_v33').fetchone()[0];con.close()
    url=f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — MOBILE EXACT ===',flush=True)
    print('V33_3D_MOBILE bundles=10 meshes=12 textures=18 cache=models-v33-mobile-3304',flush=True)
    print('V33_2D_EXACT_CLOSURE dependencies<=28 depth<=3 candidates=EXCLUDED',flush=True)
    print('V33_EXACT_DEP_EDGES',edges,flush=True)
    print(url,flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),core.Handler).serve_forever()
