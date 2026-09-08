#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.2 — lifecycle-aware recursive animation code analysis.

V40.2 keeps V40 exact Unity/CLR evidence, then follows validated MethodDef calls recursively from
Unity/game lifecycle methods. It separates continuous/frame-driven motion from initialization,
state changes and teardown. It also scans scripts on exact local WORK/IDLE/runtime child prefabs.
No synthetic motion, geometry or visual-similarity dependency is introduced.
"""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json, re, sqlite3, time

HERE=Path(__file__).resolve().parent
BASE=HERE/'lastwar-animation-graph-agent-v40.py'
spec=importlib.util.spec_from_file_location('wfgg_agent_v40_base_for_v402',BASE)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

CACHE_ROOT=Path.home()/'.cache/wfgg-lastwar-v402'
CACHE_ROOT.mkdir(parents=True,exist_ok=True)
CACHE_DB=CACHE_ROOT/'animation-agent-v402.sqlite3'

FRAME_RE=re.compile(r'^(Update|LateUpdate|FixedUpdate|OnAnimatorMove)$',re.I)
INIT_RE=re.compile(r'^(Awake|Start|OnEnable|OnSpawn|OnSpawnComplete|Init|Initialize|Setup|Create|Load|Bind)',re.I)
STATE_RE=re.compile(r'^(StartBuild|StopBuild|Set|Switch|Change|Refresh|Play|Pause|Resume|Open|Close|Show|Hide)',re.I)
TEARDOWN_RE=re.compile(r'^(OnDestroy|OnDisable|Dispose|Release|Unload|Clear)$',re.I)
COROUTINE_RE=re.compile(r'(MoveNext|Coroutine|Tween|Loop|Rotate|Spin|Tick)',re.I)


def _db():
    con=sqlite3.connect(CACHE_DB)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE IF NOT EXISTS graph_cache(stable_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,payload_json TEXT NOT NULL)')
    return con


def _phase(name:str):
    n=str(name or '')
    if FRAME_RE.search(n):return 'frame-loop'
    if INIT_RE.search(n):return 'initialization'
    if TEARDOWN_RE.search(n):return 'teardown'
    if STATE_RE.search(n):return 'state-event'
    if COROUTINE_RE.search(n):return 'runtime-loop-candidate'
    return 'event'


def _adjust_conf(kind,conf,phase):
    c=float(conf or 0)
    if phase=='frame-loop':return min(0.995,c)
    if phase=='runtime-loop-candidate':return min(0.94,c)
    if phase=='state-event':return min(0.86,c)
    if phase=='initialization':return min(0.72,c)
    if phase=='teardown':return min(0.30,c)
    return min(0.80,c)


def _motionish(kind):
    return kind in {'continuous-rotation','rotation-assignment','rotation-math','animator-state','legacy-animation','tween'}


def _related_types(index,cls):
    exact=index.find_types(cls)
    seen={t['rid'] for t in exact};out=list(exact)
    low=str(cls or '').casefold()
    if low:
        for t in index.types:
            full=str(t.get('full') or '').casefold()
            if t['rid'] in seen:continue
            if low in full and ('<' in full or '+' in full or 'd__' in full):
                seen.add(t['rid']);out.append(t)
            if len(out)>=16:break
    return out


def _analyze_script(index,script,asset_sid,max_depth=7,max_visits=220):
    cls=str(script.get('className') or script.get('scriptName') or '').strip()
    game=str(script.get('gameObject') or script.get('nodePath') or '')
    out={'className':cls,'gameObject':game,'asset':asset_sid,'signals':[],'methodsVisited':0,'types':[]}
    if not cls:return out
    types=_related_types(index,cls)
    methods={}
    for ty in types:
        out['types'].append(ty.get('full') or ty.get('name'))
        for m in ty.get('methods') or []:methods[m['rid']]=m
    if not methods:return out
    analyzed={}
    def ma(m):
        rid=m['rid']
        if rid not in analyzed:analyzed[rid]=index.analyze_method(m)
        return analyzed[rid]
    seeds=[]
    for m in methods.values():
        ph=_phase(m.get('name'))
        if ph!='event':seeds.append((m,ph))
    if not seeds:
        seeds=[(m,'event') for m in list(methods.values())[:80]]
    visited_global=set()
    records=[]
    for seed,seed_phase in seeds:
        stack=[(seed,0,[seed.get('name') or '?'])];seen=set()
        while stack and len(visited_global)<max_visits:
            m,depth,path=stack.pop();rid=m['rid']
            if (rid,depth) in seen or depth>max_depth:continue
            seen.add((rid,depth));visited_global.add(rid)
            info=ma(m)
            field_names=[str(f.get('full') or f.get('name') or '') for f in info.get('fields') or []]
            for call in info.get('calls') or []:
                kind,raw_conf=base._signal_from_call(call.get('full'))
                if kind:
                    conf=_adjust_conf(kind,raw_conf,seed_phase)
                    records.append({
                        'kind':kind,'confidence':conf,'rawConfidence':raw_conf,'phase':seed_phase,
                        'continuous':bool(_motionish(kind) and seed_phase in {'frame-loop','runtime-loop-candidate'}),
                        'seedMethod':seed.get('name'),'method':m.get('name'),'call':call.get('full'),
                        'callChain':' → '.join(path),'depth':depth,'className':cls,'gameObject':game,
                        'asset':asset_sid,'fields':field_names[:30],'strings':(info.get('strings') or [])[:24],
                        'token':call.get('token')
                    })
                if depth>=max_depth:continue
                if call.get('table')=='MethodDef':
                    try:crid=int(str(call.get('token') or '0'),16)&0x00ffffff
                    except Exception:crid=0
                    callee=index.methods[crid] if 0<crid<len(index.methods) else None
                    if callee and callee.get('rva'):
                        owner=str(callee.get('owner') or '')
                        # Follow game-code methods; stop at framework/Unity namespaces.
                        if not owner.startswith(('System.','UnityEngine.','Microsoft.')):
                            stack.append((callee,depth+1,path+[callee.get('name') or '?']))
    # Include direct signals in methods not reached from a known seed, but clearly mark them event-only.
    for m in methods.values():
        if m['rid'] in visited_global:continue
        info=ma(m)
        for call in info.get('calls') or []:
            kind,raw_conf=base._signal_from_call(call.get('full'))
            if kind:
                records.append({'kind':kind,'confidence':_adjust_conf(kind,raw_conf,'event'),'rawConfidence':raw_conf,
                    'phase':'event','continuous':False,'seedMethod':m.get('name'),'method':m.get('name'),'call':call.get('full'),
                    'callChain':m.get('name'),'depth':0,'className':cls,'gameObject':game,'asset':asset_sid,
                    'fields':[str(f.get('full') or f.get('name') or '') for f in (info.get('fields') or [])[:30]],
                    'strings':(info.get('strings') or [])[:24],'token':call.get('token')})
    # Deterministic dedupe and ranking.
    uniq=[];seen=set()
    phase_rank={'frame-loop':0,'runtime-loop-candidate':1,'state-event':2,'initialization':3,'event':4,'teardown':5}
    records.sort(key=lambda r:(not r['continuous'],phase_rank.get(r['phase'],9),-float(r['confidence']),r.get('callChain') or ''))
    for r in records:
        k=(r['kind'],r['phase'],r['callChain'],r['call'])
        if k in seen:continue
        seen.add(k);uniq.append(r)
    out['signals']=uniq[:160];out['methodsVisited']=len(visited_global)
    return out


def _script_stub(sc):
    return {'className':sc.get('className') or sc.get('scriptName'),'gameObject':sc.get('nodePath') or sc.get('gameObject')}


def build_graph(stable_id,v3915,force=False):
    sid=str(stable_id or '').strip().upper()
    if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid):raise ValueError('invalid-stable-id')
    if not force:
        con=_db();row=con.execute('SELECT payload_json FROM graph_cache WHERE stable_id=?',(sid,)).fetchone();con.close()
        if row:
            try:
                d=json.loads(row[0]);d['cacheHit']=True;return d
            except Exception:pass
    started=time.perf_counter()
    # Reuse V40 exact graph, but V40.2 owns its own cache/inference layer.
    payload=base.build_graph(sid,v3915,force=False)
    idx=base.clr_index(False)
    sources=[]
    for s in payload.get('scriptCodeEvidence') or []:
        sources.append((payload.get('rootPrefab') or sid,{'className':s.get('className'),'gameObject':s.get('gameObject')}))
    for csid,diag in (payload.get('childDiagnostics') or {}).items():
        if not isinstance(diag,dict):continue
        for sc in (diag.get('components',{}).get('scripts') or []):sources.append((csid,_script_stub(sc)))
    detailed=[]
    seen_scripts=set()
    for asset_sid,sc in sources:
        k=(asset_sid,str(sc.get('className')),str(sc.get('gameObject')))
        if k in seen_scripts:continue
        seen_scripts.add(k);detailed.append(_analyze_script(idx,sc,asset_sid))
    signals=[]
    for d in detailed:signals.extend(d.get('signals') or [])
    # Prefer proven continuous evidence, then runtime candidates/state/init. Keep strongest per kind/source/phase.
    signals.sort(key=lambda r:(not r.get('continuous'),-float(r.get('confidence') or 0),r.get('phase') or ''))
    refined=[];seen=set()
    for s in signals:
        k=(s.get('kind'),s.get('asset'),s.get('className'),s.get('phase'))
        if k in seen:continue
        seen.add(k)
        refined.append({'type':s.get('kind'),'confidence':s.get('confidence'),'phase':s.get('phase'),'continuous':s.get('continuous'),
            'evidence':{'method':s.get('callChain'),'call':s.get('call'),'className':s.get('className'),'gameObject':s.get('gameObject'),
                        'asset':s.get('asset'),'seedMethod':s.get('seedMethod'),'fields':s.get('fields'),'strings':s.get('strings')}})
        if len(refined)>=24:break
    continuous=[x for x in refined if x.get('continuous')]
    init=[x for x in refined if x.get('phase')=='initialization']
    state=[x for x in refined if x.get('phase')=='state-event']
    raw=payload.get('motionRecipe') or []
    payload['version']='40.2'
    payload['motionRecipeRawV40']=raw
    payload['motionRecipe']=refined or raw
    payload['recursiveCodeEvidence']=detailed
    payload['motionAnalysis']={
        'continuousCount':len(continuous),'initializationCount':len(init),'stateEventCount':len(state),
        'scriptsScanned':len(detailed),'methodsVisited':sum(int(x.get('methodsVisited') or 0) for x in detailed),
        'bestContinuous':continuous[0] if continuous else None,
        'status':'continuous-motion-proved' if continuous else ('initialization-or-state-only' if refined else 'no-motion-api-proved')
    }
    payload.setdefault('summary',{})['status']=payload['motionAnalysis']['status']
    payload['summary']['continuousMotionFound']=bool(continuous)
    payload['summary']['recursiveScriptsScanned']=len(detailed)
    payload['summary']['recursiveMethodsVisited']=payload['motionAnalysis']['methodsVisited']
    payload['policy']='V40.2 exact Unity relations + validated CLR tokens. Recursive game-code call graph is lifecycle-labelled; initialization/state/teardown are not promoted to continuous motion. No synthetic geometry/motion or visual-similarity runtime dependency.'
    payload['createdAtV402']=datetime.now(timezone.utc).isoformat()
    payload['scanSecondsV402']=round(time.perf_counter()-started,3)
    payload['cacheHit']=False
    con=_db();con.execute('INSERT OR REPLACE INTO graph_cache(stable_id,created_at,payload_json) VALUES(?,?,?)',(sid,payload['createdAtV402'],json.dumps(payload,ensure_ascii=False,separators=(',',':'))));con.commit();con.close()
    return payload


def cache_status():
    con=_db();n=con.execute('SELECT count(*) FROM graph_cache').fetchone()[0];con.close()
    return {'version':'40.2','cacheDb':str(CACHE_DB),'graphsCached':n,'baseAssemblyCached':base.ASSEMBLY_CACHE.exists()}
