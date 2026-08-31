#!/data/data/com.termux/files/usr/bin/python
from pathlib import Path
from collections import Counter
import contextlib, json, platform, re, site, sys, traceback

ROOT=Path(sys.argv[1]).resolve()
V8=ROOT/'frontend/lab/master-assets-v2/meta/audie-mesh-external-v8.json'
OUT=ROOT/'frontend/lab/audie-mesh-carrier-v6-data'
MAN=OUT/'manifest.json'
JSONOUT=ROOT/'frontend/lab/master-assets-v2/meta/audie-mesh-android-v9.json'
if not V8.is_file(): raise SystemExit('ERREUR: V8 absent: '+str(V8))

# Termux reports Android to Python. Some UnityPy/dependency paths reject it even
# though the Unity assets themselves are Android assets. For parsing only, expose
# the host as Linux; the serialized file target platform is left untouched.
_real_platform_system=platform.system
platform.system=lambda: 'Linux'

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'
try:
    from UnityPy.export.MeshExporter import export_mesh_obj
except Exception:
    export_mesh_obj=None

v8=json.loads(V8.read_text('utf-8'))
old={}
if MAN.is_file():
    try: old=json.loads(MAN.read_text('utf-8'))
    except Exception: old={}
textures=old.get('textures') or []
OUT.mkdir(parents=True,exist_ok=True)
meshdir=OUT/'meshes'; meshdir.mkdir(parents=True,exist_ok=True)
for p in meshdir.glob('v9_*.obj'):
    try:p.unlink()
    except:pass

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def sfname(o):
    af=getattr(o,'assets_file',None)
    return str(getattr(af,'name','') or getattr(af,'file_name','') or '')
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:110] or 'asset'

def export_via_object(o):
    errs=[]
    for check in (False,True):
        try:
            m=o.parse_as_object(check_read=check)
            if export_mesh_obj:
                t=export_mesh_obj(m)
                if isinstance(t,bytes): t=t.decode('utf-8','replace')
                if isinstance(t,str) and ('\nv ' in '\n'+t): return t,f'parse_as_object(check_read={check})+MeshExporter'
            ex=getattr(m,'export',None)
            if callable(ex):
                t=ex()
                if isinstance(t,bytes): t=t.decode('utf-8','replace')
                if isinstance(t,str) and ('\nv ' in '\n'+t): return t,f'parse_as_object(check_read={check})+.export'
            errs.append(f'parse_as_object({check}): no OBJ')
        except Exception as e:
            errs.append(f'parse_as_object({check}):{type(e).__name__}:{e}')
    raise RuntimeError(' | '.join(errs))

def raw_typetree_probe(o):
    # This is deliberately diagnostic first: if the generic TypeTree reader works,
    # record the geometry-bearing fields without inventing a mesh.
    try:
        d=o.read_typetree(wrap=False,check_read=False)
    except Exception as e:
        return None,f'{type(e).__name__}:{e}'
    if not isinstance(d,dict): return None,'typetree-not-dict'
    vd=d.get('m_VertexData') or {}
    sm=d.get('m_SubMeshes') or []
    ib=d.get('m_IndexBuffer')
    stream=d.get('m_StreamData') or {}
    def blen(x):
        try:return len(x)
        except:return 0
    info={
      'name':d.get('m_Name',''),
      'vertexCount':int((vd or {}).get('m_VertexCount') or 0) if isinstance(vd,dict) else 0,
      'channelCount':len((vd or {}).get('m_Channels') or []) if isinstance(vd,dict) else 0,
      'vertexDataBytes':blen((vd or {}).get('m_DataSize')) if isinstance(vd,dict) else 0,
      'indexBytes':blen(ib),
      'subMeshes':len(sm),
      'streamPath':(stream or {}).get('path','') if isinstance(stream,dict) else '',
      'streamSize':int((stream or {}).get('size') or 0) if isinstance(stream,dict) else 0,
    }
    return info,''

def source_grep():
    hits=[]
    roots=[]
    try: roots += [Path(x) for x in site.getsitepackages()]
    except: pass
    try: roots.append(Path(site.getusersitepackages()))
    except: pass
    seen=set()
    for base in roots:
        if not base.exists():continue
        for p in base.rglob('*.py'):
            if p in seen:continue
            seen.add(p)
            try: txt=p.read_text('utf-8',errors='ignore')
            except:continue
            if 'Unsupported system' not in txt:continue
            for n,line in enumerate(txt.splitlines(),1):
                if 'Unsupported system' in line:
                    hits.append({'path':str(p),'line':n,'text':line.strip()[:300]})
                    if len(hits)>=40:return hits
    return hits

# Use the exact objects V8 already resolved. No global rescan.
resolved=(v8.get('diagnostics') or {}).get('resolvedPointers') or []
targets=[];seen=set()
for r in resolved:
    if str(r.get('resolvedType') or '')!='Mesh':continue
    rp=str(r.get('resolvedPath') or '')
    sn=str(r.get('targetSerialized') or '').lower()
    mp=str(r.get('meshPathID') or '')
    if not rp or not mp:continue
    k=(rp,sn,mp)
    if k in seen:continue
    seen.add(k);targets.append({'path':rp,'serialized':sn,'pathID':mp,'rendererReferenced':True,'source':r})

# Also include exact serialized hits from V8, but only the Audie mesh family.
for sn,arr in ((v8.get('diagnostics') or {}).get('serializedHits') or {}).items():
    if 'audie' not in str(sn).lower() or 'mesh' not in str(sn).lower():continue
    for h in arr or []:
        rp=str(h.get('path') or '')
        if not rp:continue
        # pathIDs for this CAB come from V8 pointers targeting this serialized name
        pids={str(x.get('meshPathID')) for x in ((v8.get('diagnostics') or {}).get('externalMeshPointers') or []) if str(x.get('targetSerialized') or '').lower()==str(sn).lower() and x.get('meshPathID')}
        for mp in pids:
            k=(rp,str(sn).lower(),mp)
            if k in seen:continue
            seen.add(k);targets.append({'path':rp,'serialized':str(sn).lower(),'pathID':mp,'rendererReferenced':True,'source':{}})

print('AUDIE_MESH_ANDROID_V9_START',f'targets={len(targets)}',f'hostReported={_real_platform_system()}',f'hostShim={platform.system()}',flush=True)
meshes=[]; diagnostics=[]; bundle_cache={}
for i,t in enumerate(targets,1):
    p=Path(t['path']); sn=t['serialized']; mp=int(t['pathID'])
    print('V9_TARGET',f'{i}/{len(targets)}',p.name,sn,'p'+str(mp),flush=True)
    if not p.is_file():
        diagnostics.append({**t,'status':'missing-bundle'});continue
    key=str(p)
    if key not in bundle_cache:
        try: bundle_cache[key]=(UnityPy.load(str(p)),None)
        except Exception as e: bundle_cache[key]=(None,f'{type(e).__name__}:{e}')
    env,loaderr=bundle_cache[key]
    if env is None:
        diagnostics.append({**t,'status':'load-fail','error':loaderr});continue
    objs=[o for o in env.objects if typ(o)=='Mesh' and sfname(o).lower()==sn and pid(o)==mp]
    if not objs:
        diagnostics.append({**t,'status':'object-not-found'});continue
    o=objs[0]
    rawinfo,rawerr=raw_typetree_probe(o)
    try:
        text,method=export_via_object(o)
        fn=f'v9_{safe(p.name)}_p{mp}_{safe(pname(o) or "Mesh")}.obj'
        fp=meshdir/fn; fp.write_text(text,'utf-8',newline='')
        rec={'bundle':p.name,'bundlePath':str(p),'category':'android-shim-exact','pathID':str(mp),'serializedFile':sn,'name':pname(o) or ('Mesh_'+str(mp)),'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size,'rendererReferenced':True,'exportMethod':method,'rawProbe':rawinfo}
        meshes.append(rec)
        diagnostics.append({**t,'status':'exported','method':method,'rawProbe':rawinfo})
        print('V9_MESH_OK',p.name,'p'+str(mp),rec['name'],'bytes='+str(fp.stat().st_size),'method='+method,flush=True)
    except Exception as e:
        tb=''.join(traceback.format_exception(type(e),e,e.__traceback__))[-8000:]
        diagnostics.append({**t,'status':'export-fail','error':f'{type(e).__name__}:{e}','traceback':tb,'rawProbe':rawinfo,'rawProbeError':rawerr})
        print('V9_MESH_FAIL',p.name,'p'+str(mp),f'{type(e).__name__}:{e}'[:700],flush=True)
        if rawinfo: print('V9_RAW_TYPETREE_OK',json.dumps(rawinfo,ensure_ascii=False),flush=True)
        elif rawerr: print('V9_RAW_TYPETREE_FAIL',rawerr[:700],flush=True)

# If exact pointers yielded nothing, try every Mesh in the exact Audie mesh CABs,
# still without leaving the already-resolved V8 bundle set.
if not meshes:
    cab_pairs={(str(t['path']),t['serialized']) for t in targets if 'audie' in t['serialized'] and 'mesh' in t['serialized']}
    for rp,sn in sorted(cab_pairs):
        env,loaderr=bundle_cache.get(rp,(None,None))
        if env is None:
            try: env=UnityPy.load(rp); bundle_cache[rp]=(env,None)
            except: continue
        for o in env.objects:
            if typ(o)!='Mesh' or sfname(o).lower()!=sn:continue
            if any(m['bundlePath']==rp and m['pathID']==str(pid(o)) for m in meshes):continue
            rawinfo,rawerr=raw_typetree_probe(o)
            try:
                text,method=export_via_object(o)
                fn=f'v9fallback_{safe(Path(rp).name)}_p{pid(o)}_{safe(pname(o) or "Mesh")}.obj'
                fp=meshdir/fn; fp.write_text(text,'utf-8',newline='')
                meshes.append({'bundle':Path(rp).name,'bundlePath':rp,'category':'android-shim-cab-fallback','pathID':str(pid(o)),'serializedFile':sn,'name':pname(o) or ('Mesh_'+str(pid(o))),'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size,'rendererReferenced':False,'exportMethod':method,'rawProbe':rawinfo})
                print('V9_FALLBACK_OK',Path(rp).name,'p'+str(pid(o)),pname(o),'bytes='+str(fp.stat().st_size),flush=True)
            except Exception as e:
                diagnostics.append({'path':rp,'serialized':sn,'pathID':str(pid(o)),'status':'fallback-fail','error':f'{type(e).__name__}:{e}','rawProbe':rawinfo,'rawProbeError':rawerr})

source_hits=[] if meshes else source_grep()
if source_hits:
    print('V9_UNSUPPORTED_SYSTEM_SOURCE_HITS',len(source_hits),flush=True)
    for h in source_hits[:12]: print('V9_SOURCE_HIT',h['path'],h['line'],h['text'],flush=True)

# Rebuild carrier list around exact geometry bundles.
carriers=[]
for rp in sorted({m['bundlePath'] for m in meshes} | {t['path'] for t in targets}):
    p=Path(rp)
    ms=[m for m in meshes if m['bundlePath']==rp]
    carriers.append({'basename':p.name,'path':rp,'category':'v9-android-mesh-target','meshCount':len(ms),'rendererReferencedMeshes':sum(1 for m in ms if m['rendererReferenced']),'counts':{'Mesh':len(ms)}})

if meshes: verdict='ANDROID_MESH_EXPORTED_V9'
elif any(d.get('rawProbe') for d in diagnostics): verdict='RAW_TYPETREE_VISIBLE_EXPORT_BLOCKED_V9'
else: verdict='ANDROID_MESH_PARSE_STILL_BLOCKED_V9'
manifest={
 'format':'WFGG_LASTWAR_AUDIE_MESH_ANDROID_V9','verdict':verdict,
 'counts':{'carriers':len(carriers),'sourceCarriers':len(targets),'meshPointers':len(targets),'uniqueMeshPointers':len(targets),'targetSerializedFiles':len({t['serialized'] for t in targets}),'matchedGeometryBundles':len({t['path'] for t in targets}),'meshes':len(meshes),'rendererReferencedMeshes':sum(1 for m in meshes if m['rendererReferenced']),'textures':len(textures),'unresolvedPointers':sum(1 for d in diagnostics if d.get('status')!='exported')},
 'carriers':carriers,'meshes':meshes,'textures':textures,
 'diagnostics':{'hostReal':_real_platform_system(),'hostShim':platform.system(),'targets':targets,'attempts':diagnostics,'unsupportedSystemSourceHits':source_hits},
 'rules':['V9 does not rescan the 2778 bundles; it consumes exact mesh bundle/CAB/pathID targets already found by V8.','The Termux host platform is shimmed from Android to Linux only for Python dependency compatibility; Unity SerializedFile target_platform is not modified.','Meshes are accepted only when a real OBJ with vertex records is exported from the exact Unity Mesh object.','Raw TypeTree probes are diagnostic evidence only and are never rendered as invented geometry.']
}
MAN.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
JSONOUT.parent.mkdir(parents=True,exist_ok=True); JSONOUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_MESH_ANDROID_V9_READY',f'verdict={verdict}',f'meshes={len(meshes)}',f'targets={len(targets)}',f'rawTypetree={sum(1 for d in diagnostics if d.get("rawProbe"))}',flush=True)
print('JSON='+str(JSONOUT),flush=True)
print('MANIFEST='+str(MAN),flush=True)
