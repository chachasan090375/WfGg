#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
V1="$ROOT/frontend/lab/master-assets-v2/meta/audie-family-scan-v1.json"
V2="$ROOT/frontend/lab/master-assets-v2/meta/audie-family-deep-scan-v2.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/audie-material-map-v3.json"
UNITY_VERSION="2019.4.41f1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR: branche LAB incorrecte" >&2; exit 1; }
[[ -s "$V1" ]] || bash "$ROOT/scripts/lastwar-audie-family-scan-v1.sh"
[[ -s "$V2" ]] || bash "$ROOT/scripts/lastwar-audie-family-deep-scan-v2.sh"
[[ -s "$V1" && -s "$V2" ]] || { echo "ERREUR: scans Audie V1/V2 absents" >&2; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERREUR: python absent" >&2; exit 1; }
python - <<'PYCHK' >/dev/null 2>&1 || { echo "ERREUR: UnityPy absent" >&2; exit 1; }
import UnityPy
PYCHK

echo "AUDIE_MATERIAL_MAP_V3_START"
PYTHONUNBUFFERED=1 python - "$V1" "$V2" "$OUT" "$UNITY_VERSION" <<'PY'
from pathlib import Path
from collections import defaultdict, Counter
import json,re,sys
import UnityPy

v1p=Path(sys.argv[1]); v2p=Path(sys.argv[2]); outp=Path(sys.argv[3]); unity_version=sys.argv[4]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
v1=json.loads(v1p.read_text('utf-8'))
v2=json.loads(v2p.read_text('utf-8'))

AUDIE_RE=re.compile(r'^A_Hero_Audie_01(?:_(.*?))?_([DNS])$',re.I)

def parse_audie(name):
    m=AUDIE_RE.match(str(name or ''))
    if not m:return None
    variant=(m.group(1) or 'base').strip('_') or 'base'
    return {'variant':variant,'role':m.group(2).upper()}

def typ(o):return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o):return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def afkey(o):
    af=getattr(o,'assets_file',None)
    for a in ('name','path'):
        x=getattr(af,a,None)
        if x:return str(x)
    return f'assetsfile@{id(af)}'
def aliases(s):
    if not s:return set()
    b=Path(str(s).replace('\\','/')).name.lower(); out={b}
    if '.' in b:out.add(b.rsplit('.',1)[0])
    return {x for x in out if x}
def externals(o):
    af=getattr(o,'assets_file',None); out=[]
    for e in list(getattr(af,'externals',[]) or []):
        s=''
        for a in ('path','name','file_name'):
            x=getattr(e,a,None)
            if x:s=str(x);break
        if not s:s=str(e)
        out.append(s)
    return out

def ptrs(tree):
    out=[]
    def walk(x,path):
        if isinstance(x,dict):
            if 'm_FileID' in x and 'm_PathID' in x:
                try:f=int(x.get('m_FileID') or 0);p=int(x.get('m_PathID') or 0)
                except:f=p=0
                if p:out.append((path,f,p))
            for k,v in x.items():walk(v,f'{path}.{k}' if path else str(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]')
    walk(tree,'');return out

def tex_slots(tree):
    out=[]; seen=set()
    def walk(x,path,slot_hint=''):
        if isinstance(x,dict):
            hint=slot_hint
            if isinstance(x.get('first'),str) and 'second' in x:
                hint=x.get('first') or hint
                walk(x.get('second'),f'{path}.second' if path else 'second',hint)
                for k,v in x.items():
                    if k not in ('first','second'):walk(v,f'{path}.{k}' if path else str(k),hint)
                return
            if 'm_FileID' in x and 'm_PathID' in x:
                try:f=int(x.get('m_FileID') or 0);p=int(x.get('m_PathID') or 0)
                except:f=p=0
                if p:
                    k=(path,hint,f,p)
                    if k not in seen:seen.add(k);out.append({'field':path,'slot':hint,'fileID':f,'pathID':p})
            for k,v in x.items():walk(v,f'{path}.{k}' if path else str(k),hint)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]',slot_hint)
    walk(tree,'')
    # Keep only material texture environments when paths expose them; otherwise retain named shader slots.
    preferred=[x for x in out if 'TexEnv' in x['field'] or 'm_TexEnvs' in x['field'] or x['slot'].startswith('_')]
    return preferred or out

def read_tree(o):
    try:return o.read_typetree()
    except:return None

# Physical bundle list proved by V1.
paths=[];seen=set()
for b in v1.get('hitBundles',[]):
    p=Path(str(b.get('path') or ''))
    if not p.is_file():continue
    try:k=str(p.resolve())
    except:k=str(p)
    if k not in seen:seen.add(k);paths.append(p)

textures=[]; texture_sets=defaultdict(lambda:{'textures':[],'roles':defaultdict(list)})
material_links=[]; renderer_records=[]; meshfilter_records=[]; bundle_summaries=[]; errors=[]

for n,p in enumerate(paths,1):
    print('AUDIE_MATERIAL_MAP_V3_BUNDLE',f'{n}/{len(paths)}',p.name,flush=True)
    try:env=UnityPy.load(str(p));objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'path':str(p),'error':f'{type(e).__name__}:{e}'});continue
    m=re.search(r'bundle-(\d+)\.bundle$',p.name);bid=int(m.group(1)) if m else None
    byfile=defaultdict(dict);meta=defaultdict(dict);alias_to_file={}
    for o in objs:
        sf=afkey(o);q=pid(o);byfile[sf][q]=o;meta[sf][q]={'type':typ(o),'name':pname(o)}
        for a in aliases(sf):alias_to_file.setdefault(a,sf)
    def resolve(source,fid,target_pid):
        sf=afkey(source)
        if fid==0:tsf=sf
        else:
            ex=externals(source); ep=ex[fid-1] if fid>0 and fid-1<len(ex) else ''
            tsf=None
            for a in aliases(ep):
                if a in alias_to_file:tsf=alias_to_file[a];break
        if not tsf:return None,None
        return tsf,byfile.get(tsf,{}).get(target_pid)

    audie_keys=set(); local_tex=[]
    for o in objs:
        if typ(o)!='Texture2D':continue
        pa=parse_audie(pname(o))
        if not pa:continue
        sf=afkey(o);q=pid(o);audie_keys.add((sf,q))
        try:d=o.read();w=int(d.m_Width);h=int(d.m_Height);fmt=str(getattr(d,'m_TextureFormat',''))
        except Exception:w=h=0;fmt='?'
        rec={'bundleId':bid,'bundlePath':str(p),'serializedFile':sf,'pathID':str(q),'name':pname(o),'variant':pa['variant'],'role':pa['role'],'width':w,'height':h,'pixels':w*h,'format':fmt}
        textures.append(rec);local_tex.append(rec)
        key=(bid,pa['variant'])
        texture_sets[key]['bundleId']=bid;texture_sets[key]['variant']=pa['variant'];texture_sets[key]['textures'].append(rec);texture_sets[key]['roles'][pa['role']].append(rec)

    relevant_materials=set(); local_links=[]
    for o in objs:
        if typ(o)!='Material':continue
        tree=read_tree(o)
        if tree is None:continue
        for s in tex_slots(tree):
            tsf,to=resolve(o,s['fileID'],s['pathID'])
            tname=pname(to) if to is not None else ''
            pa=parse_audie(tname)
            if not pa:continue
            relevant_materials.add((afkey(o),pid(o)))
            link={'bundleId':bid,'bundlePath':str(p),'materialSerializedFile':afkey(o),'materialPathID':str(pid(o)),'materialName':pname(o),'slot':s.get('slot') or s.get('field'),'field':s.get('field'),'fileID':s['fileID'],'textureSerializedFile':tsf,'texturePathID':str(s['pathID']),'textureName':tname,'variant':pa['variant'],'role':pa['role'],'resolved':True}
            material_links.append(link);local_links.append(link)

    # Components: collect renderer -> materials/mesh/gameobject and MeshFilter -> mesh/gameobject.
    local_renderers=[];local_filters=[]
    for o in objs:
        t=typ(o)
        if t not in ('MeshRenderer','SkinnedMeshRenderer','MeshFilter'):continue
        tree=read_tree(o)
        if tree is None:continue
        go=None; mesh=None; mats=[]
        for field,fid,tp in ptrs(tree):
            tsf,to=resolve(o,fid,tp);tt=typ(to) if to is not None else '';tn=pname(to) if to is not None else ''
            target={'serializedFile':tsf,'pathID':str(tp),'type':tt,'name':tn,'field':field,'fileID':fid}
            if tt=='GameObject' and ('m_GameObject' in field or go is None):go=target
            if tt=='Mesh' and ('m_Mesh' in field or mesh is None):mesh=target
            if tt=='Material':mats.append(target)
        rec={'bundleId':bid,'bundlePath':str(p),'serializedFile':afkey(o),'pathID':str(pid(o)),'type':t,'name':pname(o),'gameObject':go,'mesh':mesh,'materials':mats}
        if t=='MeshFilter':local_filters.append(rec);meshfilter_records.append(rec)
        else:local_renderers.append(rec);renderer_records.append(rec)

    # MeshRenderer gets mesh through a MeshFilter on the same GameObject.
    filter_by_go=defaultdict(list)
    for f in local_filters:
        g=f.get('gameObject')
        if g:filter_by_go[(g.get('serializedFile'),g.get('pathID'))].append(f)
    for r in local_renderers:
        if r.get('mesh') is None and r.get('gameObject'):
            g=r['gameObject'];fs=filter_by_go.get((g.get('serializedFile'),g.get('pathID')),[])
            for f in fs:
                if f.get('mesh'):
                    r['mesh']=f['mesh'];r['meshVia']='MeshFilter';break

    bundle_summaries.append({'bundleId':bid,'path':str(p),'objectCount':len(objs),'audieTextures':len(local_tex),'audieMaterialLinks':len(local_links),'renderers':len(local_renderers),'meshFilters':len(local_filters)})

# Normalize sets and determine completeness/resolution signatures.
sets=[]
for (bid,variant),s in texture_sets.items():
    roles={k:v for k,v in s['roles'].items()}
    sizes=sorted({f"{x['width']}x{x['height']}" for x in s['textures'] if x['width'] and x['height']})
    sets.append({'bundleId':bid,'variant':variant,'textureCount':len(s['textures']),'roles':roles,'roleCounts':{k:len(v) for k,v in roles.items()},'completeDNS':all(k in roles and roles[k] for k in ('D','N','S')),'sizes':sizes,'maxPixels':max([x['pixels'] for x in s['textures']] or [0]),'textures':s['textures']})
sets.sort(key=lambda x:(str(x['variant']).lower(),x['bundleId'] if x['bundleId'] is not None else -1))

# Material -> renderer -> GO -> mesh chains.
mat_key_to_links=defaultdict(list)
for l in material_links:mat_key_to_links[(l['bundleId'],l['materialSerializedFile'],l['materialPathID'])].append(l)
chains=[]
for r in renderer_records:
    for m in r.get('materials',[]):
        key=(r['bundleId'],m.get('serializedFile'),m.get('pathID'))
        links=mat_key_to_links.get(key,[])
        if not links:continue
        variants=sorted({x['variant'] for x in links});roles=sorted({x['role'] for x in links})
        chains.append({'bundleId':r['bundleId'],'rendererType':r['type'],'rendererName':r.get('name'),'rendererSerializedFile':r['serializedFile'],'rendererPathID':r['pathID'],'gameObject':r.get('gameObject'),'mesh':r.get('mesh'),'meshVia':r.get('meshVia','direct'),'material':m,'textureLinks':links,'variants':variants,'roles':roles,'completeDNS':all(x in roles for x in ('D','N','S')),'reconstructible':bool(r.get('mesh')) and bool(links)})

# Empirical quality verdict: High only counts as higher definition if its actual dimensions/pixel count exceed base.
by_variant=defaultdict(list)
for t in textures:by_variant[t['variant'].lower()].append(t)
def maxpix(v):return max([x['pixels'] for x in by_variant.get(v,[])]+[0])
def sizes(v):return sorted({f"{x['width']}x{x['height']}" for x in by_variant.get(v,[]) if x['width'] and x['height']})
base_px=maxpix('base');high_px=maxpix('high')
if high_px and base_px and high_px>base_px:qv='HIGH_CONFIRMED_HIGHER_RESOLUTION'
elif high_px and base_px and high_px==base_px:qv='HIGH_SAME_MAX_RESOLUTION_AS_BASE'
elif high_px:qv='HIGH_PRESENT_BASE_RESOLUTION_UNKNOWN'
else:qv='HIGH_VARIANT_NOT_FOUND'
quality={'verdict':qv,'baseMaxPixels':base_px,'highMaxPixels':high_px,'baseSizes':sizes('base'),'highSizes':sizes('high'),'explanation':'D/N/S are map roles (Diffuse/Normal/Specular-like), not resolution labels. Resolution is inferred only from width×height; High is treated as higher definition only when its measured pixel count is larger.'}

variant_summary={}
for v,items in by_variant.items():
    variant_summary[v]={'textureCount':len(items),'bundles':sorted({x['bundleId'] for x in items if x['bundleId'] is not None}),'sizes':sorted({f"{x['width']}x{x['height']}" for x in items if x['width'] and x['height']}),'roles':dict(Counter(x['role'] for x in items)),'maxPixels':max([x['pixels'] for x in items] or [0])}

res={'format':'WFGG_LASTWAR_AUDIE_MATERIAL_MAP_V3','sourceV1':str(v1p),'sourceV2':str(v2p),'bundlesScanned':len(bundle_summaries),'textureCount':len(textures),'textureSetCount':len(sets),'completeTextureSets':sum(1 for x in sets if x['completeDNS']),'materialTextureLinks':len(material_links),'rendererCount':len(renderer_records),'reconstructionChains':len(chains),'reconstructibleChains':sum(1 for x in chains if x['reconstructible']),'qualityHypothesis':quality,'variantSummary':variant_summary,'textureSets':sets,'materialLinks':material_links,'chains':chains,'textures':textures,'bundles':bundle_summaries,'errors':errors[:200],'rules':['D/N/S are classified as texture-map roles, never as SD/HD labels.','Variant names such as High and bullet are separated from texture roles.','A High variant is called higher-resolution only if measured Texture2D dimensions prove it.','Material links come from serialized Unity texture slots that resolve to A_Hero_Audie_01* Texture2D objects.','Reconstruction chains require an actual Renderer using that Material; a chain is reconstructible only when a Mesh is also resolved.']}
outp.parent.mkdir(parents=True,exist_ok=True);outp.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_MATERIAL_MAP_V3_READY',f'bundles={res["bundlesScanned"]}',f'textures={res["textureCount"]}',f'sets={res["textureSetCount"]}',f'complete={res["completeTextureSets"]}',f'materialLinks={res["materialTextureLinks"]}',f'chains={res["reconstructionChains"]}',f'reconstructible={res["reconstructibleChains"]}',flush=True)
print('QUALITY_VERDICT='+quality['verdict'],flush=True)
print('VARIANTS='+json.dumps(variant_summary,ensure_ascii=False),flush=True)
print('JSON='+str(outp),flush=True)
PY

echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-material-map-viewer.html?v=3"