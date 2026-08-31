#!/data/data/com.termux/files/usr/bin/python
from pathlib import Path
import json, math, re, struct, sys, traceback

ROOT=Path(sys.argv[1]).resolve()
V8=ROOT/'frontend/lab/master-assets-v2/meta/audie-mesh-external-v8.json'
V9=ROOT/'frontend/lab/master-assets-v2/meta/audie-mesh-android-v9.json'
OUT=ROOT/'frontend/lab/audie-mesh-carrier-v6-data'
MAN=OUT/'manifest.json'
JSONOUT=ROOT/'frontend/lab/master-assets-v2/meta/audie-mesh-raw-v10.json'
if not V8.is_file(): raise SystemExit('ERREUR: V8 absent: '+str(V8))

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'

OUT.mkdir(parents=True,exist_ok=True)
meshdir=OUT/'meshes'; meshdir.mkdir(parents=True,exist_ok=True)
for p in list(meshdir.glob('v10_*.obj'))+list(meshdir.glob('v10fallback_*.obj')):
    try:p.unlink()
    except:pass

old={}
if MAN.is_file():
    try: old=json.loads(MAN.read_text('utf-8'))
    except: old={}
textures=old.get('textures') or []

v8=json.loads(V8.read_text('utf-8'))
v9={}
if V9.is_file():
    try:v9=json.loads(V9.read_text('utf-8'))
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
def geti(d,*keys,default=0):
    if not isinstance(d,dict): return default
    for k in keys:
        if k in d and d[k] is not None:
            try:return int(d[k])
            except:return d[k]
    return default
def getv(d,*keys,default=None):
    if not isinstance(d,dict): return default
    for k in keys:
        if k in d and d[k] is not None:return d[k]
    return default

def component_spec(fmt):
    # Unity 2019 VertexFormat
    specs={
      0:('f',4,'float'), 1:('e',2,'float'),
      2:('B',1,'unorm8'), 3:('b',1,'snorm8'),
      4:('H',2,'unorm16'),5:('h',2,'snorm16'),
      6:('B',1,'uint'),7:('b',1,'sint'),
      8:('H',2,'uint'),9:('h',2,'sint'),
      10:('I',4,'uint'),11:('i',4,'sint')}
    if int(fmt) not in specs: raise ValueError('vertex-format-'+str(fmt))
    return specs[int(fmt)]

def normalize_value(x,kind,bits):
    if kind=='unorm8': return float(x)/255.0
    if kind=='snorm8': return max(-1.0,float(x)/127.0)
    if kind=='unorm16': return float(x)/65535.0
    if kind=='snorm16': return max(-1.0,float(x)/32767.0)
    return float(x)

def decode_channel(data,vertex_count,channel,stream):
    st=geti(channel,'stream','m_Stream')
    coff=geti(channel,'offset','m_Offset')
    fmt=geti(channel,'format','m_Format')
    dim=geti(channel,'dimension','m_Dimension') & 0xF
    _,size,kind=component_spec(fmt)
    code=component_spec(fmt)[0]
    soff=stream['offset']; stride=stream['stride']
    vals=[]
    for vi in range(vertex_count):
        pos=soff+vi*stride+coff
        need=dim*size
        if pos<0 or pos+need>len(data):
            raise ValueError(f'channel-oob vi={vi} pos={pos} need={need} data={len(data)}')
        raw=struct.unpack_from('<'+code*dim,data,pos)
        vals.append(tuple(normalize_value(x,kind,size*8) for x in raw))
    return vals

def derive_streams(channels,vertex_count,data_len):
    active=[]
    for i,ch in enumerate(channels or []):
        if not isinstance(ch,dict):continue
        dim=geti(ch,'dimension','m_Dimension') & 0xF
        if dim<=0:continue
        st=geti(ch,'stream','m_Stream')
        fmt=geti(ch,'format','m_Format')
        _,sz,_=component_spec(fmt)
        off=geti(ch,'offset','m_Offset')
        active.append((i,st,off,dim,sz))
    if not active: raise ValueError('no-active-channels')
    stream_count=1+max(x[1] for x in active)
    streams=[]; offset=0
    for s in range(stream_count):
        xs=[x for x in active if x[1]==s]
        if not xs:
            stride=0
        else:
            # UnityPy sums active channel sizes; max-end protects against explicit padding.
            stride_sum=sum(dim*sz for _,_,_,dim,sz in xs)
            stride_end=max(off+dim*sz for _,_,off,dim,sz in xs)
            stride=max(stride_sum,stride_end)
        streams.append({'stream':s,'offset':offset,'stride':stride})
        offset += vertex_count*stride
        offset=(offset+15)&~15
    if streams and streams[-1]['offset']>data_len:
        raise ValueError(f'stream-layout-oob lastOffset={streams[-1]["offset"]} data={data_len}')
    return streams,active

def triangulate(indices,submeshes,index_size,vertex_count):
    faces=[]; meta=[]
    if not submeshes:
        submeshes=[{'firstByte':0,'indexCount':len(indices),'topology':0,'baseVertex':0}]
    for si,sm in enumerate(submeshes):
        if not isinstance(sm,dict):continue
        firstb=geti(sm,'firstByte','m_FirstByte')
        count=geti(sm,'indexCount','m_IndexCount')
        topo=geti(sm,'topology','m_Topology')
        base=geti(sm,'baseVertex','m_BaseVertex')
        start=firstb//index_size
        arr=indices[start:start+count]
        before=len(faces)
        if topo==0: # triangles
            for j in range(0,len(arr)-2,3):
                tri=(arr[j]+base,arr[j+1]+base,arr[j+2]+base)
                if min(tri)>=0 and max(tri)<vertex_count and len(set(tri))==3:faces.append(tri)
        elif topo==1: # triangle strip
            for j in range(0,len(arr)-2):
                tri=(arr[j]+base,arr[j+1]+base,arr[j+2]+base)
                if j&1: tri=(tri[1],tri[0],tri[2])
                if min(tri)>=0 and max(tri)<vertex_count and len(set(tri))==3:faces.append(tri)
        elif topo==2: # quads -> triangles
            for j in range(0,len(arr)-3,4):
                q=[x+base for x in arr[j:j+4]]
                if min(q)>=0 and max(q)<vertex_count:
                    faces.append((q[0],q[1],q[2]));faces.append((q[0],q[2],q[3]))
        meta.append({'submesh':si,'topology':topo,'indexCount':count,'baseVertex':base,'faces':len(faces)-before})
    return faces,meta

def raw_mesh_to_obj(o):
    d=o.read_typetree(wrap=False,check_read=False)
    if not isinstance(d,dict):raise ValueError('typetree-not-dict')
    name=str(d.get('m_Name') or pname(o) or ('Mesh_'+str(pid(o))))
    vd=d.get('m_VertexData') or {}
    if not isinstance(vd,dict):raise ValueError('no-m_VertexData')
    vc=geti(vd,'m_VertexCount','vertexCount')
    channels=getv(vd,'m_Channels','channels',default=[]) or []
    data=getv(vd,'m_DataSize','dataSize',default=b'') or b''
    data=bytes(data)
    if vc<=0 or not data:raise ValueError(f'no-inline-vertex-data vc={vc} bytes={len(data)}')
    streams,active=derive_streams(channels,vc,len(data))
    positions=decode_channel(data,vc,channels[0],streams[geti(channels[0],'stream','m_Stream')]) if len(channels)>0 and (geti(channels[0],'dimension','m_Dimension')&0xF)>=3 else None
    normals=decode_channel(data,vc,channels[1],streams[geti(channels[1],'stream','m_Stream')]) if len(channels)>1 and (geti(channels[1],'dimension','m_Dimension')&0xF)>=3 else None
    # Unity 2018+: channel 4 = TexCoord0
    uvs=decode_channel(data,vc,channels[4],streams[geti(channels[4],'stream','m_Stream')]) if len(channels)>4 and (geti(channels[4],'dimension','m_Dimension')&0xF)>=2 else None
    if not positions or len(positions)!=vc:raise ValueError('position-channel-missing')
    ib=bytes(d.get('m_IndexBuffer') or b'')
    if not ib:raise ValueError('index-buffer-empty')
    index_format=geti(d,'m_IndexFormat',default=0)
    index_size=2 if index_format==0 else 4
    code='H' if index_size==2 else 'I'
    usable=len(ib)-(len(ib)%index_size)
    indices=list(struct.unpack('<'+code*(usable//index_size),ib[:usable]))
    submeshes=d.get('m_SubMeshes') or []
    faces,submeta=triangulate(indices,submeshes,index_size,vc)
    if not faces:raise ValueError(f'no-triangle-faces indices={len(indices)} submeshes={len(submeshes)}')
    lines=['# WFGG Audie V10 raw TypeTree OBJ',f'o {safe(name)}']
    for v in positions:
        x=float(v[0]);y=float(v[1]);z=float(v[2]);lines.append(f'v {x:.9g} {y:.9g} {z:.9g}')
    has_uv=bool(uvs and len(uvs)==vc)
    has_n=bool(normals and len(normals)==vc)
    if has_uv:
        for uv in uvs: lines.append(f'vt {float(uv[0]):.9g} {float(uv[1]):.9g}')
    if has_n:
        for n in normals: lines.append(f'vn {float(n[0]):.9g} {float(n[1]):.9g} {float(n[2]):.9g}')
    for a,b,c in faces:
        a+=1;b+=1;c+=1
        if has_uv and has_n: lines.append(f'f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}')
        elif has_uv: lines.append(f'f {a}/{a} {b}/{b} {c}/{c}')
        elif has_n: lines.append(f'f {a}//{a} {b}//{b} {c}//{c}')
        else: lines.append(f'f {a} {b} {c}')
    info={'name':name,'vertexCount':vc,'faceCount':len(faces),'indexCount':len(indices),'indexFormat':index_format,'indexSize':index_size,'subMeshes':submeta,'hasUV0':has_uv,'hasNormals':has_n,'vertexDataBytes':len(data),'indexBytes':len(ib),'streams':streams,'activeChannels':[{'channel':i,'stream':st,'offset':off,'dimension':dim,'componentBytes':sz} for i,st,off,dim,sz in active]}
    return '\n'.join(lines)+'\n',info

# Exact targets from V8, plus all Mesh objects in Audie mesh CABs discovered by V9.
resolved=(v8.get('diagnostics') or {}).get('resolvedPointers') or []
targets=[];seen=set()
for r in resolved:
    if str(r.get('resolvedType') or '')!='Mesh':continue
    rp=str(r.get('resolvedPath') or ''); sn=str(r.get('targetSerialized') or '').lower(); mp=str(r.get('meshPathID') or '')
    if not rp or not sn or not mp:continue
    k=(rp,sn,mp)
    if k in seen:continue
    seen.add(k);targets.append({'path':rp,'serialized':sn,'pathID':mp,'rendererReferenced':True,'source':r})
for t in ((v9.get('diagnostics') or {}).get('targets') or []):
    rp=str(t.get('path') or ''); sn=str(t.get('serialized') or '').lower(); mp=str(t.get('pathID') or '')
    if not rp or not sn or not mp:continue
    k=(rp,sn,mp)
    if k in seen:continue
    seen.add(k);targets.append({'path':rp,'serialized':sn,'pathID':mp,'rendererReferenced':bool(t.get('rendererReferenced',True)),'source':t.get('source') or {}})

print('AUDIE_MESH_RAW_V10_START',f'exactTargets={len(targets)}',flush=True)
meshes=[];diagnostics=[];bundle_cache={};cab_pairs=set()
for i,t in enumerate(targets,1):
    p=Path(t['path']);sn=t['serialized'];mp=int(t['pathID']);cab_pairs.add((str(p),sn))
    print('V10_TARGET',f'{i}/{len(targets)}',p.name,sn,'p'+str(mp),flush=True)
    if not p.is_file(): diagnostics.append({**t,'status':'missing-bundle'});continue
    key=str(p)
    if key not in bundle_cache:
        try:bundle_cache[key]=(UnityPy.load(str(p)),None)
        except Exception as e:bundle_cache[key]=(None,f'{type(e).__name__}:{e}')
    env,err=bundle_cache[key]
    if env is None: diagnostics.append({**t,'status':'load-fail','error':err});continue
    objs=[o for o in env.objects if typ(o)=='Mesh' and sfname(o).lower()==sn and pid(o)==mp]
    if not objs: diagnostics.append({**t,'status':'object-not-found'});continue
    o=objs[0]
    try:
        text,info=raw_mesh_to_obj(o)
        fn=f'v10_{safe(p.name)}_p{mp}_{safe(info["name"])}.obj';fp=meshdir/fn;fp.write_text(text,'utf-8',newline='')
        rec={'bundle':p.name,'bundlePath':str(p),'category':'v10-raw-typetree','pathID':str(mp),'serializedFile':sn,'name':info['name'],'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size,'rendererReferenced':bool(t.get('rendererReferenced')),'exportMethod':'RAW_TYPETREE_V10','rawDecode':info}
        meshes.append(rec);diagnostics.append({**t,'status':'exported-raw','rawDecode':info})
        print('V10_MESH_OK',p.name,'p'+str(mp),info['name'],f'vertices={info["vertexCount"]}',f'faces={info["faceCount"]}',f'uv={info["hasUV0"]}',f'bytes={fp.stat().st_size}',flush=True)
    except Exception as e:
        diagnostics.append({**t,'status':'raw-export-fail','error':f'{type(e).__name__}:{e}','traceback':' '.join(traceback.format_exception_only(type(e),e)).strip()})
        print('V10_MESH_FAIL',p.name,'p'+str(mp),f'{type(e).__name__}:{e}',flush=True)

# Export all additional Meshes from exact Audie mesh CABs, not only renderer pointers.
for rp,sn in sorted(cab_pairs):
    if 'audie' not in sn or 'mesh' not in sn:continue
    env,err=bundle_cache.get(rp,(None,None))
    if env is None:
        try:env=UnityPy.load(rp);bundle_cache[rp]=(env,None)
        except:continue
    for o in env.objects:
        if typ(o)!='Mesh' or sfname(o).lower()!=sn:continue
        if any(m['bundlePath']==rp and m['pathID']==str(pid(o)) for m in meshes):continue
        try:
            text,info=raw_mesh_to_obj(o)
            fn=f'v10fallback_{safe(Path(rp).name)}_p{pid(o)}_{safe(info["name"])}.obj';fp=meshdir/fn;fp.write_text(text,'utf-8',newline='')
            meshes.append({'bundle':Path(rp).name,'bundlePath':rp,'category':'v10-raw-cab-fallback','pathID':str(pid(o)),'serializedFile':sn,'name':info['name'],'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size,'rendererReferenced':False,'exportMethod':'RAW_TYPETREE_V10','rawDecode':info})
            print('V10_FALLBACK_OK',Path(rp).name,'p'+str(pid(o)),info['name'],f'vertices={info["vertexCount"]}',f'faces={info["faceCount"]}',flush=True)
        except Exception as e:
            diagnostics.append({'path':rp,'serialized':sn,'pathID':str(pid(o)),'status':'raw-fallback-fail','error':f'{type(e).__name__}:{e}'})

carriers=[]
for rp in sorted({m['bundlePath'] for m in meshes}|{t['path'] for t in targets}):
    p=Path(rp);ms=[m for m in meshes if m['bundlePath']==rp]
    carriers.append({'basename':p.name,'path':rp,'category':'v10-raw-mesh','meshCount':len(ms),'rendererReferencedMeshes':sum(1 for m in ms if m['rendererReferenced']),'counts':{'Mesh':len(ms)}})

verdict='RAW_TYPETREE_OBJ_EXPORTED_V10' if meshes else 'RAW_TYPETREE_OBJ_DECODE_FAILED_V10'
manifest={
 'format':'WFGG_LASTWAR_AUDIE_MESH_RAW_V10','verdict':verdict,
 'counts':{'carriers':len(carriers),'sourceCarriers':len(targets),'meshPointers':len(targets),'uniqueMeshPointers':len(targets),'targetSerializedFiles':len({t['serialized'] for t in targets}),'matchedGeometryBundles':len({t['path'] for t in targets}),'meshes':len(meshes),'rendererReferencedMeshes':sum(1 for m in meshes if m['rendererReferenced']),'textures':len(textures),'unresolvedPointers':sum(1 for d in diagnostics if not str(d.get('status','')).startswith('exported'))},
 'carriers':carriers,'meshes':meshes,'textures':textures,
 'diagnostics':{'targets':targets,'attempts':diagnostics},
 'rules':['V10 never calls parse_as_object(), Mesh.export(), fmod_toolkit, or libfmod.','Geometry is decoded directly from Mesh TypeTree m_VertexData/m_Channels/m_DataSize and m_IndexBuffer.','Unity 2019 vertex stream layout follows UnityPy MeshHelper: per-stream stride from active channels and 16-byte alignment between streams.','Only real decoded vertices and valid indexed triangle faces are written to OBJ; no geometry is invented.']}
MAN.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
JSONOUT.parent.mkdir(parents=True,exist_ok=True);JSONOUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_MESH_RAW_V10_READY',f'verdict={verdict}',f'meshes={len(meshes)}',f'referenced={sum(1 for m in meshes if m["rendererReferenced"])}',flush=True)
for m in sorted(meshes,key=lambda x:(0 if 'A_Hero_Audie_01' in x['name'] else 1,-int((x.get('rawDecode') or {}).get('vertexCount') or 0)))[:20]:
    q=m.get('rawDecode') or {};print('V10_RESULT',m['name'],f'vertices={q.get("vertexCount")}',f'faces={q.get("faceCount")}',f'uv={q.get("hasUV0")}',f'ref={m.get("rendererReferenced")}',flush=True)
print('JSON='+str(JSONOUT),flush=True);print('MANIFEST='+str(MAN),flush=True)
