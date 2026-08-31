#!/data/data/com.termux/files/usr/bin/python
from pathlib import Path
import json,re,sys,shutil
import UnityPy

ROOT=Path(sys.argv[1]).resolve()
V5=ROOT/'frontend/lab/master-assets-v2/meta/audie-package-family-v5.json'
OUT=ROOT/'frontend/lab/audie-mesh-carrier-v6-data'
MAN=OUT/'manifest.json'
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'

if not V5.is_file(): raise SystemExit('ERREUR: V5 absent: '+str(V5))
v5=json.loads(V5.read_text('utf-8'))
carriers=v5.get('meshCarriers') or []
if not carriers: raise SystemExit('ERREUR: aucun mesh carrier V5')
OUT.mkdir(parents=True,exist_ok=True)
meshdir=OUT/'meshes'; meshdir.mkdir(parents=True,exist_ok=True)
for p in meshdir.glob('*.obj'):
    try:p.unlink()
    except:pass

base_manifest={}
if MAN.is_file():
    try: base_manifest=json.loads(MAN.read_text('utf-8'))
    except: base_manifest={}

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:100] or 'asset'
def ser_name(o):
    for a in ('assets_file','serialized_file'):
        x=getattr(o,a,None)
        if x is not None:
            for b in ('name','file_name'):
                y=getattr(x,b,None)
                if y:return str(y)
    return ''
def pptr_info(v):
    if v is None:return None
    try:
        return {'fileID':int(getattr(v,'m_FileID',getattr(v,'file_id',0)) or 0),'pathID':str(int(getattr(v,'m_PathID',getattr(v,'path_id',0)) or 0))}
    except:return None

def parse_obj(reader):
    errs=[]
    for meth in ('parse_as_object','read'):
        fn=getattr(reader,meth,None)
        if not callable(fn):
            errs.append(meth+':unavailable'); continue
        try:return fn(),meth,errs
        except Exception as e:errs.append(f'{meth}:{type(e).__name__}:{e}')
    raise RuntimeError(' | '.join(errs))

def export_mesh_text(reader):
    errs=[]
    # Method A: current UnityPy API
    for meth in ('parse_as_object','read'):
        fn=getattr(reader,meth,None)
        if not callable(fn):
            errs.append(meth+':unavailable'); continue
        try:
            m=fn()
            ex=getattr(m,'export',None)
            if not callable(ex):
                errs.append(meth+':export-unavailable'); continue
            text=ex()
            if isinstance(text,bytes): text=text.decode('utf-8','replace')
            if isinstance(text,str) and ('\nv ' in ('\n'+text) or text.startswith('v ')):
                return text,meth+'.export',errs
            errs.append(meth+':empty-or-no-vertices')
        except Exception as e:
            errs.append(f'{meth}:{type(e).__name__}:{e}')
    # Method B: official UnityPy extractor helper
    try:
        from UnityPy.tools.extractor import export_obj
        tmp=OUT/'_v7_extract_tmp'; tmp.mkdir(parents=True,exist_ok=True)
        before={p.resolve() for p in tmp.rglob('*.obj')}
        export_obj(reader,str(tmp/'mesh'),append_name=True,append_path_id=True)
        after=[p for p in tmp.rglob('*.obj') if p.resolve() not in before]
        if after:
            text=max(after,key=lambda p:p.stat().st_size).read_text('utf-8',errors='replace')
            if text.strip(): return text,'UnityPy.tools.extractor.export_obj',errs
        errs.append('extractor:no-obj')
    except Exception as e:
        errs.append(f'extractor:{type(e).__name__}:{e}')
    raise RuntimeError(' | '.join(errs))

meshes=[]; errors=[]; carrier_out=[]
print('AUDIE_MESH_CARRIER_V7_START carriers='+str(len(carriers)),flush=True)
for ci,rec in enumerate(carriers,1):
    p=Path(str(rec.get('path') or ''))
    print('V7_CARRIER',f'{ci}/{len(carriers)}',p.name,flush=True)
    if not p.is_file():
        errors.append({'bundle':p.name,'stage':'load','error':'file missing'}); continue
    try:
        env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'bundle':p.name,'stage':'load','error':f'{type(e).__name__}:{e}'}); continue

    # Collect renderer->mesh PPtrs strictly by serialized file and local PPtr only.
    renderer_mesh_refs=[]
    for o in objs:
        if typ(o) not in ('MeshFilter','MeshRenderer','SkinnedMeshRenderer'): continue
        try:d,pm,_=parse_obj(o)
        except Exception:continue
        sf=ser_name(o)
        for attr in ('m_Mesh','mesh'):
            q=pptr_info(getattr(d,attr,None))
            if q and q['fileID']==0 and int(q['pathID']):
                renderer_mesh_refs.append((sf,q['pathID'],typ(o),str(pid(o))))
                break

    local_count=0; ref_count=0
    for o in objs:
        if typ(o)!='Mesh':continue
        n=pname(o) or ('Mesh_'+str(pid(o)))
        sf=ser_name(o)
        try:
            text,method,prior=export_mesh_text(o)
            fn=f'v7_c{ci:02d}_p{pid(o)}_{safe(n)}.obj'; fp=meshdir/fn
            fp.write_text(text,'utf-8',newline='')
            referenced=any(rsf==sf and rpid==str(pid(o)) for rsf,rpid,_,_ in renderer_mesh_refs)
            if referenced: ref_count+=1
            local_count+=1
            meshes.append({'carrierIndex':ci-1,'bundle':p.name,'bundlePath':str(p),'category':rec.get('category'),'pathID':str(pid(o)),'serializedFile':sf,'name':n,'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size,'rendererReferenced':referenced,'exportMethod':method,'priorErrors':prior})
            print('V7_MESH_OK',p.name,'p'+str(pid(o)),n,'method='+method,'bytes='+str(fp.stat().st_size),'ref='+str(referenced),flush=True)
        except Exception as e:
            err={'bundle':p.name,'pathID':str(pid(o)),'serializedFile':sf,'name':n,'stage':'mesh-export','error':f'{type(e).__name__}:{e}'}
            errors.append(err)
            print('V7_MESH_FAIL',p.name,'p'+str(pid(o)),n,err['error'][:500],flush=True)
    carrier_out.append({'basename':p.name,'path':str(p),'category':rec.get('category'),'meshCount':local_count,'rendererReferencedMeshes':ref_count,'sourceMeshCount':rec.get('meshCount',0)})

meshes.sort(key=lambda x:(not x['rendererReferenced'],x['bundle'].lower(),x['name'].lower(),int(x['pathID'])))
textures=base_manifest.get('textures') or []
verdict='MESHES_EXPORTED_V7' if meshes else 'MESH_EXPORT_FAILED_V7_WITH_DIAGNOSTICS'
manifest={
 'format':'WFGG_LASTWAR_AUDIE_MESH_CARRIER_V7',
 'verdict':verdict,
 'counts':{'carriers':len(carriers),'meshes':len(meshes),'rendererReferencedMeshes':sum(1 for x in meshes if x['rendererReferenced']),'textures':len(textures),'meshErrors':len(errors),'textureErrors':len((base_manifest.get('diagnostics') or {}).get('textureErrors',[]))},
 'carriers':carrier_out,'meshes':meshes,'textures':textures,
 'diagnostics':{'meshErrors':errors[:500],'textureErrors':(base_manifest.get('diagnostics') or {}).get('textureErrors',[])[:200]},
 'rules':[
   'V7 uses parse_as_object().export() first, matching current UnityPy API.',
   'If that fails it retries read().export(), then UnityPy.tools.extractor.export_obj.',
   'rendererReferenced is accepted only for local fileID=0 PPtrs in the same serialized file and pathID.',
   'No geometry is generated or approximated.'
 ]
}
MAN.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_MESH_CARRIER_V7_READY',f'verdict={verdict}',f'meshes={len(meshes)}',f'rendererReferenced={manifest["counts"]["rendererReferencedMeshes"]}',f'errors={len(errors)}',flush=True)
for e in errors[:20]:print('V7_ERROR_SAMPLE',json.dumps(e,ensure_ascii=False),flush=True)
print('JSON='+str(MAN),flush=True)
