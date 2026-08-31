#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
OUTDIR="$ROOT/frontend/lab/formation-lua-trace-viewer-data"
MANIFEST="$OUTDIR/manifest.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LWLUA_CONTAINER_IL_TRACE_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$OUTDIR"
python - "$ROOT" "$META" "$OUTDIR" "$MANIFEST" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import json, os, re, sys, zipfile, hashlib
root, meta, outdir, manifest, report = map(Path, sys.argv[1:])

nodes={}
edges=[]
evidence=[]
containers=[]
scripts=[]
previews=[]

COLORS={
 'ui':'UI / prefab','runtime':'Runtime','lua':'Lua','code':'C# / XLua','asset':'Asset','render':'Render','container':'Conteneur','unknown':'Autre'
}

def add_node(nid,label,kind='unknown',**extra):
    if nid in nodes:
        nodes[nid].update({k:v for k,v in extra.items() if v not in (None,'',[],{})})
        return nodes[nid]
    n={'id':nid,'label':label,'kind':kind}
    n.update(extra); nodes[nid]=n; return n

def add_edge(src,dst,relation,proof='derived',confidence='derived',evidence_text=None,source=None,**extra):
    if not src or not dst: return
    key=(src,dst,relation,proof,source or '')
    for e in edges:
        if (e['source'],e['target'],e['relation'],e.get('proof'),e.get('sourceFile',''))==key:
            return
    e={'id':f'e{len(edges)+1}','source':src,'target':dst,'relation':relation,'proof':proof,'confidence':confidence}
    if source: e['sourceFile']=source
    e.update(extra)
    if evidence_text:
        eid=f'ev{len(evidence)+1}'
        evidence.append({'id':eid,'edgeId':e['id'],'text':evidence_text,'source':source or ''})
        e['evidenceId']=eid
    edges.append(e)

# Canonical anchors already proven by previous passes.
add_node('ui:UIHeroPVPFormationPanel','UIHeroPVPFormationPanel','ui',bundleId=6933,assetPath='Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab')
add_node('ui:FormationRT','FormationRT','render',bundleId=6933,subtype='RawImage',note='RawImage prefab; m_Texture=0')
add_node('ui:FormationBg','FormationBg','ui',bundleId=6933)
add_node('ui:SlotAreas','SlotAreas','ui',bundleId=6933)
add_node('ui:HeroInfoBars','HeroInfoBars','ui',bundleId=6933)
add_node('render:RenderTexture','RenderTexture','render')
add_node('render:Camera','Camera','render')
add_node('asset:Murphy','Murphy / A_Hero_Audie_01','asset',prefabBundle=17859,meshBundle=26631,textureBundles=[26633,26634])
add_node('code:LuaUIFormLogic.LuaInit','LuaUIFormLogic.LuaInit','code')
add_node('code:XLuaManager.CustomLoaderImpl','XLuaManager.CustomLoaderImpl','code')
add_node('code:XLuaManager.Initialize','XLuaManager.Initialize','code')
add_node('code:LWLuaFile.Load','LWLuaFile.Load','code')
add_node('code:LWLuaFile.LoadFile','LWLuaFile.LoadFile','code')
add_node('code:RawImage.set_texture','XLua → RawImage.texture','runtime')
add_node('code:Camera.set_targetTexture','XLua → Camera.targetTexture','runtime')

add_edge('ui:UIHeroPVPFormationPanel','ui:FormationRT','contains','serialized','exact','FormationRT est un GameObject du prefab UIHeroPVPFormationPanel','bundle 6933')
add_edge('ui:UIHeroPVPFormationPanel','ui:FormationBg','contains','serialized','exact','FormationBg est un GameObject du prefab UIHeroPVPFormationPanel','bundle 6933')
add_edge('ui:FormationRT','code:RawImage.set_texture','runtime assignment boundary','serialized+wrapper','high','FormationRT porte un RawImage dont m_Texture est nul dans le prefab; l’affectation se fait au runtime.','formation-rt-trace-v1')
add_edge('render:Camera','code:Camera.set_targetTexture','runtime setter boundary','wrapper','high','Le wrapper XLua expose Camera.set_targetTexture.','formation-murphy-trace-graph-v1')
add_edge('code:XLuaManager.Initialize','code:LWLuaFile.Load','calls','MethodDef','exact','XLuaManager.Initialize appelle LWLuaFile.Load.','formation-lua-source-container-crosswalk-v1')
add_edge('code:XLuaManager.CustomLoaderImpl','code:LWLuaFile.LoadFile','calls','MethodDef','exact','CustomLoaderImpl délègue le chargement à LWLuaFile.LoadFile.','formation-dynamic-binding-bridge-v1')
add_edge('code:LuaUIFormLogic.LuaInit','code:XLuaManager.CustomLoaderImpl','Lua runtime boundary','runtime','high','LuaUIFormLogic exécute le code Lua via XLua; les modules sont fournis par CustomLoaderImpl.','formation-dynamic-binding-bridge-v1')

# Load known trace graph, if present, for bridge-method evidence.
graphp=meta/'formation-murphy-trace-graph-v1.json'
if graphp.exists():
    try:
        g=json.loads(graphp.read_text('utf-8'))
        for r in (g.get('topBridgeMethods') or [])[:80]:
            sym=r.get('symbol') or r.get('name')
            if not sym: continue
            nid='code:'+sym
            add_node(nid,sym,'code',score=r.get('score'),calls=r.get('calls') or r.get('externalCalls') or [])
            calls=' '.join(map(str,r.get('calls') or r.get('externalCalls') or [])).lower()
            if 'rawimage.set_texture' in calls:
                add_edge(nid,'code:RawImage.set_texture','calls setter','MethodDef/external','high',sym+' appelle RawImage.set_texture',graphp.name)
            if 'camera.set_targettexture' in calls:
                add_edge(nid,'code:Camera.set_targetTexture','calls setter','MethodDef/external','high',sym+' appelle Camera.set_targetTexture',graphp.name)
    except Exception:
        pass

# Parse IL trace report: literals, local files, APK entry names.
if report.exists():
    txt=report.read_text('utf-8',errors='replace')
    for line in txt.splitlines():
        if line.startswith('LITERAL '):
            val=line[8:].strip().strip('"\'')
            nid='literal:'+hashlib.sha1(val.encode()).hexdigest()[:12]
            add_node(nid,val,'container',subtype='literal')
            add_edge('code:LWLuaFile.LoadFile',nid,'uses literal','IL ldstr','exact',line,report.name)
        elif line.startswith('FILE '):
            p=line[5:].strip(); pp=Path(p)
            nid='container:'+hashlib.sha1(p.encode()).hexdigest()[:12]
            add_node(nid,pp.name,'container',path=p,exists=pp.exists(),size=(pp.stat().st_size if pp.exists() else None))
            containers.append({'id':nid,'path':p,'kind':'local-file'})
            add_edge('code:LWLuaFile.LoadFile',nid,'candidate container','name match','candidate',line,report.name)
        elif line.startswith('APKENTRY '):
            val=line[9:].strip(); nid='container:'+hashlib.sha1(val.encode()).hexdigest()[:12]
            add_node(nid,val,'container',subtype='apk-entry')
            containers.append({'id':nid,'path':val,'kind':'apk-entry'})
            add_edge('code:LWLuaFile.LoadFile',nid,'candidate APK entry','entry-name','candidate',line,report.name)

# Also add literal candidates from the JSON generated by the IL trace.
ilp=meta/'lwlua-container-il-trace-v1.json'
if ilp.exists():
    try:
        d=json.loads(ilp.read_text('utf-8'))
        for r in d.get('exactBoundaryMethodIL') or []:
            sym=r.get('symbol')
            if not sym: continue
            sid='code:'+sym; add_node(sid,sym,'code')
            for s in r.get('strings') or []:
                if not isinstance(s,str) or not s.strip(): continue
                if any(k in s.lower() for k in ('lua','script','zip','bytes','data','file')) or '/' in s or '\\' in s or '.' in s:
                    nid='literal:'+hashlib.sha1(s.encode()).hexdigest()[:12]
                    add_node(nid,s,'container',subtype='IL literal')
                    add_edge(sid,nid,'IL literal','IL ldstr','exact',repr(s),ilp.name)
    except Exception: pass

# Inspect candidate ZIPs and script directories only. No broad content scan.
script_sources=[]
for c in list(containers):
    p=Path(c['path'])
    if not p.exists() or not p.is_file(): continue
    try:
        with p.open('rb') as f: sig=f.read(4)
    except: continue
    if sig[:2]==b'PK':
        try:
            with zipfile.ZipFile(p) as z:
                c['archive']='zip'; c['entries']=len(z.infolist())
                for zi in z.infolist():
                    low=zi.filename.lower()
                    if zi.is_dir() or zi.file_size>3*1024*1024: continue
                    if low.endswith(('.lua','.luac','.txt','.bytes')) or 'lua' in low:
                        try: raw=z.read(zi)
                        except: continue
                        # Only parse text-like payloads here; binary Lua stays listed but not guessed.
                        nul=raw[:4096].count(b'\0')
                        if nul>32: 
                            scripts.append({'name':zi.filename,'container':str(p),'binary':True,'bytes':len(raw)})
                            continue
                        text=raw.decode('utf-8','replace')
                        script_sources.append((f'{p}!{zi.filename}',zi.filename,text))
        except Exception as e:
            c['zipError']=f'{type(e).__name__}: {e}'

# Optional user/runtime extraction directory, if created later by a dedicated extractor.
for canddir in [Path.home()/'storage'/'downloads'/'WFGG_LASTWAR_LUA_EXTRACTED', root/'frontend'/'lab'/'master-assets-v2'/'runtime-lua']:
    if not canddir.exists() or not canddir.is_dir(): continue
    did='container:'+hashlib.sha1(str(canddir).encode()).hexdigest()[:12]
    add_node(did,canddir.name,'container',path=str(canddir),subtype='directory')
    containers.append({'id':did,'path':str(canddir),'kind':'directory'})
    for p in canddir.rglob('*'):
        if p.is_file() and p.stat().st_size<=3*1024*1024 and p.suffix.lower() in ('.lua','.txt','.bytes'):
            try: raw=p.read_bytes()
            except: continue
            if raw[:4096].count(b'\0')>32: continue
            script_sources.append((str(p),str(p.relative_to(canddir)),raw.decode('utf-8','replace')))

# Lua/text relation extractor.
REQ=re.compile(r'\b(?:require|dofile|loadfile)\s*\(?\s*["\']([^"\']+)["\']',re.I)
ASSET=re.compile(r'["\'](Assets/[A-Za-z0-9_./ -]+)["\']')
ANCHORS={
 'formationrt':'ui:FormationRT','formationbg':'ui:FormationBg','uiheropvpformationpanel':'ui:UIHeroPVPFormationPanel',
 'a_hero_audie_01':'asset:Murphy','renders?texture':'render:RenderTexture','targettexture':'code:Camera.set_targetTexture',
 'rawimage':'code:RawImage.set_texture'
}
script_id_by_name={}
for source,name,text in script_sources:
    sid='lua:'+hashlib.sha1(source.encode()).hexdigest()[:16]
    script_id_by_name[name.replace('\\','/').lower()]=sid
    add_node(sid,name,'lua',source=source)
    lines=text.splitlines()
    hits=[]
    for i,line in enumerate(lines,1):
        ll=line.lower()
        if any(k in ll for k in ('formation','hero','rendertexture','targettexture','rawimage','camera','a_hero_audie_01')):
            hits.append({'line':i,'text':line[:300]})
    scripts.append({'id':sid,'name':name,'source':source,'lines':len(lines),'hits':hits[:100]})
    for m in REQ.finditer(text):
        mod=m.group(1); tid='lua-module:'+mod.lower().replace('\\','/').replace('.','/')
        add_node(tid,mod,'lua',subtype='module-ref')
        line=text.count('\n',0,m.start())+1
        add_edge(sid,tid,'require/load','Lua text','exact',f'line {line}: {m.group(0)[:220]}',source)
    for m in ASSET.finditer(text):
        ap=m.group(1); aid='assetpath:'+hashlib.sha1(ap.encode()).hexdigest()[:16]
        add_node(aid,ap,'asset',assetPath=ap)
        line=text.count('\n',0,m.start())+1
        add_edge(sid,aid,'asset path literal','Lua text','exact',f'line {line}: {m.group(0)[:220]}',source)
    for pat,target in ANCHORS.items():
        rx=re.compile(pat,re.I)
        for m in list(rx.finditer(text))[:30]:
            line=text.count('\n',0,m.start())+1
            snippet=lines[line-1].strip()[:280] if 0<line<=len(lines) else m.group(0)
            add_edge(sid,target,'mentions / manipulates','Lua text','exact',f'line {line}: {snippet}',source)

# Resolve module references to concrete script nodes when names match.
for e in list(edges):
    if not e['target'].startswith('lua-module:'): continue
    mod=e['target'][11:]
    cands=[mod+'.lua',mod.replace('.','/')+'.lua',mod]
    for c in cands:
        for n,sid in script_id_by_name.items():
            if n.endswith(c.lower()):
                add_edge(e['source'],sid,'require resolves to','name resolution','high',f'{mod} → {n}',e.get('sourceFile'))
                break

# Reuse actual visual previews from the existing bundle viewer manifest.
bmv=root/'frontend'/'lab'/'formation-bridge-bundle-viewer-data'/'manifest.json'
if bmv.exists():
    try:
        bm=json.loads(bmv.read_text('utf-8'))
        for b in bm.get('bundles') or []:
            role=str(b.get('role','')).lower()
            for t in b.get('textures') or []:
                name=str(t.get('name') or '')
                if 'audie' in name.lower() or 'murphy' in role:
                    src=t.get('src')
                    if src:
                        previews.append({'nodeId':'asset:Murphy','src':src,'name':name,'bundleId':b.get('bundleId')})
    except Exception: pass

# Compute adjacency, connectedness, shortest paths between FormationRT and Murphy.
adj=defaultdict(set)
for e in edges:
    adj[e['source']].add(e['target']); adj[e['target']].add(e['source'])
def shortest(a,b):
    q=deque([a]); prev={a:None}
    while q:
        x=q.popleft()
        if x==b: break
        for y in adj.get(x,()):
            if y not in prev: prev[y]=x; q.append(y)
    if b not in prev: return []
    p=[]; cur=b
    while cur is not None: p.append(cur); cur=prev[cur]
    return p[::-1]
path=shortest('ui:FormationRT','asset:Murphy')

# Rank nodes around our two anchors using degree + keyword relevance.
for n in nodes.values():
    deg=len(adj.get(n['id'],()))
    text=(n.get('label','')+' '+str(n.get('source',''))).lower()
    rel=sum(1 for k in ('formation','hero','murphy','audie','render','camera','lua') if k in text)
    n['degree']=deg; n['score']=deg*3+rel*8

result={
 'format':'WFGG_LASTWAR_FORMATION_LUA_TRACE_VIEWER_V1',
 'generatedFrom':{
   'ilTrace':str(ilp) if ilp.exists() else None,
   'report':str(report) if report.exists() else None,
   'traceGraph':str(graphp) if graphp.exists() else None,
   'bundleViewer':str(bmv) if bmv.exists() else None,
 },
 'summary':{
   'nodes':len(nodes),'edges':len(edges),'evidence':len(evidence),'containers':len(containers),'scripts':len(scripts),
   'shortestFormationMurphyHops':(len(path)-1 if path else None),
   'luaSourcesParsed':len(script_sources),
 },
 'anchors':['ui:FormationRT','ui:UIHeroPVPFormationPanel','asset:Murphy','code:LWLuaFile.LoadFile'],
 'shortestFormationMurphyPath':path,
 'nodes':sorted(nodes.values(),key=lambda n:(-n.get('score',0),n['kind'],n['label'])),
 'edges':edges,'evidence':evidence,'containers':containers,'scripts':scripts,'previews':previews,
 'guardrails':{'labOnly':True,'mainUntouched':True,'noBroadBundleScan':True,'noInventedRelations':True,'proofVisible':True}
}
manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_LUA_TRACE_VIEWER_V1_READY nodes={len(nodes)} edges={len(edges)} evidence={len(evidence)} containers={len(containers)} scripts={len(scripts)} parsedLua={len(script_sources)}")
print(f"MANIFEST={manifest}")
if path: print('PATH='+' -> '.join(nodes[x]['label'] for x in path))
else: print('PATH=NONE_DYNAMIC_LUA_CONTAINER_REQUIRED')
PY
