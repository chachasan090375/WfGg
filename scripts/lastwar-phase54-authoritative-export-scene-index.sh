#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 54
# AUTHORITATIVE EXPORT-ID + SCENE INDEX IN ONE PASS
# CODE ONLY · OFFLINE ONLY · no fuzzy/name fallback for bindings.
#
# Fixes the root cause exposed by Phase53x:
# Phase49B exported exact OBJ/PNG in deterministic env.objects order, but did not
# persist each object's Unity identity. This phase recreates that exact order,
# verifies it against the already validated Phase49B files, and records:
#   objectKey = normalized serialized assets-file name + pathId
# It resolves PPtrs WITHOUT dereferencing external files:
#   m_FileID==0 -> source serialized file
#   m_FileID>0  -> source SerializedFile.externals[m_FileID-1]
# Thus no CAB file needs to exist as a standalone disk file.
#
# Inputs: Phase47 exact bundles, Phase49B verified OBJ/PNG, Phase52 runtime pack.
# Outputs: one exact scene/index JSON per hero + one compact manifest/report.
# No re-extraction from network. No generated geometry/motion. main untouched.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P49="$ROOT/frontend/lab/master-assets-v2/meta/current15-web-export-v2.json"
P52="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-pack-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
WEB49="$ROOT/frontend/lab/local_assets/lastwar-current15-web-v2"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-runtime-v5-authoritative"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-authoritative-export-scene-index-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE54_AUTHORITATIVE_EXPORT_SCENE_INDEX.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase54-authoritative-index.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" && -s "$P49" && -s "$P52" ]] || fail "manifestes Phase47/49B/52 absents"
[[ -d "$SRC" && -d "$WEB49" ]] || fail "assets locaux Phase47/49B absents"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import hashlib, json, os, re, sys, traceback

p47p,p49p,p52p,src,web49,out,manifestp,reportp,unity_version=map(str,sys.argv[1:])
p47p=Path(p47p);p49p=Path(p49p);p52p=Path(p52p);src=Path(src);web49=Path(web49);out=Path(out);manifestp=Path(manifestp);reportp=Path(reportp)
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
j47=json.loads(p47p.read_text(encoding='utf-8')); j49=json.loads(p49p.read_text(encoding='utf-8')); j52=json.loads(p52p.read_text(encoding='utf-8'))
h47={int(x['heroId']):x for x in j47.get('heroes',[])}; h49={int(x['heroId']):x for x in j49.get('heroes',[])}; h52={int(x['heroId']):x for x in j52.get('heroes',[])}
ids=sorted(set(h47)&set(h49)&set(h52))
if len(ids)!=15: raise SystemExit(f'expected 15 common heroes, got {len(ids)}')

def typ(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def read(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except:return None
def attr(o,*names,default=None):
    for n in names:
        try:
            v=getattr(o,n)
            if v is not None:return v
        except Exception:pass
    return default
def raw_pid(x):
    if x is None:return None
    for n in ('path_id','m_PathID'):
        try:
            v=getattr(x,n,None)
            if v is not None:return int(v)
        except Exception:pass
    return None
def raw_fid(p):
    if p is None:return 0
    for n in ('m_FileID','file_id','fileID'):
        try:
            v=getattr(p,n,None)
            if v is not None:return int(v)
        except Exception:pass
    return 0
def af_of_reader(r):
    for n in ('assets_file','assetsfile'):
        try:
            x=getattr(r,n,None)
            if x is not None:return x
        except Exception:pass
    return None
def af_name(af):
    if af is None:return ''
    return str(getattr(af,'name','') or getattr(af,'path','') or '')
def norm_file(s):
    s=str(s or '').replace('\\','/').rstrip('/')
    if '/' in s:s=s.rsplit('/',1)[-1]
    return s.lower()
def rkey(r):
    p=raw_pid(r); n=norm_file(af_name(af_of_reader(r)))
    return None if p is None or not n else (n,p)
def keyrow(k): return None if k is None else {'assetsFile':k[0],'pathId':k[1],'objectKey':f'{k[0]}::{k[1]}'}
def keystr(k): return None if k is None else f'{k[0]}::{k[1]}'
def ext_path(e):
    for n in ('path','path_name','m_PathName','name'):
        try:
            v=getattr(e,n,None)
            if v:return str(v)
        except Exception:pass
    return ''
def source_af_of_ptr(p):
    for n in ('assets_file','assetsfile','_assets_file'):
        try:
            x=getattr(p,n,None)
            if x is not None:return x
        except Exception:pass
    return None
def pkey(p):
    if p is None:return None
    path=raw_pid(p)
    if path in (None,0):return None
    srcaf=source_af_of_ptr(p)
    if srcaf is None:return None
    fid=raw_fid(p)
    if fid==0:return (norm_file(af_name(srcaf)),path)
    exts=list(getattr(srcaf,'externals',[]) or [])
    if fid<1 or fid>len(exts):return None
    target=norm_file(ext_path(exts[fid-1]))
    return None if not target else (target,path)
def name(o,fb=''):
    if o is None:return str(fb or '')
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or fb or '')
def vec(v,ns):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in ns]
    except:return None
def expected_root(q):return Path(str(q or '')).stem
def root_score(n,e):
    n=str(n or '');e=str(e or '')
    if n==e:return 10000
    nl=n.lower();el=e.lower()
    if nl==el:return 9500
    if nl.startswith(el) or el.startswith(nl):return 7000
    if el in nl or nl in el:return 5000
    return 0
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def pair_items(x):
    if x is None:return []
    if isinstance(x,dict):return list(x.items())
    out=[]
    for it in x or []:
        if isinstance(it,(list,tuple)) and len(it)>=2:out.append((it[0],it[1]));continue
        if isinstance(it,dict):k=it.get('first',it.get('key',it.get('Key')));v=it.get('second',it.get('value',it.get('Value')))
        else:k=attr(it,'first','key','Key');v=attr(it,'second','value','Value')
        if k is not None:out.append((k,v))
    return out

def tex_slots(mat):
    sp=attr(mat,'m_SavedProperties','savedProperties'); te=attr(sp,'m_TexEnvs','TexEnvs',default=[])
    out=[]
    for k,v in pair_items(te):
        tp=attr(v,'m_Texture','texture') if v is not None else None
        if tp is None and isinstance(v,dict):tp=v.get('m_Texture',v.get('texture'))
        out.append({'slot':str(k),'textureKey':keyrow(pkey(tp))})
    return out

rows=[]
for pos,hid in enumerate(ids,1):
    h=h47[hid]; e49=h49[hid]; e52=h52[hid]; nm=h.get('name') or str(hid); expected=expected_root(h.get('queueModelPath'))
    print(f'PHASE54_HERO {pos}/15 id={hid} name={nm}',flush=True)
    row={'heroId':hid,'name':nm,'parseOk':False,'exportIdentityOk':False,'rootExact':False,'sceneLinked':False,'errors':[]}
    try:
        hdir=src/str(hid); files=sorted({hdir/os.path.basename(str(b.get('logicalName') or '')) for b in h.get('bundles',[]) if os.path.basename(str(b.get('logicalName') or '')) and (hdir/os.path.basename(str(b.get('logicalName') or ''))).is_file()})
        if not files:raise ValueError('no exact bundles')
        env=UnityPy.load(*[str(p) for p in files]); row['parseOk']=True
        # EXACT Phase49B dedup order.
        seen=set(); objs=[]
        for r in env.objects:
            k=(typ(r),raw_pid(r),norm_file(af_name(af_of_reader(r))))
            if k in seen:continue
            seen.add(k);objs.append(r)
        readers_by_key={rkey(r):r for r in objs if rkey(r) is not None}
        loaded_files=sorted({k[0] for k in readers_by_key})

        # Persist exact identities for already validated Phase49B files.
        mesh_rs=[r for r in objs if typ(r)=='Mesh']; tex_rs=[r for r in objs if typ(r)=='Texture2D']
        em=list(e49.get('meshes',[])); et=list(e49.get('textures',[]))
        if len(mesh_rs)!=len(em) or len(tex_rs)!=len(et):raise ValueError(f'Phase49 counts changed mesh {len(mesh_rs)}/{len(em)} tex {len(tex_rs)}/{len(et)}')
        export_mesh={}; export_tex={}; mism=[]
        for r,x in zip(mesh_rs,em):
            o=read(r); rk=rkey(r); n=name(o,'Mesh')
            if n!=str(x.get('name') or ''):mism.append(f'Mesh:{n}!={x.get("name")}')
            p=web49/str(hid)/str(x.get('file') or '')
            if not p.is_file() or (x.get('sha256') and sha(p)!=x.get('sha256')):raise ValueError(f'OBJ missing/hash mismatch {x.get("file")}')
            export_mesh[rk]={**x,'objectKey':keyrow(rk)}
        for r,x in zip(tex_rs,et):
            o=read(r); rk=rkey(r); n=name(o,'Texture2D')
            if n!=str(x.get('name') or ''):mism.append(f'Texture:{n}!={x.get("name")}')
            p=web49/str(hid)/str(x.get('file') or '')
            if not p.is_file() or (x.get('sha256') and sha(p)!=x.get('sha256')):raise ValueError(f'PNG missing/hash mismatch {x.get("file")}')
            export_tex[rk]={**x,'objectKey':keyrow(rk)}
        if mism:raise ValueError('Phase49 order/name mismatch: '+' | '.join(mism[:8]))
        row['exportIdentityOk']=True

        # Catalog exact objects by objectKey.
        go={}; tr={}; go_to_tr={}; mats={}; meshes={}; textures={}
        mfilters=[]; renderers=[]; skinned=[]; external_targets=set()
        def register_external(k):
            if k is not None and k[0] not in loaded_files:external_targets.add(k[0])
        for r in objs:
            t=typ(r); o=read(r); rk=rkey(r)
            if o is None or rk is None:continue
            if t=='GameObject':go[rk]=name(o)
            elif t in ('Transform','RectTransform'):
                gk=pkey(attr(o,'m_GameObject')); pk=pkey(attr(o,'m_Father')); register_external(gk);register_external(pk)
                kids=[]
                for pp in (attr(o,'m_Children',default=[]) or []):
                    q=pkey(pp);register_external(q)
                    if q:kids.append(q)
                tr[rk]={'key':keyrow(rk),'gameObjectKey':keyrow(gk),'name':'','parent':pk,'children':kids,'localPosition':vec(attr(o,'m_LocalPosition'),('x','y','z')),'localRotation':vec(attr(o,'m_LocalRotation'),('x','y','z','w')),'localScale':vec(attr(o,'m_LocalScale'),('x','y','z'))}
                if gk:go_to_tr[gk]=rk
            elif t=='Mesh':meshes[rk]={'key':keyrow(rk),'name':name(o,'Mesh'),'export':export_mesh.get(rk)}
            elif t=='Texture2D':textures[rk]={'key':keyrow(rk),'name':name(o,'Texture2D'),'export':export_tex.get(rk)}
            elif t=='Material':
                slots=tex_slots(o)
                for s in slots:
                    kd=s.get('textureKey'); register_external((kd['assetsFile'],kd['pathId']) if kd else None)
                mats[rk]={'key':keyrow(rk),'name':name(o,'Material'),'textures':slots}
        for k,t in tr.items():
            g=t.get('gameObjectKey'); gk=(g['assetsFile'],g['pathId']) if g else None
            t['name']=go.get(gk,'')

        roots=[(k,t) for k,t in tr.items() if t['parent'] is None or t['parent'] not in tr]
        def desc(rootk):
            n=0
            for k in tr:
                cur=k;seen2=set()
                while cur in tr and cur not in seen2:
                    if cur==rootk:n+=1;break
                    seen2.add(cur);cur=tr[cur]['parent']
            return n
        cand=[]
        for k,t in roots:
            sc=root_score(t['name'],expected)
            if sc>=5000:cand.append((sc,desc(k),k,t))
        if not cand:raise ValueError('authoritative root not found')
        cand.sort(key=lambda z:(z[0],z[1]),reverse=True); sc,rootdesc,rootk,root=cand[0];row['rootExact']=True
        def under(k):
            cur=k;seen2=set()
            while cur in tr and cur not in seen2:
                if cur==rootk:return True
                seen2.add(cur);cur=tr[cur]['parent']
            return False
        pmemo={}
        def pathof(k):
            if k in pmemo:return pmemo[k]
            t=tr.get(k)
            if not t:return ''
            pp=pathof(t['parent']) if t['parent'] in tr else ''
            v=(pp+'/'+t['name']) if pp else t['name'];pmemo[k]=v;return v
        scene_tr=[]
        for k,t in tr.items():
            if under(k):
                scene_tr.append({'key':t['key'],'gameObjectKey':t['gameObjectKey'],'name':t['name'],'parentKey':keyrow(t['parent']),'path':pathof(k),'localPosition':t['localPosition'],'localRotation':t['localRotation'],'localScale':t['localScale']})
        pathmap={keystr(k):pathof(k) for k in tr if under(k)}

        # Components are collected after hierarchy exists.
        for r in objs:
            t=typ(r)
            if t not in ('MeshFilter','MeshRenderer','Renderer','SkinnedMeshRenderer'):continue
            o=read(r);rk=rkey(r)
            if o is None or rk is None:continue
            gk=pkey(attr(o,'m_GameObject'));register_external(gk);tk=go_to_tr.get(gk)
            if tk is None or not under(tk):continue
            matkeys=[]
            for pp in (attr(o,'m_Materials',default=[]) or []):
                mk=pkey(pp);register_external(mk);matkeys.append(mk)
            base={'componentKey':keyrow(rk),'gameObjectKey':keyrow(gk),'transformKey':keyrow(tk),'transformPath':pathmap.get(keystr(tk)),'materialKeys':[keyrow(x) for x in matkeys if x]}
            if t=='MeshFilter':
                mk=pkey(attr(o,'m_Mesh'));register_external(mk);mfilters.append({**base,'meshKey':keyrow(mk)})
            elif t in ('MeshRenderer','Renderer'):renderers.append(base)
            else:
                mk=pkey(attr(o,'m_Mesh'));register_external(mk)
                bones=[]
                for pp in (attr(o,'m_Bones',default=[]) or []):
                    bk=pkey(pp);register_external(bk);bones.append(keyrow(bk))
                rb=pkey(attr(o,'m_RootBone'));register_external(rb)
                skinned.append({**base,'meshKey':keyrow(mk),'bones':bones,'rootBone':keyrow(rb)})

        meshlinks=[];unm=[]
        for c in mfilters+skinned:
            kd=c.get('meshKey');mk=(kd['assetsFile'],kd['pathId']) if kd else None; ex=export_mesh.get(mk)
            x={'componentKey':c['componentKey'],'transformPath':c['transformPath'],'meshKey':kd,'meshName':meshes.get(mk,{}).get('name'),'objFile':ex.get('file') if ex else None,'objSha256':ex.get('sha256') if ex else None}
            meshlinks.append(x)
            if not x['objFile']:unm.append(x)
        usedm=[];unmat=[];untex=[]
        usedkeys=set()
        for c in renderers+skinned:
            for kd in c.get('materialKeys',[]):usedkeys.add((kd['assetsFile'],kd['pathId']))
        for mk in sorted(usedkeys):
            m=mats.get(mk)
            if not m:unmat.append(keyrow(mk));continue
            mm={**m,'textures':[]}
            for s in m['textures']:
                kd=s.get('textureKey');tk=(kd['assetsFile'],kd['pathId']) if kd else None;ex=export_tex.get(tk) if tk else None
                ss={**s,'textureName':textures.get(tk,{}).get('name'),'pngFile':ex.get('file') if ex else None,'pngSha256':ex.get('sha256') if ex else None}
                if tk and not ss['pngFile']:untex.append(ss)
                mm['textures'].append(ss)
            usedm.append(mm)

        scene={'format':'WFGG_LASTWAR_HERO_AUTHORITATIVE_SCENE_V1','heroId':hid,'name':nm,'queueModelPath':h.get('queueModelPath'),'rendererMode':e52.get('rendererMode'),
               'root':{'key':keyrow(rootk),'name':root['name'],'path':pathof(rootk),'descendants':rootdesc},'loadedSerializedFiles':loaded_files,
               'transforms':scene_tr,'meshFilters':mfilters,'renderers':renderers,'skinnedRenderers':skinned,'meshLinks':meshlinks,'materials':usedm,
               'runtimeBase':f'../lastwar-current15-runtime-v1/{hid}/','idleAnimation':'animation/idle.json.gz','rig':'rig.json.gz',
               'guardrails':{'pptrResolvedFromFileIdAndExternals':True,'noPPtrDereferenceRequired':True,'noNameFallbackForBinding':True,'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True}}
        hd=out/str(hid);hd.mkdir(parents=True,exist_ok=True);(hd/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
        row.update({'rootDescendantCount':rootdesc,'transformCount':len(scene_tr),'meshLinkCount':len(meshlinks),'unresolvedMeshLinks':len(unm),'materialCount':len(usedm),'unresolvedMaterialLinks':len(unmat),'unresolvedTextureLinks':len(untex),'externalTargetFiles':sorted(external_targets),'sceneJson':str((hd/'scene.json').relative_to(out))})
        row['sceneLinked']=bool(scene_tr and meshlinks and not unm and not unmat)
        if unm:row['errors'].append('unresolved meshes='+str(len(unm)))
        if unmat:row['errors'].append('unresolved materials='+str(len(unmat)))
    except Exception as e:
        row['errors'].append(repr(e));row['traceback']=traceback.format_exc()[-4000:]
    rows.append(row)
    print('PHASE54_HERO_DONE',hid,f"identity={row['exportIdentityOk']}",f"root={row['rootExact']}",f"linked={row['sceneLinked']}",f"transforms={row.get('transformCount',0)}",f"mesh={row.get('unresolvedMeshLinks',0)}",f"mat={row.get('unresolvedMaterialLinks',0)}",f"tex={row.get('unresolvedTextureLinks',0)}",flush=True)

summary={'format':'WFGG_LASTWAR_CURRENT15_AUTHORITATIVE_EXPORT_SCENE_INDEX_V1','networkUsed':False,'heroCount':15,'parseOkCount':sum(x['parseOk'] for x in rows),'exportIdentityOkCount':sum(x['exportIdentityOk'] for x in rows),'rootExactCount':sum(x['rootExact'] for x in rows),'sceneLinkedCount':sum(x['sceneLinked'] for x in rows),'transformCount':sum(x.get('transformCount',0) for x in rows),'meshLinkCount':sum(x.get('meshLinkCount',0) for x in rows),'unresolvedMeshLinkCount':sum(x.get('unresolvedMeshLinks',0) for x in rows),'unresolvedMaterialLinkCount':sum(x.get('unresolvedMaterialLinks',0) for x in rows),'unresolvedTextureLinkCount':sum(x.get('unresolvedTextureLinks',0) for x in rows),'heroes':[{k:v for k,v in x.items() if k!='traceback'} for x in rows],'guardrails':{'phase49IdentityPersistedAtSourceOrder':True,'pptrResolvedFromFileIdAndExternals':True,'noNameFallbackForBinding':True,'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True,'noLastWarNetwork':True}}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War LAB — PHASE 54 AUTHORITATIVE EXPORT + SCENE INDEX',f"heroes=15 parseOk={summary['parseOkCount']}/15 exportIdentity={summary['exportIdentityOkCount']}/15 rootExact={summary['rootExactCount']}/15 sceneLinked={summary['sceneLinkedCount']}/15",f"transforms={summary['transformCount']} meshLinks={summary['meshLinkCount']} unresolvedMesh={summary['unresolvedMeshLinkCount']} unresolvedMaterial={summary['unresolvedMaterialLinkCount']} unresolvedTexture={summary['unresolvedTextureLinkCount']}",'']
for x in rows:lines.append(f"HERO {x['heroId']} {x['name']} identity={x['exportIdentityOk']} root={x['rootExact']} linked={x['sceneLinked']} rootDesc={x.get('rootDescendantCount',0)} transforms={x.get('transformCount',0)} meshLinks={x.get('meshLinkCount',0)} unresolvedMesh={x.get('unresolvedMeshLinks',0)} unresolvedMaterial={x.get('unresolvedMaterialLinks',0)} unresolvedTexture={x.get('unresolvedTextureLinks',0)} externalTargets={x.get('externalTargetFiles',[])} errors={x['errors']}")
lines += ['','GUARDRAILS','  phase49_identity_persisted_at_source_order=true','  pptr_resolved_from_fileid_and_externals=true','  no_name_fallback_for_binding=true','  no_fuzzy_matching=true','  no_generated_geometry=true','  no_generated_motion=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE54_OK',f"exportIdentity={summary['exportIdentityOkCount']}/15",f"rootExact={summary['rootExactCount']}/15",f"sceneLinked={summary['sceneLinkedCount']}/15",f"unresolvedMesh={summary['unresolvedMeshLinkCount']}",f"unresolvedMaterial={summary['unresolvedMaterialLinkCount']}",f"unresolvedTexture={summary['unresolvedTextureLinkCount']}",flush=True)
print('PHASE54_REPORT',reportp,flush=True)
PYEOF

python "$PY" "$P47" "$P49" "$P52" "$SRC" "$WEB49" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"
rm -f "$PY"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record authoritative current15 export and scene index"
  git push origin "$BRANCH"
fi
printf 'PHASE54_DONE report=%s\n' "$REPORT"
