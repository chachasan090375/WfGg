#!/data/data/com.termux/files/usr/bin/python
from pathlib import Path
from collections import defaultdict, Counter
import json,re,sys
import UnityPy

ROOT=Path(sys.argv[1]).resolve()
V5=ROOT/'frontend/lab/master-assets-v2/meta/audie-package-family-v5.json'
OUT=ROOT/'frontend/lab/audie-mesh-carrier-v6-data'
MAN=OUT/'manifest.json'
JSONOUT=ROOT/'frontend/lab/master-assets-v2/meta/audie-mesh-external-v8.json'
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'

if not V5.is_file(): raise SystemExit('ERREUR: V5 absent: '+str(V5))
v5=json.loads(V5.read_text('utf-8'))
source_carriers=v5.get('meshCarriers') or []
if not source_carriers: raise SystemExit('ERREUR: aucun carrier V5')

OUT.mkdir(parents=True,exist_ok=True)
meshdir=OUT/'meshes'; meshdir.mkdir(parents=True,exist_ok=True)
for p in meshdir.glob('*.obj'):
    try:p.unlink()
    except:pass

old={}
if MAN.is_file():
    try: old=json.loads(MAN.read_text('utf-8'))
    except: old={}
textures=old.get('textures') or []

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def sfname(o):
    af=getattr(o,'assets_file',None)
    return str(getattr(af,'name','') or getattr(af,'file_name','') or '')
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:110] or 'asset'
def norm_external(s):
    z=str(s or '').replace('\\','/')
    if z.lower().startswith('archive:/'): z=z[9:]
    if z.lower().startswith('assets/'): z=z[7:]
    return z.rsplit('/',1)[-1].lower()
def pptr_vals(q):
    if q is None:return None
    try:
        return int(getattr(q,'m_FileID',getattr(q,'file_id',0)) or 0), int(getattr(q,'m_PathID',getattr(q,'path_id',0)) or 0)
    except:return None

def parse(o):
    errs=[]
    for m in ('parse_as_object','read'):
        f=getattr(o,m,None)
        if not callable(f): continue
        try:return f(),m
        except Exception as e: errs.append(f'{m}:{type(e).__name__}:{e}')
    raise RuntimeError(' | '.join(errs))

def mesh_ptr(o):
    try:d,_=parse(o)
    except Exception:return None
    for a in ('m_Mesh','mesh'):
        q=getattr(d,a,None)
        pv=pptr_vals(q)
        if pv and pv[1]: return q,pv
    return None

def external_name(reader,fileid):
    if fileid<=0:return sfname(reader)
    af=getattr(reader,'assets_file',None)
    exts=list(getattr(af,'externals',[]) or [])
    i=fileid-1
    if 0<=i<len(exts): return str(getattr(exts[i],'path','') or '')
    return ''

def export_mesh(o):
    errs=[]
    for m in ('parse_as_object','read'):
        f=getattr(o,m,None)
        if not callable(f):continue
        try:
            x=f(); ex=getattr(x,'export',None)
            if not callable(ex): errs.append(m+':export unavailable'); continue
            t=ex()
            if isinstance(t,bytes):t=t.decode('utf-8','replace')
            if isinstance(t,str) and (t.startswith('v ') or '\nv ' in '\n'+t): return t,m+'.export'
            errs.append(m+':no OBJ vertices')
        except Exception as e: errs.append(f'{m}:{type(e).__name__}:{e}')
    raise RuntimeError(' | '.join(errs))

print('AUDIE_MESH_EXTERNAL_V8_START carriers='+str(len(source_carriers)),flush=True)
refs=[]; carrier_diag=[]
for ci,rec in enumerate(source_carriers,1):
    p=Path(str(rec.get('path') or ''))
    if not p.is_file():
        carrier_diag.append({'bundle':p.name,'error':'missing'});continue
    try:
        env=UnityPy.load(str(p)); objs=list(env.objects)
    except Exception as e:
        carrier_diag.append({'bundle':p.name,'error':f'{type(e).__name__}:{e}'});continue
    counts=Counter(typ(o) for o in objs)
    local_meshes=sum(1 for o in objs if typ(o)=='Mesh')
    ptrn=0
    for o in objs:
        if typ(o) not in ('MeshFilter','SkinnedMeshRenderer'):continue
        got=mesh_ptr(o)
        if not got:continue
        q,(fid,mpid)=got; ptrn+=1
        ext=external_name(o,fid)
        target=norm_external(ext) if fid>0 else sfname(o).lower()
        r={'sourceBundle':p.name,'sourcePath':str(p),'sourceSerialized':sfname(o),'sourceType':typ(o),'sourcePathID':str(pid(o)),'fileID':fid,'meshPathID':str(mpid),'externalPath':ext,'targetSerialized':target,'external':fid>0}
        refs.append(r)
        print('V8_MESH_PTR',p.name,typ(o),'p'+str(pid(o)),'fileID='+str(fid),'meshPathID='+str(mpid),'target='+target,flush=True)
    carrier_diag.append({'bundle':p.name,'counts':dict(counts),'localMeshes':local_meshes,'meshPointers':ptrn})

# de-duplicate exact pointers while retaining every source observation
uniq={}
for r in refs:
    k=(r['targetSerialized'].lower(),r['meshPathID'])
    uniq.setdefault(k,r)
target_names={k[0] for k in uniq if k[0]}
print('V8_POINTER_SUMMARY',f'raw={len(refs)}',f'unique={len(uniq)}',f'targetSerialized={len(target_names)}',flush=True)

# Physical bundle catalogue, same roots as V5.
roots=[ROOT/'frontend/lab/local_assets',Path.home()/'.cache']
paths=[];seen=set()
for base in roots:
    if not base.exists():continue
    for p in base.rglob('*.bundle'):
        try:k=str(p.resolve())
        except:k=str(p)
        if k in seen:continue
        seen.add(k);paths.append(p)
paths.sort(key=lambda p:p.name.lower())

resolved=[]; scan_errors=[]; serial_hits=defaultdict(list); geometry_bundles={}
print('V8_CATALOG_SCAN_START bundles='+str(len(paths)),flush=True)
for i,p in enumerate(paths,1):
    if i==1 or i%50==0: print('V8_CATALOG_SCAN',f'{i}/{len(paths)}',p.name,flush=True)
    try: env=UnityPy.load(str(p)); objs=list(env.objects)
    except Exception as e:
        if len(scan_errors)<100: scan_errors.append({'bundle':p.name,'error':f'{type(e).__name__}:{e}'})
        continue
    # Only inspect bundles containing one of the exact serialized filenames targeted by PPtrs.
    names={sfname(o).lower() for o in objs if sfname(o)}
    matched=names & target_names
    if not matched:continue
    geometry_bundles[str(p)]={'basename':p.name,'path':str(p),'matchedSerialized':sorted(matched),'meshCount':0,'resolvedCount':0,'counts':dict(Counter(typ(o) for o in objs))}
    print('V8_SERIALIZED_HIT',p.name,','.join(sorted(matched)),flush=True)
    for o in objs:
        sn=sfname(o).lower()
        if sn not in matched:continue
        serial_hits[sn].append({'bundle':p.name,'path':str(p)})
        key=(sn,str(pid(o)))
        ref=uniq.get(key)
        if not ref:continue
        rr=dict(ref); rr.update({'resolvedBundle':p.name,'resolvedPath':str(p),'resolvedType':typ(o),'resolvedName':pname(o)})
        if typ(o)=='Mesh':
            try:
                text,method=export_mesh(o)
                fn=f'v8_{safe(p.name)}_p{pid(o)}_{safe(pname(o) or "Mesh")}.obj'
                fp=meshdir/fn; fp.write_text(text,'utf-8',newline='')
                rr.update({'exported':True,'exportMethod':method,'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size})
                geometry_bundles[str(p)]['meshCount']+=1; geometry_bundles[str(p)]['resolvedCount']+=1
                print('V8_MESH_RESOLVED',p.name,sn,'p'+str(pid(o)),pname(o),'bytes='+str(fp.stat().st_size),flush=True)
            except Exception as e:
                rr.update({'exported':False,'exportError':f'{type(e).__name__}:{e}'})
                print('V8_MESH_EXPORT_FAIL',p.name,'p'+str(pid(o)),rr['exportError'][:400],flush=True)
        else:
            rr.update({'exported':False,'resolveError':'target pathID exists but type='+typ(o)})
            print('V8_TARGET_TYPE_MISMATCH',p.name,sn,'p'+str(pid(o)),'type='+typ(o),flush=True)
        resolved.append(rr)

# Fallback: in any matched serialized file, export all Mesh objects even if exact pathID was not found.
exported_keys={(x.get('resolvedPath'),x.get('meshPathID')) for x in resolved if x.get('exported')}
meshes=[]
for x in resolved:
    if x.get('exported'):
        meshes.append({'bundle':x['resolvedBundle'],'bundlePath':x['resolvedPath'],'category':'external-mesh','pathID':x['meshPathID'],'serializedFile':x['targetSerialized'],'name':x.get('resolvedName') or ('Mesh_'+x['meshPathID']),'src':x['src'],'objBytes':x.get('objBytes',0),'rendererReferenced':True,'exportMethod':x.get('exportMethod','')})

# If a target CAB was found but exact pathID did not resolve, export every Mesh from that CAB as fallback candidates.
for gp,g in list(geometry_bundles.items()):
    try: env=UnityPy.load(gp); objs=list(env.objects)
    except: continue
    matched=set(g['matchedSerialized'])
    for o in objs:
        if typ(o)!='Mesh' or sfname(o).lower() not in matched:continue
        if any(m['bundlePath']==gp and m['pathID']==str(pid(o)) for m in meshes):continue
        try:
            text,method=export_mesh(o)
            fn=f'v8fallback_{safe(Path(gp).name)}_p{pid(o)}_{safe(pname(o) or "Mesh")}.obj'
            fp=meshdir/fn; fp.write_text(text,'utf-8',newline='')
            meshes.append({'bundle':Path(gp).name,'bundlePath':gp,'category':'external-cab-fallback','pathID':str(pid(o)),'serializedFile':sfname(o),'name':pname(o) or ('Mesh_'+str(pid(o))),'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size,'rendererReferenced':False,'exportMethod':method})
            geometry_bundles[gp]['meshCount']+=1
            print('V8_FALLBACK_MESH',Path(gp).name,sfname(o),'p'+str(pid(o)),pname(o),flush=True)
        except Exception as e:
            pass

# Put geometry bundles first so the existing 3D viewer selects useful content immediately.
carrier_out=[]
for gp,g in sorted(geometry_bundles.items(),key=lambda kv:(-kv[1]['meshCount'],kv[1]['basename'].lower())):
    carrier_out.append({'basename':g['basename'],'path':g['path'],'category':'resolved-geometry','meshCount':sum(1 for m in meshes if m['bundlePath']==g['path']),'rendererReferencedMeshes':sum(1 for m in meshes if m['bundlePath']==g['path'] and m['rendererReferenced']),'counts':g.get('counts',{}),'matchedSerialized':g.get('matchedSerialized',[])})
for d,src in zip(carrier_diag,source_carriers):
    carrier_out.append({'basename':d.get('bundle') or Path(str(src.get('path') or '')).name,'path':str(src.get('path') or ''),'category':'source-renderer','meshCount':d.get('localMeshes',0),'rendererReferencedMeshes':0,'counts':d.get('counts',{}),'meshPointers':d.get('meshPointers',0)})

unresolved=[]
resolved_keys={(x['targetSerialized'].lower(),x['meshPathID']) for x in resolved}
for k,r in uniq.items():
    if (k[0],k[1]) not in resolved_keys: unresolved.append(r)

if meshes: verdict='EXTERNAL_MESH_RESOLVED_V8'
elif target_names and any(serial_hits.values()): verdict='TARGET_CAB_FOUND_NO_MESH_AT_PTR_V8'
elif target_names: verdict='EXTERNAL_MESH_TARGETS_NOT_LOCAL_V8'
else: verdict='NO_MESH_PPTR_FOUND_V8'

manifest={
 'format':'WFGG_LASTWAR_AUDIE_MESH_EXTERNAL_V8','verdict':verdict,
 'counts':{'carriers':len(carrier_out),'sourceCarriers':len(source_carriers),'meshPointers':len(refs),'uniqueMeshPointers':len(uniq),'targetSerializedFiles':len(target_names),'matchedGeometryBundles':len(geometry_bundles),'meshes':len(meshes),'rendererReferencedMeshes':sum(1 for m in meshes if m['rendererReferenced']),'textures':len(textures),'unresolvedPointers':len(unresolved)},
 'carriers':carrier_out,'meshes':meshes,'textures':textures,
 'diagnostics':{'carrierDiagnostics':carrier_diag,'externalMeshPointers':refs,'resolvedPointers':resolved,'unresolvedPointers':unresolved,'serializedHits':dict(serial_hits),'scanErrors':scan_errors},
 'rules':['V8 follows MeshFilter/SkinnedMeshRenderer m_Mesh PPtrs instead of treating a renderer-only bundle as a local mesh carrier.','fileID > 0 is resolved through the source SerializedFile externals table to an exact target serialized filename.','A strong mesh match requires target serialized filename + exact pathID + Unity type Mesh.','Fallback meshes are exported only from the exact target serialized file and remain marked rendererReferenced=false.','No geometry is generated or approximated.']
}
MAN.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
JSONOUT.parent.mkdir(parents=True,exist_ok=True); JSONOUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_MESH_EXTERNAL_V8_READY',f'verdict={verdict}',f'ptrs={len(refs)}',f'targets={len(target_names)}',f'geometryBundles={len(geometry_bundles)}',f'meshes={len(meshes)}',f'unresolved={len(unresolved)}',flush=True)
for x in unresolved[:20]:print('V8_UNRESOLVED_SAMPLE',json.dumps(x,ensure_ascii=False),flush=True)
print('JSON='+str(JSONOUT),flush=True)
print('MANIFEST='+str(MAN),flush=True)
