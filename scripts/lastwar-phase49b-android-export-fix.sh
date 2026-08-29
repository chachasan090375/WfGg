#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 49B
# ANDROID-SAFE EXACT MESH/TEXTURE EXPORT
# CODE ONLY · OFFLINE GAME DATA ONLY · exact Phase47 bundles only.
#
# Why this exists:
# UnityPy's high-level export package imports native helpers which reject
# Python's Android platform. Phase48 proves the assets themselves parse 15/15.
# This phase bypasses UnityPy.export entirely:
#   - Mesh => UnityPy.helpers.MeshHelper.MeshHandler (pure Python path)
#   - Texture2D => get_image_data() + texture2ddecoder directly
# No generated geometry. No substitute model. No Last War network.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-web-v2"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-web-export-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE49B_ANDROID_EXPORT_FIX.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase49b-android-export.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente: $P47"
[[ -d "$SRC" ]] || fail "Assets locaux Phase47 absents: $SRC"
command -v python >/dev/null 2>&1 || fail "python absent"

# texture2ddecoder is independent from UnityPy's astc_encoder import. If the
# preinstalled wheel is unusable on Android, rebuild this small C++ extension
# natively in Termux. Failure here is not hidden: the Python phase will report it.
if ! python - <<'PY' >/dev/null 2>&1
import texture2ddecoder
assert callable(getattr(texture2ddecoder,'decode_astc',None))
PY
then
  echo "PHASE49B_DECODER_REBUILD texture2ddecoder"
  pkg install -y clang make >/dev/null 2>&1 || true
  python -m pip install --no-cache-dir --force-reinstall --no-binary=:all: --no-build-isolation texture2ddecoder >/dev/null 2>&1 || true
fi

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import hashlib, json, math, re, sys, traceback

p47p=Path(sys.argv[1]); src=Path(sys.argv[2]); outroot=Path(sys.argv[3]); manifestp=Path(sys.argv[4]); reportp=Path(sys.argv[5]); unity_version=sys.argv[6]

data=json.loads(p47p.read_text(encoding='utf-8'))
heroes=data.get('heroes') or []
if len(heroes)!=15:
    raise SystemExit(f'expected 15 heroes, got {len(heroes)}')

try:
    import UnityPy
    from UnityPy.helpers.MeshHelper import MeshHandler
    from UnityPy.enums import TextureFormat
except Exception as e:
    raise SystemExit(f'UnityPy core import failed: {e!r}')
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

try:
    import texture2ddecoder as t2d
    DECODER_IMPORT_ERROR=None
except Exception as e:
    t2d=None
    DECODER_IMPORT_ERROR=repr(e)

try:
    from PIL import Image
except Exception as e:
    raise SystemExit(f'Pillow absent: {e!r}')

SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s,fallback='asset'):
    x=SAFE.sub('_',str(s or '')).strip('._')
    return x[:180] or fallback

def sha256_file(p,chunk=1024*1024):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while True:
            b=f.read(chunk)
            if not b:break
            h.update(b)
    return h.hexdigest()

def read_obj(reader):
    try:return reader.read()
    except Exception:
        try:return reader.parse_as_object()
        except Exception:return None

def obj_name(d,fallback=''):
    return str(getattr(d,'m_Name','') or getattr(d,'name','') or fallback or '')

def type_name(reader):
    try:return reader.type.name
    except Exception:return str(getattr(reader,'type',''))

def ptr_obj(ptr):
    if ptr is None:return None
    try:return ptr.read()
    except Exception:
        try:return ptr.deref_parse_as_object()
        except Exception:return None

def ptr_name(ptr):
    d=ptr_obj(ptr)
    return obj_name(d) if d is not None else ''

def vec(v,names):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in names]
    except Exception:return None

def manual_obj(mesh):
    # Do NOT import UnityPy.export.MeshExporter: that package is the Android
    # failure path. MeshHandler itself is sufficient to decode Unity vertex/index
    # buffers and compressed mesh data.
    mh=MeshHandler(mesh)
    mh.process()
    verts=mh.m_Vertices or []
    if not verts:
        raise ValueError('MeshHandler produced no vertices')
    uvs=mh.m_UV0 or []
    normals=mh.m_Normals or []
    lines=[f'g {obj_name(mesh,"mesh")}\n']
    for p in verts:
        lines.append('v {:.9g} {:.9g} {:.9g}\n'.format(-float(p[0]),float(p[1]),float(p[2])).replace('nan','0'))
    for uv in uvs:
        lines.append('vt {:.9g} {:.9g}\n'.format(float(uv[0]),float(uv[1])).replace('nan','0'))
    for n in normals:
        lines.append('vn {:.9g} {:.9g} {:.9g}\n'.format(-float(n[0]),float(n[1]),float(n[2])).replace('nan','0'))
    have_uv=len(uvs)>=len(verts)
    have_n=len(normals)>=len(verts)
    tri_groups=mh.get_triangles()
    face_count=0
    for gi,tris in enumerate(tri_groups):
        lines.append(f'g {safe(obj_name(mesh,"mesh"))}_{gi}\n')
        for a,b,c in tris:
            # Mirror X, therefore reverse winding exactly as UnityPy exporter.
            ids=(int(c)+1,int(b)+1,int(a)+1)
            if have_uv and have_n:
                lines.append('f {0}/{0}/{0} {1}/{1}/{1} {2}/{2}/{2}\n'.format(*ids))
            elif have_uv:
                lines.append('f {0}/{0} {1}/{1} {2}/{2}\n'.format(*ids))
            elif have_n:
                lines.append('f {0}//{0} {1}//{1} {2}//{2}\n'.format(*ids))
            else:
                lines.append('f {} {} {}\n'.format(*ids))
            face_count+=1
    if face_count==0:
        raise ValueError('MeshHandler produced no triangles')
    return ''.join(lines),len(verts),face_count,len(uvs),len(normals)

def decfn(*names):
    if t2d is None:return None
    for n in names:
        f=getattr(t2d,n,None)
        if callable(f):return f
    return None

def texture_format_name(tex):
    try:return TextureFormat(int(tex.m_TextureFormat)).name
    except Exception:return str(getattr(tex,'m_TextureFormat','UNKNOWN'))

def direct_texture_image(tex):
    raw=bytes(tex.get_image_data())
    w=int(getattr(tex,'m_Width',0) or 0); h=int(getattr(tex,'m_Height',0) or 0)
    if w<=0 or h<=0:raise ValueError(f'invalid texture size {w}x{h}')
    fmt=texture_format_name(tex)

    # Uncompressed Unity formats — pure Pillow, no native codec.
    if fmt=='RGBA32': img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','RGBA')
    elif fmt=='ARGB32': img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','ARGB')
    elif fmt=='BGRA32': img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','BGRA')
    elif fmt=='RGB24': img=Image.frombytes('RGB',(w,h),raw[:w*h*3],'raw','RGB').convert('RGBA')
    elif fmt=='BGR24': img=Image.frombytes('RGB',(w,h),raw[:w*h*3],'raw','BGR').convert('RGBA')
    elif fmt in ('Alpha8','R8'):
        band=Image.frombytes('L',(w,h),raw[:w*h])
        if fmt=='Alpha8':
            img=Image.new('RGBA',(w,h),(255,255,255,0));img.putalpha(band)
        else:img=Image.merge('RGBA',(band,band,band,Image.new('L',(w,h),255)))
    else:
        if t2d is None:
            raise RuntimeError('texture2ddecoder unavailable: '+str(DECODER_IMPORT_ERROR))
        f=None; args=(raw,w,h)
        # ASTC family: TextureFormat names end in e.g. _4x4, _5x5, _6x6.
        if fmt.startswith('ASTC'):
            m=re.search(r'_(\d+)x(\d+)$',fmt)
            if not m:raise NotImplementedError('ASTC block size unresolved: '+fmt)
            bw,bh=map(int,m.groups());f=decfn('decode_astc');args=(raw,w,h,bw,bh)
        elif fmt in ('ETC_RGB4','ETC_RGB4_3DS'):
            f=decfn('decode_etc1')
        elif fmt=='ETC2_RGB':
            f=decfn('decode_etc2','decode_etc2_rgb')
        elif fmt=='ETC2_RGBA1':
            f=decfn('decode_etc2a1','decode_etc2_rgba1')
        elif fmt=='ETC2_RGBA8':
            f=decfn('decode_etc2a8','decode_etc2_rgba8')
        elif fmt in ('EAC_R','EAC_R_SIGNED'):
            f=decfn('decode_eacr_signed' if fmt.endswith('SIGNED') else 'decode_eacr')
        elif fmt in ('EAC_RG','EAC_RG_SIGNED'):
            f=decfn('decode_eacrg_signed' if fmt.endswith('SIGNED') else 'decode_eacrg')
        elif fmt=='DXT1':f=decfn('decode_bc1')
        elif fmt=='DXT5':f=decfn('decode_bc3')
        elif fmt=='BC4':f=decfn('decode_bc4')
        elif fmt=='BC5':f=decfn('decode_bc5')
        elif fmt in ('BC6H','BC6H_SF16','BC6H_UF16'):f=decfn('decode_bc6')
        elif fmt=='BC7':f=decfn('decode_bc7')
        elif fmt=='ATC_RGB4':f=decfn('decode_atc_rgb4')
        elif fmt=='ATC_RGBA8':f=decfn('decode_atc_rgba8')
        elif fmt in ('PVRTC_RGB2','PVRTC_RGBA2'):
            f=decfn('decode_pvrtc');args=(raw,w,h,True)
        elif fmt in ('PVRTC_RGB4','PVRTC_RGBA4'):
            f=decfn('decode_pvrtc');args=(raw,w,h,False)
        else:raise NotImplementedError('direct decoder not implemented: '+fmt)
        if f is None:raise RuntimeError('decoder function absent for '+fmt)
        decoded=f(*args)
        # texture2ddecoder outputs BGRA for its block codecs.
        img=Image.frombytes('RGBA',(w,h),decoded,'raw','BGRA')

    # UnityPy's public converter defaults to vertical flip; preserve that exact
    # convention so renderer output matches the expected exporter semantics.
    img=img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img,fmt,len(raw)

def transform_row(t):
    return {
      'gameObject':ptr_name(getattr(t,'m_GameObject',None)),
      'parentTransform':ptr_name(getattr(t,'m_Father',None)),
      'localPosition':vec(getattr(t,'m_LocalPosition',None),('x','y','z')),
      'localRotation':vec(getattr(t,'m_LocalRotation',None),('x','y','z','w')),
      'localScale':vec(getattr(t,'m_LocalScale',None),('x','y','z')),
    }

def material_row(mat):
    return {'name':obj_name(mat,'Material'),'shader':ptr_name(getattr(mat,'m_Shader',None))}

out=[]
format_counts={}
for h in heroes:
    hid=int(h['heroId']); name=h.get('name') or str(hid); hsrc=src/str(hid); hout=outroot/str(hid)
    (hout/'meshes').mkdir(parents=True,exist_ok=True);(hout/'textures').mkdir(parents=True,exist_ok=True)
    files=sorted(hsrc.glob('*.bundle'))
    row={'heroId':hid,'name':name,'queueModelPath':h.get('queueModelPath'),'bundleCount':len(files),'parseOk':False,
         'meshes':[],'textures':[],'transforms':[],'renderers':[],'skinnedRenderers':[],'materials':[],'clips':[],'errors':[]}
    try:
        UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
        env=UnityPy.load(*[str(p) for p in files])
        row['parseOk']=True
        seen=set();objs=[]
        for r in env.objects:
            key=(type_name(r),getattr(r,'path_id',None),str(getattr(getattr(r,'assets_file',None),'name','')))
            if key in seen:continue
            seen.add(key);objs.append(r)
        mi=ti=0
        for r in objs:
            typ=type_name(r)
            if typ not in {'Mesh','Texture2D','Transform','MeshRenderer','Renderer','SkinnedMeshRenderer','Material','AnimationClip'}:continue
            d=read_obj(r)
            if d is None:continue
            nm=obj_name(d,typ)
            if typ=='Mesh':
                mi+=1;item={'name':nm,'exported':False}
                try:
                    txt,vn,fn,uvn,nn=manual_obj(d);p=hout/'meshes'/f'{mi:03d}_{safe(nm,"mesh")}.obj';p.write_text(txt,encoding='utf-8')
                    item.update({'exported':True,'file':'meshes/'+p.name,'vertices':vn,'faces':fn,'uvs':uvn,'normals':nn,'bytes':p.stat().st_size,'sha256':sha256_file(p)})
                except Exception as e:item['error']=repr(e)
                row['meshes'].append(item)
            elif typ=='Texture2D':
                ti+=1;item={'name':nm,'exported':False,'format':texture_format_name(d),'width':getattr(d,'m_Width',None),'height':getattr(d,'m_Height',None)}
                format_counts[item['format']]=format_counts.get(item['format'],0)+1
                try:
                    img,fmt,rawbytes=direct_texture_image(d);p=hout/'textures'/f'{ti:03d}_{safe(nm,"texture")}.png';img.save(p,'PNG')
                    item.update({'exported':True,'file':'textures/'+p.name,'format':fmt,'rawBytes':rawbytes,'bytes':p.stat().st_size,'sha256':sha256_file(p)})
                except Exception as e:item['error']=repr(e)
                row['textures'].append(item)
            elif typ=='Transform':row['transforms'].append(transform_row(d))
            elif typ in ('MeshRenderer','Renderer'):
                row['renderers'].append({'gameObject':ptr_name(getattr(d,'m_GameObject',None)),'materials':[ptr_name(p) for p in (getattr(d,'m_Materials',[]) or []) if ptr_name(p)]})
            elif typ=='SkinnedMeshRenderer':
                row['skinnedRenderers'].append({'gameObject':ptr_name(getattr(d,'m_GameObject',None)),'mesh':ptr_name(getattr(d,'m_Mesh',None)),'materials':[ptr_name(p) for p in (getattr(d,'m_Materials',[]) or []) if ptr_name(p)],'bones':[ptr_name(p) for p in (getattr(d,'m_Bones',[]) or []) if ptr_name(p)],'rootBone':ptr_name(getattr(d,'m_RootBone',None))})
            elif typ=='Material':row['materials'].append(material_row(d))
            elif typ=='AnimationClip':row['clips'].append(obj_name(d,'AnimationClip'))
        (hout/'scene.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as e:
        row['errors'].append(repr(e));row['errors'].append(traceback.format_exc()[-5000:])
    out.append(row)
    print('PHASE49B_HERO',hid,name,f"obj={sum(x.get('exported',False) for x in row['meshes'])}/{len(row['meshes'])}",f"png={sum(x.get('exported',False) for x in row['textures'])}/{len(row['textures'])}",flush=True)

summary={
 'format':'WFGG_LASTWAR_CURRENT15_WEB_EXPORT_V2_ANDROID_SAFE','networkUsed':False,'unityFallback':unity_version,
 'texture2ddecoderAvailable':t2d is not None,'texture2ddecoderImportError':DECODER_IMPORT_ERROR,
 'heroCount':15,'parseOkCount':sum(x['parseOk'] for x in out),
 'heroesWithObj':sum(any(m.get('exported') for m in x['meshes']) for x in out),
 'heroesWithPng':sum(any(t.get('exported') for t in x['textures']) for x in out),
 'heroesWithClips':sum(bool(x['clips']) for x in out),
 'meshObjectCount':sum(len(x['meshes']) for x in out),'meshObjExportCount':sum(sum(m.get('exported',False) for m in x['meshes']) for x in out),
 'textureObjectCount':sum(len(x['textures']) for x in out),'texturePngExportCount':sum(sum(t.get('exported',False) for t in x['textures']) for x in out),
 'textureFormats':format_counts,'heroes':out,
 'guardrails':{'exactPhase47BundlesOnly':True,'unityPyHighLevelExporterUsed':False,'noSimilarityFallback':True,'noGeneratedGeometry':True,'noLastWarNetwork':True,'exportedRenderAssetsCommitted':False}
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 49B ANDROID EXPORT FIX',
 'exact Phase47 bundles · manual MeshHandler OBJ · direct Texture2D decoding',
 f"decoderAvailable={summary['texture2ddecoderAvailable']} decoderImportError={summary['texture2ddecoderImportError']}",
 f"heroes=15 parseOk={summary['parseOkCount']}/15 heroesWithObj={summary['heroesWithObj']}/15 heroesWithPng={summary['heroesWithPng']}/15 heroesWithClips={summary['heroesWithClips']}/15",
 f"meshObjects={summary['meshObjectCount']} objExported={summary['meshObjExportCount']} textureObjects={summary['textureObjectCount']} pngExported={summary['texturePngExportCount']}",
 'textureFormats='+json.dumps(format_counts,ensure_ascii=False,sort_keys=True),'']
for h in out:
    lines.append(f"HERO {h['heroId']} {h['name']} parse={h['parseOk']} obj={sum(x.get('exported',False) for x in h['meshes'])}/{len(h['meshes'])} png={sum(x.get('exported',False) for x in h['textures'])}/{len(h['textures'])} clips={len(h['clips'])}")
    for m in h['meshes']:
        if not m.get('exported'):lines.append(f"  MESH_FAIL {m['name']} :: {m.get('error')}")
    for t in h['textures']:
        if not t.get('exported'):lines.append(f"  TEX_FAIL {t['name']} format={t.get('format')} size={t.get('width')}x{t.get('height')} :: {t.get('error')}")
    for e in h['errors']:lines.append('  ERROR '+str(e).replace('\n',' ')[:1600])
    lines.append('')
lines += ['GUARDRAILS','  exact_phase47_bundles_only=true','  unitypy_high_level_exporter_used=false','  no_similarity_fallback=true','  no_generated_geometry=true','  no_lastwar_network=true','  exported_render_assets_not_committed=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE49B_OK',f"parse={summary['parseOkCount']}/15",f"obj={summary['heroesWithObj']}/15",f"png={summary['heroesWithPng']}/15",f"clips={summary['heroesWithClips']}/15",f"mesh={summary['meshObjExportCount']}/{summary['meshObjectCount']}",f"tex={summary['texturePngExportCount']}/{summary['textureObjectCount']}")
PYEOF

python "$PY" "$P47" "$SRC" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"
rm -f "$PY"

# Only script + metadata go to Git. OBJ/PNG outputs remain local until renderer
# packaging policy is decided.
git add scripts/lastwar-phase49b-android-export-fix.sh frontend/lab/master-assets-v2/meta/current15-web-export-v2.json
if ! git diff --cached --quiet -- scripts/lastwar-phase49b-android-export-fix.sh frontend/lab/master-assets-v2/meta/current15-web-export-v2.json; then
  git commit -m "lab: export exact current15 assets without Android UnityPy exporters"
fi
git push origin "$BRANCH"

echo "=== PHASE 49B TERMINEE ==="
echo "Assets locaux: frontend/lab/local_assets/lastwar-current15-web-v2"
echo "Manifest: frontend/lab/master-assets-v2/meta/current15-web-export-v2.json"
echo "Rapport: $REPORT"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
