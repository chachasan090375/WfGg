#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact serialized-object/PPtr audit for the real Formation panel.
# Targeted: extracts only the bundle that contains UIHeroPVPFormationPanel.prefab.
# No broad AssetBundle scan. No guessed links. External PPtrs remain unresolved until proven.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
IDX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
TARGET="Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-panel-serialized-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-panel-serialized-pptr-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PANEL_SERIALIZED_PPTR.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-formation-panel-serialized-pptr.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$IDX" ]] || fail "graphics master index absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$LOCAL"/*.bundle

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict,deque
import base64,contextlib,hashlib,io,json,sys,time,zipfile

idxp=Path(sys.argv[1]); target=sys.argv[2]; local=Path(sys.argv[3]); outp=Path(sys.argv[4]); reportp=Path(sys.argv[5]); unity=sys.argv[6]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity
idx=json.loads(idxp.read_text('utf-8')); t0=time.time()

bundle_id=idx.get('lookup',{}).get('assetPathToBundleId',{}).get(target)
if bundle_id is None: raise SystemExit('TARGET_ASSET_NOT_INDEXED '+target)
byid={int(x['bundleId']):x for x in idx.get('bundles',[])}
b=byid.get(int(bundle_id))
if not b: raise SystemExit('TARGET_BUNDLE_RECORD_MISSING')
loc=b.get('preferredExtraction') or {}
required=('physicalApk','fragmentEntry','offset','spanBytes')
missing=[x for x in required if loc.get(x) in (None,'')]
if missing: raise SystemExit('TARGET_EXTRACTION_UNRESOLVED '+','.join(missing))

apk_by_base={str(x.get('basename')):Path(str(x.get('path'))) for x in idx.get('source',{}).get('installedApks',[]) if x.get('basename') and x.get('path')}
apk=apk_by_base.get(str(loc['physicalApk']))
if apk is None or not apk.is_file():
    p=Path(str(loc['physicalApk']))
    if p.is_file(): apk=p
if apk is None or not apk.is_file(): raise SystemExit('PHYSICAL_APK_NOT_FOUND '+str(loc['physicalApk']))

start=int(loc['offset']); span=int(loc['spanBytes'])
if span<=0 or span>250_000_000: raise SystemExit(f'UNSAFE_TARGET_SPAN {span}')
dest=local/f'bundle-{bundle_id}.bundle'
with zipfile.ZipFile(apk) as z, z.open(str(loc['fragmentEntry'])) as f:
    left=start
    while left:
        c=f.read(min(left,1024*1024))
        if not c: raise SystemExit('FRAGMENT_OFFSET_EOF')
        left-=len(c)
    blob=f.read(span)
if len(blob)!=span: raise SystemExit(f'FRAGMENT_SHORT_READ {len(blob)}/{span}')
dest.write_bytes(blob)
print('FORMATION_PPTR_EXTRACTED',f'bundle={bundle_id}',f'bytes={span}',dest)

sink=io.StringIO()
with contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
    env=UnityPy.load(str(dest))
readers=list(env.objects)
print('FORMATION_PPTR_UNITYPY',f'objects={len(readers)}',f'container={len(getattr(env,"container",{}) or {})}')

def pidof(x):
    if x is None:return None
    for o in (x,getattr(x,'object_reader',None),getattr(x,'reader',None)):
        if o is None:continue
        for k in ('path_id','m_PathID'):
            try:
                v=getattr(o,k,None)
                if v is not None:return int(v)
            except:pass
    return None

def fileobj(r):
    for k in ('assets_file','assetsfile'):
        v=getattr(r,k,None)
        if v is not None:return v
    return None

def filekey(r):
    af=fileobj(r)
    if af is None:return 'unknown-file'
    for k in ('name','path','file_name'):
        v=getattr(af,k,None)
        if v:return str(v)
    return af.__class__.__name__

def typename(r):
    try:return str(r.type.name)
    except:return str(getattr(r,'type','Unknown'))

def jsonable(x,depth=0):
    if depth>80:return {'__truncated_depth__':depth}
    if x is None or isinstance(x,(bool,int,float,str)):return x
    if isinstance(x,bytes):return {'__bytes_b64__':base64.b64encode(x).decode('ascii'),'bytes':len(x)}
    if isinstance(x,(list,tuple)):return [jsonable(v,depth+1) for v in x]
    if isinstance(x,dict):return {str(k):jsonable(v,depth+1) for k,v in x.items()}
    try:
        if hasattr(x,'value') and isinstance(x.value,(bool,int,float,str)):return x.value
    except:pass
    return str(x)

def treeof(r):
    try:return jsonable(r.read_typetree())
    except Exception:
        try:
            o=r.read(); d={}
            for k in ('m_Name','m_IsActive','m_Layer','m_Tag','m_Enabled'):
                if hasattr(o,k):d[k]=jsonable(getattr(o,k))
            return d
        except:return {}

def namefrom(tree):
    if isinstance(tree,dict):
        for k in ('m_Name','name'):
            v=tree.get(k)
            if isinstance(v,str) and v:return v
    return ''

def pptrs(x,path='$'):
    out=[]
    if isinstance(x,dict):
        if 'm_FileID' in x and 'm_PathID' in x:
            try:out.append({'propertyPath':path,'fileID':int(x.get('m_FileID',0)),'pathID':int(x.get('m_PathID',0))})
            except:pass
        for k,v in x.items():out.extend(pptrs(v,path+'.'+str(k)))
    elif isinstance(x,list):
        for i,v in enumerate(x):out.extend(pptrs(v,f'{path}[{i}]'))
    return out

# Exact container lookup only; case-insensitive equality is accepted, substring matching is not.
container=getattr(env,'container',{}) or {}
root_reader=None; container_key=None
for k,v in container.items():
    if str(k)==target:
        container_key=str(k);root_reader=v;break
if root_reader is None:
    for k,v in container.items():
        if str(k).lower()==target.lower():
            container_key=str(k);root_reader=v;break
if root_reader is None:
    near=sorted(str(k) for k in container if 'UIHeroPVPFormationPanel'.lower() in str(k).lower())
    raise SystemExit('TARGET_CONTAINER_NOT_FOUND candidates='+json.dumps(near[:20],ensure_ascii=False))

root_pid=pidof(root_reader); root_fk=filekey(root_reader)
print('FORMATION_PPTR_ROOT',f'container={container_key}',f'file={root_fk}',f'pathId={root_pid}',f'type={typename(root_reader)}')

# Reader lookup is file-scoped because PathIDs are not globally unique.
lookup={}
for r in readers:
    p=pidof(r)
    if p is not None:lookup[(filekey(r),p)]=r

# Capture external file table for exact fileID interpretation.
external_tables={}
for r in readers:
    fk=filekey(r)
    if fk in external_tables:continue
    af=fileobj(r); rows=[]
    for i,e in enumerate(list(getattr(af,'externals',[]) or []),1):
        rec={'fileID':i}
        for k in ('path','name','file_name','guid','type'):
            try:
                v=getattr(e,k,None)
                if v not in (None,''):rec[k]=str(v)
            except:pass
        rows.append(rec)
    external_tables[fk]=rows

# Reachability follows ONLY serialized internal PPtrs (fileID=0) from the exact prefab root.
q=deque([(root_fk,int(root_pid))]); seen=set(); objects=[]; edges=[]; external_refs=[]
MAX_OBJECTS=12000
while q and len(seen)<MAX_OBJECTS:
    key=q.popleft()
    if key in seen:continue
    r=lookup.get(key)
    if r is None:continue
    seen.add(key); fk,pid=key; tree=treeof(r); typ=typename(r); nm=namefrom(tree)
    canonical=json.dumps(tree,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    node_id=f'uobj:{bundle_id}:{fk}:{pid}'
    refs=pptrs(tree)
    objects.append({'id':node_id,'bundleId':bundle_id,'serializedFile':fk,'pathId':pid,'type':typ,'name':nm,'treeSha256':hashlib.sha256(canonical).hexdigest(),'tree':tree,'pptrCount':len(refs)})
    for ref in refs:
        fid=int(ref['fileID']); tpid=int(ref['pathID'])
        if tpid==0:continue
        er={'from':node_id,'propertyPath':ref['propertyPath'],'fileID':fid,'pathID':tpid,'source':'serialized-pptr','confidence':'serialized_exact','renderEligible':True if fid==0 else False}
        if fid==0:
            tr=lookup.get((fk,tpid))
            target_id=f'uobj:{bundle_id}:{fk}:{tpid}'
            er.update({'to':target_id,'resolution':'internal_exact'})
            if tr is not None:
                er['targetType']=typename(tr)
                tt=treeof(tr); er['targetName']=namefrom(tt)
                q.append((fk,tpid))
            else:
                er['resolution']='internal_pathid_missing'
                er['renderEligible']=False
        else:
            ext=None
            tab=external_tables.get(fk,[])
            if 1<=fid<=len(tab):ext=tab[fid-1]
            er.update({'resolution':'external_exact_unresolved','externalFile':ext})
            external_refs.append(er.copy())
        edges.append(er)

truncated=bool(q)
# Compact exact hierarchy summary from serialized objects. No guessed parent/child inference beyond fields themselves.
type_counts=Counter(x['type'] for x in objects)
name_counts=Counter(x['name'] for x in objects if x['name'])
ext_groups=defaultdict(lambda:{'count':0,'pathIDs':set(),'properties':set()})
for e in external_refs:
    key=json.dumps(e.get('externalFile'),ensure_ascii=False,sort_keys=True)
    g=ext_groups[key];g['count']+=1;g['pathIDs'].add(e['pathID']);g['properties'].add(e['propertyPath'])
ext_summary=[]
for k,g in ext_groups.items():
    ext_summary.append({'externalFile':json.loads(k) if k!='null' else None,'referenceCount':g['count'],'pathIDs':sorted(g['pathIDs']),'properties':sorted(g['properties'])[:200]})

res={
 'format':'WFGG_LASTWAR_SERIALIZED_PPTR_AUDIT_V1',
 'target':{'assetPath':target,'bundleId':bundle_id,'logicalName':b.get('logicalName'),'aliasName':b.get('aliasName'),'containerKey':container_key},
 'extraction':{'physicalApk':apk.name,'fragmentEntry':loc.get('fragmentEntry'),'offset':start,'spanBytes':span,'identity':loc.get('identity'),'group':loc.get('group')},
 'root':{'serializedFile':root_fk,'pathId':root_pid,'type':typename(root_reader),'nodeId':f'uobj:{bundle_id}:{root_fk}:{root_pid}'},
 'counts':{'bundleObjects':len(readers),'reachableSerializedObjects':len(objects),'serializedEdges':len(edges),'externalRefs':len(external_refs),'externalFiles':len(ext_summary)},
 'truncated':truncated,
 'maxObjects':MAX_OBJECTS,
 'typeCounts':dict(type_counts),
 'namedObjects':sorted([{'name':n,'count':c} for n,c in name_counts.items()],key=lambda x:(-x['count'],x['name']))[:500],
 'externalTables':external_tables,
 'externalReferenceSummary':ext_summary,
 'objects':objects,
 'serializedEdges':edges,
 'fidelitySemantics':{
   'serialized_exact':'The source object/property/fileID/pathID is read directly from Unity serialized data.',
   'internal_exact':'The referenced PathID was resolved in the same serialized file.',
   'external_exact_unresolved':'The serialized reference is exact, but its target object is NOT render-certified until the external dependency is loaded and PathID resolved.',
   'renderEligibleRule':'Only fully resolved object-level links may later participate in CERTIFIED_PIXEL_FAITHFUL reconstruction.'
 },
 'guardrails':{'singleTargetBundleOnly':True,'broadBundleScan':False,'noNameBasedVisualLinks':True,'noGuessedDefaults':True,'mainUntouched':True},
 'elapsedSeconds':round(time.time()-t0,3)
}
outp.write_text(json.dumps(res,ensure_ascii=False,separators=(',',':'))+'\n','utf-8')

lines=['WfGg Last War — FORMATION PANEL SERIALIZED PPtr AUDIT','',f'target={target}',f'bundleId={bundle_id}',f'container={container_key}',f'rootFile={root_fk} rootPathId={root_pid} rootType={typename(root_reader)}',f'bundleObjects={len(readers)} reachable={len(objects)} edges={len(edges)} externalRefs={len(external_refs)} externalFiles={len(ext_summary)} truncated={truncated}',f'elapsedSeconds={res["elapsedSeconds"]}','', 'TYPE_COUNTS '+json.dumps(dict(type_counts),ensure_ascii=False),'']
for x in ext_summary[:80]:lines.append('EXTERNAL '+json.dumps(x,ensure_ascii=False))
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_SERIALIZED_PPTR_OK',f'bundle={bundle_id}',f'reachable={len(objects)}',f'edges={len(edges)}',f'externalRefs={len(external_refs)}',f'externalFiles={len(ext_summary)}',f'truncated={truncated}',f'elapsed={res["elapsedSeconds"]}')
print('FORMATION_SERIALIZED_PPTR_JSON',outp)
print('FORMATION_SERIALIZED_PPTR_REPORT',reportp)
PYEOF

python "$PY" "$IDX" "$TARGET" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION"

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: map exact Formation serialized PPtrs"
fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION SERIALIZED PPtr AUDIT TERMINE ===' "JSON: $OUT" "Rapport: $REPORT" 'Aucun lien externe non resolu n est promu en recette de rendu.'
