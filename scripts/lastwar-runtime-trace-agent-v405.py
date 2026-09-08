#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.5 — exact runtime dependency/call-path tracer.

The tracer does not guess visual dependencies.  It joins already-proven Unity relations and CLR
call evidence with the catalogue's physical bundle provenance so one asset can be followed from
GameObject/script -> serialized prefab path -> stable id -> bundle/fragment/APK -> render cache.
Code strings are exposed separately as literals/candidates unless an exact serialized relation
proves them.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, re

EXACT = re.compile(r'^LWGA-[A-Z0-9]+$', re.I)
PATHISH = re.compile(r'(Assets/|AssetBundles/|\.prefab\b|\.mat\b|\.anim\b|\.controller\b|\.png\b|\.tga\b|\.dds\b)', re.I)
LOADISH = re.compile(r'(LoadAsset|LoadPrefab|LoadAsync|AssetBundle|ResourceManager|Addressable|Instantiate)', re.I)
CACHE_ROOT = Path.home()/'.cache/wfgg-lastwar-v31'
MODEL_ROOTS = [
    CACHE_ROOT/'models-v33-ptr-3402', CACHE_ROOT/'models-v33-ptr-3401', CACHE_ROOT/'models-v33-exact',
    CACHE_ROOT/'models-v33-mobile-3306', CACHE_ROOT/'models-v33'
]
CAT_FIELDS = (
    'stable_id','asset_path','logical_name','alias_name','bundle_id','offset_bytes','span_bytes',
    'fragment_entry','table_fragment','render_availability','render_source_reason','dimension_class',
    'model_role','tech_kind','asset_folder'
)


def _row(core,sid):
    con=core.dbcon()
    try:
        r=con.execute('SELECT * FROM assets WHERE stable_id=?',(sid,)).fetchone()
        return dict(r) if r else None
    finally: con.close()


def _physical(reason):
    s=str(reason or '')
    d={'raw':s or None}
    # Current V39.7 proof format: ...:apk:<name>:assets/AssetBundles/BundleFragmentN.bytes:offset=N:span=N:proof=...
    m=re.search(r':apk:([^:]+):(assets/AssetBundles/[^:]+)(?::offset=(-?\d+))?(?::span=(-?\d+))?',s,re.I)
    if m:
        d.update({'apkName':m.group(1),'apkEntry':m.group(2),'offset':int(m.group(3)) if m.group(3) else None,
                  'span':int(m.group(4)) if m.group(4) else None})
    p=re.search(r':proof=([^:]+)',s,re.I)
    if p:d['proof']=p.group(1)
    return d


def _asset(core,sid):
    r=_row(core,sid)
    if not r:return {'stableId':sid,'missing':True}
    out={k:r.get(k) for k in CAT_FIELDS if k in r}
    out['stableId']=sid;out['physicalSource']=_physical(r.get('render_source_reason'))
    return out


def _manifest(sid):
    hits=[]
    for root in MODEL_ROOTS:
        p=root/sid/'manifest.json'
        if not p.is_file():continue
        try:
            m=json.loads(p.read_text('utf-8'))
            hits.append({
                'cache':root.name,'schemaVersion':m.get('schemaVersion'),'assemblyMode':m.get('assemblyMode'),
                'objects':len(m.get('objects') or []),'bundleIds':m.get('bundleIds') or [],
                'bundleSources':m.get('bundleSources') or m.get('textureBundleSources') or [],
                'textureBindingStatus':m.get('textureBindingStatus'),
                'textureBindingCount':int(m.get('textureBindingCount') or 0),
                'textureFileCount':int(m.get('textureFileCount') or 0),
                'textureBindingErrors':(m.get('textureBindingErrors') or [])[:12],
                'textureGraphNodes':m.get('textureGraphNodes'),'textureRootAnchor':m.get('textureRootAnchor'),
                'path':str(p)
            })
        except Exception as exc:
            hits.append({'cache':root.name,'error':type(exc).__name__+': '+str(exc)[:180],'path':str(p)})
    return hits


def _runtime_relations(graph,core):
    out=[];seen=set()
    for x in graph.get('runtimePrefabs',{}).get('items') or []:
        b=x.get('best') or {};sid=str(b.get('stable_id') or '').upper()
        if not EXACT.fullmatch(sid):continue
        key=(str(x.get('nodePath') or ''),sid,str(x.get('variant') or ''))
        if key in seen:continue
        seen.add(key)
        out.append({
            'nodePath':x.get('nodePath'),'variant':x.get('variant'),'stableId':sid,
            'assetPath':b.get('asset_path'),'exactName':bool(b.get('exactName')),'exactPath':bool(b.get('exactPath')),
            'renderAvailability':b.get('render_availability'),'catalog':_asset(core,sid),'renderCaches':_manifest(sid),
            'proof':'serialized SoftReferencePrefab + exact name/path catalogue resolution'
        })
    return out


def _code_calls(graph):
    calls=[];literals=[];seen_call=set();seen_lit=set()
    for block in graph.get('recursiveCodeEvidence') or []:
        cls=block.get('className');go=block.get('gameObject');asset=block.get('asset')
        for s in block.get('signals') or []:
            call=str(s.get('call') or '')
            if LOADISH.search(call):
                k=(asset,cls,go,s.get('callChain'),call)
                if k not in seen_call:
                    seen_call.add(k);calls.append({
                        'asset':asset,'className':cls,'gameObject':go,'phase':s.get('phase'),
                        'callChain':s.get('callChain'),'apiCall':call,'fields':(s.get('fields') or [])[:16],
                        'proof':'validated CLR metadata token/call chain'
                    })
            for raw in s.get('strings') or []:
                val=str(raw or '').strip()
                if not val or not PATHISH.search(val):continue
                k=(asset,cls,val)
                if k in seen_lit:continue
                seen_lit.add(k);literals.append({
                    'asset':asset,'className':cls,'gameObject':go,'value':val,'sourceMethod':s.get('callChain'),
                    'proof':'CLR user-string literal; not promoted to an exact dependency without serialized/catalogue proof'
                })
    return calls[:120],literals[:160]


def _motion(graph):
    rows=[]
    for m in graph.get('motionRecipe') or []:
        if not m.get('continuous'):continue
        e=m.get('evidence') or {}
        rows.append({
            'type':m.get('type'),'confidence':m.get('confidence'),'phase':m.get('phase'),
            'asset':e.get('asset'),'className':e.get('className'),'gameObject':e.get('gameObject'),
            'method':e.get('method'),'apiCall':e.get('call'),'seedMethod':e.get('seedMethod'),
            'fields':e.get('fields') or [],'strings':e.get('strings') or [],
            'targetProof':'CLR call proven; exact target Transform/axis/speed remain unresolved unless separately serialized'
        })
    return rows


def build_trace(stable_id,core,agent402,v3915,force=False):
    sid=str(stable_id or '').strip().upper()
    if not EXACT.fullmatch(sid):raise ValueError('invalid-stable-id')
    root_asset=_asset(core,sid)
    if root_asset.get('missing'):raise KeyError(sid)
    graph=agent402.build_graph(sid,v3915,force=force)
    root=str(graph.get('rootPrefab') or sid).upper()
    root_info=_asset(core,root)
    relations=_runtime_relations(graph,core)
    calls,literals=_code_calls(graph)
    motion=_motion(graph)
    assets=[];seen=set()
    for x in [root_info]+[r['catalog'] for r in relations]:
        k=x.get('stableId')
        if not k or k in seen:continue
        seen.add(k);y=dict(x);y['renderCaches']=_manifest(k);assets.append(y)
    exact_textures=sum(sum(int(c.get('textureBindingCount') or 0) for c in a.get('renderCaches') or []) for a in assets)
    texture_status=[]
    for a in assets:
        for c in a.get('renderCaches') or []:
            texture_status.append({'stableId':a.get('stableId'),'cache':c.get('cache'),'status':c.get('textureBindingStatus'),
                                   'count':c.get('textureBindingCount',0),'errors':c.get('textureBindingErrors') or []})
    unresolved=[]
    if exact_textures==0:
        unresolved.append({'kind':'textures','reason':'no exact Material->Texture2D binding is present in the current model caches',
                           'next':'re-run material closure from the exact physical bundle chain before rendering'})
    ma=graph.get('motionAnalysis') or {}
    if ma.get('continuousCount') and motion:
        unresolved.append({'kind':'animation-playback','reason':'continuous CLR motion is proven, but target Transform + axis + speed are not all proven yet',
                           'next':'trace serialized fields/constants for the proven rotation call chain'})
    return {
        'version':'40.5','stableId':sid,'rootPrefab':root,'createdAt':datetime.now(timezone.utc).isoformat(),
        'rootAsset':root_asset,'rootPrefabAsset':root_info,'assets':assets,'runtimeRelations':relations,
        'loaderCalls':calls,'codePathLiterals':literals,'continuousMotion':motion,'textureDiagnostics':texture_status,
        'summary':{
            'exactRuntimeRelations':len(relations),'cataloguedAssets':len(assets),'loaderCallChains':len(calls),
            'pathLiterals':len(literals),'continuousMotionChains':len(motion),'exactTextureBindingsInCache':exact_textures,
            'physicalSourcesProven':sum(1 for a in assets if (a.get('physicalSource') or {}).get('apkEntry'))
        },
        'unresolved':unresolved,
        'policy':'Serialized Unity relations/catalogue IDs/fragment offsets and validated CLR calls are exact evidence. CLR literals are candidates until joined to a serialized/catalogue relation. No visual similarity or synthetic dependency is used.'
    }
