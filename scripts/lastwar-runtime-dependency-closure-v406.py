#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.6 — targeted exact Unity dependency closure for materials/textures.

This pass is deliberately narrow: root prefab + exact local WORK/IDLE children by default.
It expands only proven bundle dependency edges, rematerializes the exact Unity closure, then reruns
V35 Material -> Texture2D PPtr enrichment. It never uses filename similarity or synthetic textures.
"""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json, re, shutil, threading

HERE=Path(__file__).resolve().parent
V35_PATH=HERE/'lastwar-global-graphics-material-texture-v35.py'
PTR_CACHE=Path.home()/'.cache/wfgg-lastwar-v31'/'models-v33-ptr-3402'
STAGES=((48,3),(96,5),(160,7))
LOCK=threading.RLock()
EXACT=re.compile(r'^LWGA-[A-Z0-9]+$',re.I)
STALE_FIELDS={
    'textureBindingsSchema','textureBindings','materialTextures','objectTextures','textureFiles',
    'textureBindingStatus','textureBindingCount','textureFileCount','textureBindingErrors',
    'textureBundleSources','textureGraphNodes','textureRootAnchor','textureBindingSource'
}


def _load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v35=_load('wfgg_v35_for_v406',V35_PATH)


def _row(core,sid):
    con=core.dbcon()
    try:
        r=con.execute('SELECT * FROM assets WHERE stable_id=?',(sid,)).fetchone()
        if not r:return None
        try:return core.rowdict(r)
        except Exception:return dict(r)
    finally:con.close()


def _physical_row(con,core,bid):
    r=con.execute("""
      SELECT * FROM assets
      WHERE bundle_id=? AND render_availability IN ('local-exact','local-resolved')
      ORDER BY CASE render_availability WHEN 'local-exact' THEN 0 ELSE 1 END,
               CASE WHEN offset_bytes>=0 AND span_bytes>0 THEN 0 ELSE 1 END,row_no LIMIT 1
    """,(bid,)).fetchone()
    if not r:return None
    try:return core.rowdict(r)
    except Exception:return dict(r)


def dependency_rows(core,a,max_bundles=48,max_depth=3):
    """Exact BFS over bundle_dependencies_v33; same direction as the V33 exact pipeline."""
    try:start=int(a.get('bundle_id'))
    except Exception:return []
    con=core.dbcon();out=[];seen={start};frontier=[start]
    try:
        for depth in range(max_depth):
            nxt=[]
            for src in frontier:
                try:rows=con.execute('SELECT target_bundle_id FROM bundle_dependencies_v33 WHERE source_bundle_id=? ORDER BY ordinal',(src,))
                except Exception:return out
                for r in rows:
                    bid=int(r[0])
                    if bid in seen:continue
                    seen.add(bid);nxt.append(bid)
                    row=_physical_row(con,core,bid)
                    if row:
                        row['_dependency_depth']=depth+1;row['_dependency_from']=src;out.append(row)
                        if len(out)>=max_bundles:break
                if len(out)>=max_bundles:break
            if len(out)>=max_bundles or not nxt:break
            frontier=nxt
    finally:con.close()
    def rank(x):
        t=' '.join(str(x.get(k) or '').lower() for k in ('logical_name','asset_path','alias_name'))
        if 'material' in t:return 0
        if 'texture' in t:return 1
        if 'mesh' in t:return 2
        if 'prefab' in t:return 3
        if 'animation' in t or 'animator' in t:return 4
        return 5
    out.sort(key=lambda x:(rank(x),x.get('_dependency_depth',99),x.get('bundle_id',999999)))
    return out[:max_bundles]


def _manifest_path(sid):return PTR_CACHE/sid/'manifest.json'


def _ensure_manifest(core,a):
    sid=a['stable_id'];mp=_manifest_path(sid)
    if mp.is_file():
        try:
            m=json.loads(mp.read_text('utf-8'))
            if m.get('objects'):return m,mp,'existing-ptr-cache'
        except Exception:pass
    # The currently installed core builder is still the exact V34/V35 chain. Ask it once, then
    # require the canonical PTR cache; do not manufacture a replacement manifest here.
    try:core.build_model(a)
    except Exception:pass
    if mp.is_file():
        m=json.loads(mp.read_text('utf-8'))
        if m.get('objects'):return m,mp,'core-build-model'
    return None,mp,'ptr-manifest-unavailable'


def _reset_texture_fields(sid,m):
    d=dict(m);outdir=PTR_CACHE/sid
    old=[]
    for f in d.get('files') or []:
        if not isinstance(f,dict):continue
        p=str(f.get('path') or '')
        if p.startswith('texture-ptr-'):
            old.append(p)
    for p in old:
        try:(outdir/p).unlink(missing_ok=True)
        except Exception:pass
    d['files']=[f for f in (d.get('files') or []) if not (isinstance(f,dict) and str(f.get('path') or '').startswith('texture-ptr-'))]
    for k in STALE_FIELDS:d.pop(k,None)
    return d,old


def _target_ids(trace_data,scope):
    root=str(trace_data.get('rootPrefab') or trace_data.get('stableId') or '').upper()
    out=[];seen=set()
    def add(sid,role,node=''):
        sid=str(sid or '').upper()
        if not EXACT.fullmatch(sid) or sid in seen:return
        seen.add(sid);out.append({'stableId':sid,'role':role,'nodePath':node})
    add(root,'root')
    rels=trace_data.get('runtimeRelations') or []
    if scope=='all':
        for x in rels:add(x.get('stableId'),str(x.get('variant') or 'runtime').lower(),str(x.get('nodePath') or ''))
    else:
        for wanted in ('work','idle'):
            for x in rels:
                if wanted in str(x.get('variant') or '').lower():
                    add(x.get('stableId'),wanted,str(x.get('nodePath') or ''));break
    return out


def _source_summary(m):
    xs=m.get('textureBundleSources') or []
    return {
        'discovered':len(xs),
        'materialized':sum(1 for x in xs if x.get('ok')),
        'failed':sum(1 for x in xs if not x.get('ok')),
        'bundleIds':[x.get('bundleId') for x in xs if x.get('ok')][:180],
        'failures':[{'bundleId':x.get('bundleId'),'error':x.get('error')} for x in xs if not x.get('ok')][:20],
    }


def _run_asset(core,target,force=True):
    sid=target['stableId'];a=_row(core,sid)
    if not a:return {**target,'ok':False,'error':'catalogue-row-missing'}
    manifest,mp,origin=_ensure_manifest(core,a)
    if not manifest:return {**target,'ok':False,'error':'ptr-manifest-unavailable','manifestPath':str(mp)}
    start_count=int(manifest.get('textureBindingCount') or 0)
    if start_count>0 and not force:
        return {**target,'ok':True,'cacheHit':True,'manifestOrigin':origin,'bindingCount':start_count,
                'textureFileCount':int(manifest.get('textureFileCount') or 0),'status':manifest.get('textureBindingStatus'),
                'stage':None,'sources':_source_summary(manifest),'errors':manifest.get('textureBindingErrors') or []}

    attempts=[];best=manifest;best_count=start_count;removed=[]
    for bundles,depth in STAGES:
        clean,old=_reset_texture_fields(sid,best);removed.extend(old)
        try:mp.write_text(json.dumps(clean,ensure_ascii=False,indent=2),'utf-8')
        except Exception:pass
        shutil.rmtree(PTR_CACHE/'closure'/sid,ignore_errors=True)
        v35.p.MAX_DEP_BUNDLES=bundles;v35.p.MAX_DEPTH=depth;v35.MAX_TEXTURES=max(128,min(256,bundles*2))
        def deps(row,max_bundles=bundles,max_depth=depth):
            return dependency_rows(core,row,max_bundles=bundles,max_depth=depth)
        try:
            enriched=v35.enrich_manifest(a,clean,core,PTR_CACHE,deps)
        except Exception as exc:
            attempts.append({'bundles':bundles,'depth':depth,'ok':False,'error':type(exc).__name__+': '+str(exc)[:300]})
            continue
        count=int(enriched.get('textureBindingCount') or 0);files=int(enriched.get('textureFileCount') or 0)
        src=_source_summary(enriched)
        attempts.append({'bundles':bundles,'depth':depth,'ok':True,'status':enriched.get('textureBindingStatus'),
                         'bindings':count,'textureFiles':files,**src})
        best=enriched
        if count>=best_count:best_count=count
        if count>0:break
    try:mp.write_text(json.dumps(best,ensure_ascii=False,indent=2),'utf-8')
    except Exception:pass
    final_sources=_source_summary(best)
    return {**target,'ok':True,'cacheHit':False,'manifestOrigin':origin,'bindingCount':int(best.get('textureBindingCount') or 0),
            'textureFileCount':int(best.get('textureFileCount') or 0),'status':best.get('textureBindingStatus'),
            'stage':attempts[-1] if attempts else None,'attempts':attempts,'sources':final_sources,
            'errors':(best.get('textureBindingErrors') or [])[:40],'oldTextureFilesCleared':len(set(removed)),
            'manifestPath':str(mp)}


def build_closure(stable_id,core,trace_agent,agent402,v3915,scope='primary',force=True):
    sid=str(stable_id or '').strip().upper()
    if not EXACT.fullmatch(sid):raise ValueError('invalid-stable-id')
    scope='all' if str(scope).lower()=='all' else 'primary'
    with LOCK:
        trace_data=trace_agent.build_trace(sid,core,agent402,v3915,force=False)
        targets=_target_ids(trace_data,scope)
        results=[_run_asset(core,t,force=force) for t in targets]
    total_bind=sum(int(x.get('bindingCount') or 0) for x in results)
    total_files=sum(int(x.get('textureFileCount') or 0) for x in results)
    mats=sum(int((x.get('sources') or {}).get('materialized') or 0) for x in results)
    unresolved=[]
    for x in results:
        if not x.get('ok'):
            unresolved.append({'stableId':x.get('stableId'),'kind':'asset','reason':x.get('error')})
        elif not x.get('bindingCount'):
            unresolved.append({'stableId':x.get('stableId'),'kind':'Material->Texture2D',
                               'reason':x.get('status') or 'no exact texture PPtr resolved',
                               'errors':(x.get('errors') or [])[:8]})
    return {
        'version':'40.6','stableId':sid,'rootPrefab':trace_data.get('rootPrefab'),'scope':scope,
        'createdAt':datetime.now(timezone.utc).isoformat(),'targets':targets,'results':results,
        'summary':{'assetsScanned':len(results),'bundleFilesMaterialized':mats,'exactTextureBindings':total_bind,
                   'textureFilesExported':total_files,'unresolvedAssets':len(unresolved)},
        'unresolved':unresolved,
        'policy':'Exact catalogue rows + bundle_dependencies_v33 + Unity serialized PPtrs only. Staged closure 48/3 -> 96/5 -> 160/7; stop at first exact Material->Texture2D binding. No visual guessing; no synthetic geometry/texture/animation.',
        'renderHint':'When exact bindings are recovered, rerun the existing V40.4 WORK/IDLE assembly; it consumes objectTextures from the refreshed PTR manifests.'
    }
