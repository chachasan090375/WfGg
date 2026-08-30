#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — targeted current-install locator for LuaUIFormLogic.
# Scope is deliberately narrow:
#   1) exact Formation-family asset paths in current gameres catalog,
#   2) their direct dependent bundles,
#   3) direct dependencies required to resolve serialized PPtrs.
# It then looks only for MonoScript className == LuaUIFormLogic and MonoBehaviours
# referencing that exact MonoScript. No global bundle scan and no candidate promotion.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-luauiformlogic-current-install-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V1.txt"
UNITY_VERSION="2019.4.41f1"
TARGET_ASSET='Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab'

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent: $GAMERES"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$GAMERES" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" "$TARGET_ASSET" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import hashlib,json,re,struct,sys,zipfile
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION=sys.argv[5]
gameres=Path(sys.argv[1]); local=Path(sys.argv[2]); out=Path(sys.argv[3]); report=Path(sys.argv[4]); target_asset=sys.argv[6]; apks=[Path(x) for x in sys.argv[7:]]
text=gameres.read_text('utf-8',errors='replace')

# ---------- canonical current gameres catalog ----------
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end(); n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M); e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1); dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,n=ln.split(',',2); paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
    except:pass
bundles={}; asset_to_bid={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); rec={'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':[x for x in p[6].split('|') if x],'aliasName':p[7]}
        rec['assetPaths']=[paths[x] for x in rec['assetPathIds'] if x in paths]; bundles[bid]=rec
        for ap in rec['assetPaths']:asset_to_bid[ap]=bid
    except:pass

target_bid=asset_to_bid.get(target_asset)
if target_bid is None: raise SystemExit('TARGET_ASSET_NOT_IN_CURRENT_GAMERES')
terms=('uiheropvpformation','heropvpformation','pvpformation')
family_paths=[]; family_bids=set()
for bid,b in bundles.items():
    hits=[p for p in b.get('assetPaths',[]) if any(t in p.lower() for t in terms)]
    if hits:
        family_bids.add(bid); family_paths += [{'bundleId':bid,'assetPath':p} for p in hits]
family_bids.add(int(target_bid))
# direct dependents only: a parent bundle that directly references a Formation-family bundle.
direct_dependents={bid for bid,b in bundles.items() if set(b.get('dependencyBundleIds',[])) & family_bids}
seed_bids=set(family_bids)|direct_dependents
# direct deps are loaded only for exact PPtr resolution, not because they are considered Formation evidence.
selected=set(seed_bids)
for bid in list(seed_bids): selected.update(bundles.get(bid,{}).get('dependencyBundleIds',[]))
selected=sorted(selected)
MAX_SELECTED=160
if len(selected)>MAX_SELECTED:
    result={'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V1','aborted':True,'reason':'targeted_selection_exceeds_safety_cap','counts':{'familyPaths':len(family_paths),'familyBundles':len(family_bids),'directDependents':len(direct_dependents),'selected':len(selected)},'selectedBundleIds':selected,'guardrails':{'globalBundleScan':False,'candidatePromotion':False,'apkReadOnly':True,'mainUntouched':True,'previewUntouched':True}}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    report.write_text('WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V1\n\nABORTED targeted selection exceeds safety cap\nselected='+str(len(selected))+' cap='+str(MAX_SELECTED)+'\n','utf-8')
    print('LUAUIFORM_LOCATOR_ABORT selected',len(selected),'cap',MAX_SELECTED); raise SystemExit(3)

# ---------- exact current APK offset-table carving ----------
def read7(buf,pos):
    outv=0; shift=0
    while True:
        x=buf[pos]; pos+=1; outv|=(x&0x7f)<<shift
        if not x&0x80:return outv,pos
        shift+=7

def parse_offsets(buf):
    pos=0; fc=struct.unpack_from('<I',buf,pos)[0]; pos+=4; groups=[]
    for gi in range(fc):
        ln,pos=read7(buf,pos); frag=buf[pos:pos+ln].decode('utf-8','replace'); pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0]; pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0]; pos+=4; rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos); name=buf[pos:pos+ln].decode('utf-8','replace'); pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0]; pos+=8; rows.append((name,int(off)))
        groups.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return groups

def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())
tables={'logical':[],'alias':[]}; physical=[]
for apk in apks:
    with zipfile.ZipFile(apk) as z:
        ns=set(z.namelist())
        for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
            if entry in ns:
                for g in parse_offsets(z.read(entry)): tables[kind].append({**g,'tableApk':str(apk),'tableEntry':entry})
        for n in z.namelist():
            lo=n.lower()
            if 'assets/assetbundles/' in lo and 'bundlefragment' in lo and lo.endswith('.bytes'):
                physical.append({'apk':str(apk),'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})

def map_physical(g):
    nf=norm(g.get('fragment','')); gi=int(g.get('group',0)); rank=[]
    for p in physical:
        score=0; nb=norm(p['base']); ns=norm(p['stem'])
        if nf and (nf==nb or nf==ns):score=100
        elif nf and (nf in nb or nb in nf or nf in ns or ns in nf):score=80
        if re.search(rf'fragment0*{gi}(?:\D|$)',p['base'],re.I):score=max(score,60)
        if p['apk']==g.get('tableApk'):score+=5
        if score:rank.append((score,p))
    if not rank:return None
    rank.sort(key=lambda x:(-x[0],x[1]['apk'],x[1]['entry'])); best=rank[0][0]; tops=[p for s,p in rank if s==best]
    return tops[0] if len({(p['apk'],p['entry']) for p in tops})==1 else None

def row_matches(kind,name):
    out=[]
    for g in tables[kind]:
        rows=sorted(g['rows'],key=lambda x:x[1])
        for i,(n,off) in enumerate(rows):
            if n!=name:continue
            phys=map_physical(g); end=rows[i+1][1] if i+1<len(rows) else (phys['size'] if phys else None)
            if phys and end is not None and end>off: out.append({'offset':off,'end':end,'spanBytes':end-off,'physical':phys,'group':g['group'],'fragment':g['fragment']})
    ded={}
    for r in out:
        p=r['physical']; ded[(p['apk'],p['entry'],r['offset'],r['end'])]=r
    return list(ded.values())

def location(rec):
    lm=row_matches('logical',rec['logicalName']); am=row_matches('alias',rec.get('aliasName')) if rec.get('aliasName') else []
    if not lm:return None,'logical_row_not_found'
    if am:
        keep=[]
        for l in lm:
            lp=l['physical']
            for a in am:
                ap=a['physical']
                if a['offset']==l['offset'] and ap['apk']==lp['apk'] and ap['entry']==lp['entry']:keep.append(l);break
        lm=keep
    coords={(x['physical']['apk'],x['physical']['entry'],x['offset'],x['spanBytes']) for x in lm}
    if len(coords)!=1:return None,'ambiguous_or_alias_mismatch'
    return lm[0],None

bundle_dir=local/'bundles'; bundle_dir.mkdir(parents=True,exist_ok=True)
carved=[]; unresolved=[]
for bid in selected:
    rec=bundles.get(bid)
    if not rec: unresolved.append({'bundleId':bid,'reason':'not_in_gameres'}); continue
    dst=bundle_dir/f'bundle-{bid}.bundle'
    loc,err=location(rec)
    if not loc: unresolved.append({'bundleId':bid,'reason':err}); continue
    span=int(loc['spanBytes']); declared=int(rec.get('declaredBytes') or 0); n=declared if 0<declared<=span else span
    try:
        p=loc['physical']
        with zipfile.ZipFile(p['apk']) as z,z.open(p['entry'],'r') as src,dst.open('wb') as fh:
            try:src.seek(int(loc['offset']))
            except Exception:
                left=int(loc['offset'])
                while left:
                    c=src.read(min(left,1024*1024));
                    if not c:raise EOFError('offset EOF')
                    left-=len(c)
            left=n
            while left:
                c=src.read(min(left,1024*1024));
                if not c:raise EOFError('bundle EOF')
                fh.write(c); left-=len(c)
        if dst.read_bytes()[:7]!=b'UnityFS': raise ValueError('invalid UnityFS signature')
        carved.append({'bundleId':bid,'path':str(dst),'bytes':dst.stat().st_size,'logicalName':rec['logicalName'],'selectionRole':('formation_family' if bid in family_bids else 'direct_dependent' if bid in direct_dependents else 'resolution_dependency')})
    except Exception as e:
        dst.unlink(missing_ok=True); unresolved.append({'bundleId':bid,'reason':f'{type(e).__name__}:{e}'})

# ---------- exact serialized identity inspection ----------
files=[x['path'] for x in carved]
if not files: raise SystemExit('NO_TARGETED_BUNDLES_CARVED')
env=UnityPy.load(*files)
objects=list(env.objects)

def af_name(af):
    return str(getattr(af,'name',None) or getattr(af,'path',None) or '')
def obj_key(o):return (af_name(o.assets_file),int(o.path_id))
obj_by_key={obj_key(o):o for o in objects}
af_names=sorted({k[0] for k in obj_by_key})

def external_path(af,file_id):
    exts=getattr(af,'externals',None) or []
    i=int(file_id)-1
    if i<0 or i>=len(exts):return None
    e=exts[i]
    return str(getattr(e,'path',None) or getattr(e,'name',None) or '')
def resolve_key(af,pp):
    if not isinstance(pp,dict):return None
    fid=pp.get('m_FileID',pp.get('fileID',pp.get('fileId',0))); pid=pp.get('m_PathID',pp.get('pathID',pp.get('pathId',0)))
    try:fid=int(fid or 0); pid=int(pid or 0)
    except:return None
    if not pid:return None
    if fid==0:return (af_name(af),pid)
    ep=external_path(af,fid)
    if not ep:return None
    base=Path(ep).name.lower(); matches=[n for n in af_names if Path(n).name.lower()==base or n.lower()==ep.lower()]
    return (matches[0],pid) if len(matches)==1 else None

def safe_tree(o):
    try:return o.read_typetree()
    except:return None

exact_scripts=[]; exact_script_keys=set(); tree_cache={}
for o in objects:
    if str(o.type.name)!='MonoScript':continue
    t=safe_tree(o); tree_cache[obj_key(o)]=t
    if not isinstance(t,dict):continue
    cls=str(t.get('m_ClassName') or '')
    if cls=='LuaUIFormLogic':
        k=obj_key(o); exact_script_keys.add(k); exact_scripts.append({'assetsFile':k[0],'pathID':k[1],'className':cls,'namespace':t.get('m_Namespace'),'assemblyName':t.get('m_AssemblyName'),'name':t.get('m_Name')})

# Pre-build container path lookup where UnityPy exposes exact object readers/PPtrs.
container_paths=defaultdict(list)
for p,v in (getattr(env,'container',{}) or {}).items():
    r=v
    if not hasattr(r,'assets_file'):
        for m in ('get_obj','deref'):
            fn=getattr(r,m,None)
            if callable(fn):
                try:
                    rr=fn();
                    if rr is not None:r=rr;break
                except:pass
    if hasattr(r,'assets_file'):
        container_paths[obj_key(r)].append(str(p))

matching_behaviours=[]; exact_text_refs=[]; unresolved_pptrs=[]

def walk_pptr(x,path='$'):
    if isinstance(x,dict):
        if ('m_PathID' in x or 'pathID' in x or 'pathId' in x) and ('m_FileID' in x or 'fileID' in x or 'fileId' in x):
            yield path,x
        for k,v in x.items():
            if isinstance(v,(dict,list)): yield from walk_pptr(v,path+'.'+str(k))
    elif isinstance(x,list):
        for i,v in enumerate(x):
            if isinstance(v,(dict,list)): yield from walk_pptr(v,f'{path}[{i}]')

for o in objects:
    if str(o.type.name)!='MonoBehaviour':continue
    t=safe_tree(o); tree_cache[obj_key(o)]=t
    if not isinstance(t,dict):continue
    sk=resolve_key(o.assets_file,t.get('m_Script'))
    if sk not in exact_script_keys:continue
    k=obj_key(o); row={'assetsFile':k[0],'pathID':k[1],'scriptTarget':{'assetsFile':sk[0],'pathID':sk[1]},'containerPaths':container_paths.get(k,[]),'gameObject':None,'fields':sorted(t.keys())}
    gok=resolve_key(o.assets_file,t.get('m_GameObject'))
    if gok and gok in obj_by_key:
        gt=safe_tree(obj_by_key[gok]); row['gameObject']={'assetsFile':gok[0],'pathID':gok[1],'name':(gt or {}).get('m_Name'),'containerPaths':container_paths.get(gok,[])}
    for fp,pp in walk_pptr(t):
        if fp.endswith('.m_Script') or fp.endswith('.m_GameObject'):continue
        rk=resolve_key(o.assets_file,pp)
        if not rk: unresolved_pptrs.append({'from':k,'fieldPath':fp,'pptr':pp}); continue
        to=obj_by_key.get(rk)
        typ=str(to.type.name) if to else None
        if typ=='TextAsset':
            tt=safe_tree(to) or {}; raw=tt.get('m_Script','')
            if isinstance(raw,str): b=raw.encode('utf-8','replace')
            elif isinstance(raw,(bytes,bytearray)): b=bytes(raw)
            else:b=b''
            ref={'from':{'assetsFile':k[0],'pathID':k[1]},'fieldPath':fp,'to':{'assetsFile':rk[0],'pathID':rk[1]},'name':tt.get('m_Name'),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest() if b else None,'containerPaths':container_paths.get(rk,[])}
            exact_text_refs.append(ref)
    matching_behaviours.append(row)

if exact_text_refs: next_strategy='inspect_exact_luauiformlogic_textasset_and_parent_prefab'
elif matching_behaviours: next_strategy='inspect_exact_luauiformlogic_component_fields_and_unresolved_pptrs'
elif exact_scripts: next_strategy='expand_only_direct_dependents_of_exact_script_bundle_identity'
else: next_strategy='targeted_stage2_locator_needed_no_global_scan'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V1',
 'target':{'assetPath':target_asset,'bundleId':target_bid,'monoScriptClassName':'LuaUIFormLogic'},
 'selection':{'terms':list(terms),'familyAssetPaths':family_paths,'familyBundleIds':sorted(family_bids),'directDependentBundleIds':sorted(direct_dependents),'selectedBundleIds':selected,'maxSelected':MAX_SELECTED},
 'counts':{'familyAssetPaths':len(family_paths),'familyBundles':len(family_bids),'directDependents':len(direct_dependents),'selectedBundles':len(selected),'carvedBundles':len(carved),'unresolvedBundles':len(unresolved),'objectsLoaded':len(objects),'exactLuaUIFormLogicMonoScripts':len(exact_scripts),'exactLuaUIFormLogicMonoBehaviours':len(matching_behaviours),'exactTextAssetRefs':len(exact_text_refs),'unresolvedComponentPPtrs':len(unresolved_pptrs)},
 'carved':carved,'unresolvedBundles':unresolved,'exactMonoScripts':exact_scripts,'matchingMonoBehaviours':matching_behaviours,'exactTextAssetRefs':exact_text_refs,'unresolvedComponentPPtrs':unresolved_pptrs[:300],
 'conclusion':{'nextStrategy':next_strategy,'rule':'Only exact MonoScript className and exact serialized PPtr resolution are promoted. Formation-family names are selection scope only.'},
 'guardrails':{'apkReadOnly':True,'globalBundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True,'writesOnlyLocalLabAndMetadata':True}
}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V1','',
 f"familyPaths={len(family_paths)} familyBundles={len(family_bids)} directDependents={len(direct_dependents)} selected={len(selected)} carved={len(carved)} unresolvedBundles={len(unresolved)}",
 f"objectsLoaded={len(objects)} exactMonoScripts={len(exact_scripts)} exactMonoBehaviours={len(matching_behaviours)} exactTextAssetRefs={len(exact_text_refs)} unresolvedComponentPPtrs={len(unresolved_pptrs)}",
 f"nextStrategy={next_strategy}",'','FORMATION-FAMILY ASSET PATHS']
for x in family_paths[:120]: lines.append(f"  bundle={x['bundleId']} {x['assetPath']}")
lines += ['','EXACT LUAUIFORMLOGIC MONOSCRIPTS']
if exact_scripts:
    for x in exact_scripts: lines.append(f"  assetsFile={x['assetsFile']} pathID={x['pathID']} class={x['className']} namespace={x.get('namespace')} assembly={x.get('assemblyName')}")
else:lines.append('  NONE')
lines += ['','EXACT LUAUIFORMLOGIC MONOBEHAVIOURS']
if matching_behaviours:
    for x in matching_behaviours:
        go=x.get('gameObject') or {}; lines.append(f"  assetsFile={x['assetsFile']} pathID={x['pathID']} gameObject={go.get('name')} containerPaths={','.join(x.get('containerPaths') or go.get('containerPaths') or []) or '-'}")
        lines.append('    fields='+','.join(x.get('fields',[])))
else:lines.append('  NONE')
lines += ['','EXACT TEXTASSET REFS FROM LUAUIFORMLOGIC']
if exact_text_refs:
    for x in exact_text_refs: lines.append(f"  field={x['fieldPath']} name={x.get('name')} bytes={x.get('bytes')} sha256={x.get('sha256')} target={x['to']['assetsFile']}#{x['to']['pathID']} containerPaths={','.join(x.get('containerPaths') or []) or '-'}")
else:lines.append('  NONE')
lines += ['','NEXT '+next_strategy,
 'RULE: Formation-family names select the narrow bundle set only; they are not runtime proof.',
 'RULE: exact MonoScript className + exact serialized PPtr only. No candidate promotion.',
 'RULE: current APK read-only; no global bundle scan; main and preview untouched.']
report.write_text('\n'.join(lines)+'\n','utf-8')
print('LUAUIFORM_LOCATOR_OK',f'familyBundles={len(family_bids)}',f'directDependents={len(direct_dependents)}',f'selected={len(selected)}',f'carved={len(carved)}',f'exactScripts={len(exact_scripts)}',f'exactBehaviours={len(matching_behaviours)}',f'textRefs={len(exact_text_refs)}')
print('LUAUIFORM_LOCATOR_NEXT',next_strategy)
print('LUAUIFORM_LOCATOR_JSON',out)
print('LUAUIFORM_LOCATOR_REPORT',report)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: locate exact LuaUIFormLogic in current Formation scope"
  git push origin "$BRANCH"
fi
printf '\n=== LUAUIFORMLOGIC CURRENT INSTALL LOCATOR TERMINE ===\nJSON: %s\nREPORT: %s\n' "$OUT" "$REPORT"
