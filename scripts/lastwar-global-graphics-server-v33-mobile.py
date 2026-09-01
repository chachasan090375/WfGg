#!/usr/bin/env python3
from __future__ import annotations

"""Mobile runtime for the V33 LAB.

Keeps exact-only rendering, but separates two budgets:
- 3D preview: deliberately small to stay interactive on Android;
- 2D Sprite resolution: normal exact dependency closure first, then an adaptive deeper retry
  only when a Sprite backing Texture2D is still unresolved.

The LAB is an active development surface, so HTML/JS responses are explicitly no-store to
avoid Chrome keeping an older result-strip or renderer implementation after git pull.
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
# Keep the first preview responsive. The complete exact dependency graph remains in SQLite;
# this cap only limits how much geometry is assembled for one on-screen preview.
ORIGINAL_DEPENDENCY_ROWS=exact.dependency_rows
exact.MAX_DEP_BUNDLES=8
exact.MAX_MESHES=10
exact.MAX_TEXTURES=12
exact.MODEL_CACHE=CACHE/'models-v33-mobile-3306'
exact.MODEL_CACHE.mkdir(parents=True,exist_ok=True)


def mobile_dependency_rows(a,max_bundles=8,max_depth=2):
    return ORIGINAL_DEPENDENCY_ROWS(a,max_bundles=min(int(max_bundles or 8),8),max_depth=min(int(max_depth or 2),2))

exact.dependency_rows=mobile_dependency_rows
core.build_model=exact.build_model_exact

# -------- 2D: adaptive exact closure, independent of the 3D cap --------
# Most Sprite PPtrs resolve with <=28 exact dependency bundles. Some game scenes/UI prefabs
# reference a backing Texture2D farther away. Do not make every image pay that cost: retry only
# an unresolved Sprite with a larger exact-only BFS closure, preserving dependency ordinal order.
MOBILE_CLOSURE=CACHE/'closure-v33-mobile'
MOBILE_CLOSURE.mkdir(parents=True,exist_ok=True)
SHALLOW_RASTER_BUNDLES=28
SHALLOW_RASTER_DEPTH=3
DEEP_RASTER_BUNDLES=72
DEEP_RASTER_DEPTH=4
_DEEP_RASTER_IDS=set()


def raster_dependency_rows(a,max_bundles,max_depth):
    """Exact dependency BFS for raster PPtrs, preserving the TSV dependency order.

    The generic 3D helper deliberately re-ranks dependencies by likely geometry type. That is
    useful for a tiny 3D preview budget, but can evict a required Texture2D dependency. Raster
    resolution instead keeps the exact ordinal/BFS order and only filters out bundles that are
    not physically available on the phone.
    """
    try:start=int(a.get('bundle_id'))
    except Exception:return []
    con=core.dbcon();out=[];seen={start};frontier=[start]
    try:
        for depth in range(max_depth):
            nxt=[]
            for src in frontier:
                deps=list(con.execute(
                    'SELECT target_bundle_id FROM bundle_dependencies_v33 WHERE source_bundle_id=? ORDER BY ordinal',
                    (src,)
                ))
                for rec in deps:
                    bid=int(rec[0])
                    if bid in seen:continue
                    seen.add(bid);nxt.append(bid)
                    row=exact.physical_row_for_bundle(con,bid)
                    if row:
                        row['_dependency_depth']=depth+1;row['_dependency_from']=src;out.append(row)
                        if len(out)>=max_bundles:return out
            if not nxt:break
            frontier=nxt
        return out[:max_bundles]
    finally:
        con.close()


def materialize_raster_closure(a,max_deps=None):
    sid=a['stable_id'];deep=sid in _DEEP_RASTER_IDS
    dep_budget=DEEP_RASTER_BUNDLES if deep else SHALLOW_RASTER_BUNDLES
    depth_budget=DEEP_RASTER_DEPTH if deep else SHALLOW_RASTER_DEPTH
    if max_deps is not None:dep_budget=max(dep_budget,int(max_deps))
    base=MOBILE_CLOSURE/sid
    if base.exists():shutil.rmtree(base,ignore_errors=True)
    base.mkdir(parents=True,exist_ok=True)
    rows=[a]+raster_dependency_rows(a,dep_budget,depth_budget)
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
        sources.append({'bundleId':bid,'ok':True,'source':source,'dependencyDepth':row.get('_dependency_depth',0),'closureMode':'deep' if deep else 'shallow'})
    return paths,sources


u._materialize_closure=materialize_raster_closure
BASE_UNIFIED_RENDER=u.render_asset_unified


def render_asset_mobile_adaptive(a):
    """Fast exact closure first; one deeper exact-only retry for unresolved Sprite textures."""
    sid=a['stable_id']
    try:
        return BASE_UNIFIED_RENDER(a)
    except RuntimeError as exc:
        msg=str(exc)
        if 'RUNTIME_EXACT_RASTER_UNRESOLVED' not in msg or sid in _DEEP_RASTER_IDS:
            raise
        print('V33_2D_DEEP_RETRY',sid,f'bundles<={DEEP_RASTER_BUNDLES}',f'depth<={DEEP_RASTER_DEPTH}',flush=True)
        _DEEP_RASTER_IDS.add(sid)
        try:
            return BASE_UNIFIED_RENDER(a)
        finally:
            _DEEP_RASTER_IDS.discard(sid)


core.v31.render_asset=render_asset_mobile_adaptive


class MobileLabHandler(core.Handler):
    """Never let the phone keep stale LAB HTML/JS while V33 is being iterated."""
    def end_headers(self):
        self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma','no-cache')
        self.send_header('Expires','0')
        super().end_headers()


if __name__=='__main__':
    con=core.dbcon();edges=con.execute('SELECT count(*) FROM bundle_dependencies_v33').fetchone()[0];con.close()
    url=f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — MOBILE EXACT ===',flush=True)
    print('V33_3D_MOBILE bundles=8 meshes=10 textures=12 cache=models-v33-mobile-3306',flush=True)
    print(f'V33_2D_EXACT_CLOSURE shallow<={SHALLOW_RASTER_BUNDLES}/depth<={SHALLOW_RASTER_DEPTH} deep-retry<={DEEP_RASTER_BUNDLES}/depth<={DEEP_RASTER_DEPTH} candidates=EXCLUDED',flush=True)
    print('V33_2D_DEP_ORDER exact-ordinal-BFS=ON generic-3D-ranking=OFF',flush=True)
    print('V33_LAB_CACHE no-store=ON',flush=True)
    print('V33_EXACT_DEP_EDGES',edges,flush=True)
    print(url,flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),MobileLabHandler).serve_forever()
