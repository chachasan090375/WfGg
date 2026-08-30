#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — LuaUIFormLogic current-install locator V3.
# V2 had zero direct dependents, so no group was ever inspected.
# V3 does two exact/narrow things only:
#   1) inspect the already-proven 195-bundle target closure itself for MonoScript.m_ClassName == LuaUIFormLogic;
#   2) compute each exact catalog PVPFormation-family bundle closure and its delta vs that proven baseline.
# No new APK read, no bundle carving, no global scan, no candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
BASE_BUNDLE_DIR="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v2/bundles"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v3.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V3.txt"
UNITY_VERSION="2019.4.41f1"
TARGET_ASSET='Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab'

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent: $GAMERES"
[[ -d "$BASE_BUNDLE_DIR" ]] || fail "socle Formation local absent: $BASE_BUNDLE_DIR"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$GAMERES" "$BASE_BUNDLE_DIR" "$OUT" "$REPORT" "$UNITY_VERSION" "$TARGET_ASSET" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,deque
import json,re,sys
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION=sys.argv[5]
gameres=Path(sys.argv[1]); base_dir=Path(sys.argv[2]); out_p=Path(sys.argv[3]); report_p=Path(sys.argv[4]); target_asset=sys.argv[6]
text=gameres.read_text('utf-8',errors='replace')

# ---------- current canonical gameres catalog ----------
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
if target_bid is None:raise SystemExit('TARGET_ASSET_NOT_IN_CURRENT_GAMERES')
target_bid=int(target_bid)

def closure(seed):
    seen=set();q=deque([int(seed)])
    while q:
        bid=q.popleft()
        if bid in seen:continue
        seen.add(bid)
        for d in bundles.get(bid,{}).get('dependencyBundleIds',[]):
            if d not in seen:q.append(d)
    return seen

baseline=closure(target_bid)
missing=[bid for bid in sorted(baseline) if not (base_dir/f'bundle-{bid}.bundle').is_file()]
if missing:
    result={'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V3','aborted':True,'reason':'proven_baseline_bundle_files_missing','targetBundleId':target_bid,'baselineClosureCount':len(baseline),'missingBaselineBundleIds':missing[:300]}
    out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    report_p.write_text('WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V3\n\nABORTED proven baseline bundle files missing\nmissing='+str(len(missing))+' baseline='+str(len(baseline))+'\n','utf-8')
    print('LUAUIFORM_V3_ABORT missingBaseline',len(missing));raise SystemExit(3)

# Exact current catalog path scope. Path naming is a selection heuristic only, never runtime evidence.
terms=('uiheropvpformation','heropvpformation','pvpformation')
family=[]
for bid,b in bundles.items():
    hits=[p for p in b.get('assetPaths',[]) if any(t in p.lower() for t in terms)]
    if hits:
        c=closure(bid);delta=sorted(c-baseline)
        family.append({'bundleId':bid,'assetPaths':hits,'closureCount':len(c),'baselineOverlapCount':len(c&baseline),'deltaCount':len(delta),'deltaBundleIds':delta})
if not any(x['bundleId']==target_bid for x in family):
    family.append({'bundleId':target_bid,'assetPaths':[target_asset],'closureCount':len(baseline),'baselineOverlapCount':len(baseline),'deltaCount':0,'deltaBundleIds':[]})
family.sort(key=lambda x:(x['deltaCount'],x['bundleId']))

# ---------- inspect proven baseline itself ----------
files=[str(base_dir/f'bundle-{bid}.bundle') for bid in sorted(baseline)]
env=UnityPy.load(*files)
objects=list(env.objects)

def af_name(af):return str(getattr(af,'name',None) or getattr(af,'path',None) or '')
def key(o):return (af_name(o.assets_file),int(o.path_id))
obj_by_key={key(o):o for o in objects}; af_names=sorted({k[0] for k in obj_by_key})

def safe_tree(o):
    try:return o.read_typetree()
    except:return None

def pptr_vals(pp):
    if isinstance(pp,dict):
        fid=pp.get('m_FileID',pp.get('fileID',pp.get('fileId',0)));pid=pp.get('m_PathID',pp.get('pathID',pp.get('pathId',0)))
    else:
        fid=getattr(pp,'file_id',getattr(pp,'m_FileID',0));pid=getattr(pp,'path_id',getattr(pp,'m_PathID',0))
    try:return int(fid or 0),int(pid or 0)
    except:return 0,0

def external_path(af,fid):
    exts=getattr(af,'externals',None) or [];i=int(fid)-1
    if i<0 or i>=len(exts):return None
    e=exts[i];return str(getattr(e,'path',None) or getattr(e,'name',None) or '')

def resolve(af,pp):
    fid,pid=pptr_vals(pp)
    if not pid:return None
    if fid==0:return obj_by_key.get((af_name(af),pid))
    ep=external_path(af,fid)
    if not ep:return None
    base=Path(ep).name.lower();matches=[n for n in af_names if n.lower()==ep.lower() or Path(n).name.lower()==base or n.lower().endswith('/'+base)]
    if len(matches)!=1:return None
    return obj_by_key.get((matches[0],pid))

container_paths=defaultdict(list)
for p,v in (getattr(env,'container',{}) or {}).items():
    r=v
    if not hasattr(r,'assets_file'):
        for meth in ('get_obj','deref'):
            fn=getattr(r,meth,None)
            if callable(fn):
                try:
                    rr=fn()
                    if rr is not None:r=rr;break
                except:pass
    if hasattr(r,'assets_file'):container_paths[key(r)].append(str(p))

def read_name(o,t=None):
    t=t if isinstance(t,dict) else safe_tree(o)
    if isinstance(t,dict):
        for k in ('m_Name','name'):
            if isinstance(t.get(k),str):return t[k]
    try:
        d=o.read();return str(getattr(d,'m_Name','') or getattr(d,'name','') or '')
    except:return ''

exact_scripts=[];script_keys=set();trees={}
for o in objects:
    if str(o.type.name)!='MonoScript':continue
    t=safe_tree(o);trees[key(o)]=t
    if not isinstance(t,dict):continue
    cls=str(t.get('m_ClassName') or '')
    if cls=='LuaUIFormLogic':
        k=key(o);script_keys.add(k)
        exact_scripts.append({'assetsFile':k[0],'pathID':k[1],'className':cls,'namespace':t.get('m_Namespace'),'assemblyName':t.get('m_AssemblyName'),'name':t.get('m_Name'),'containerPaths':container_paths.get(k,[])})

# Normalize arbitrary nested serialized PPtrs and resolve only exact TextAsset targets.
def walk_pptr(x,path='$'):
    if isinstance(x,dict):
        has_pid=any(k in x for k in ('m_PathID','pathID','pathId'));has_fid=any(k in x for k in ('m_FileID','fileID','fileId'))
        if has_pid and has_fid:yield path,x
        for k,v in x.items():
            if isinstance(v,(dict,list)):yield from walk_pptr(v,path+'.'+str(k))
    elif isinstance(x,list):
        for i,v in enumerate(x):
            if isinstance(v,(dict,list)):yield from walk_pptr(v,f'{path}[{i}]')

behaviours=[];text_refs=[];unresolved_script_pptr=0
if script_keys:
    for o in objects:
        if str(o.type.name)!='MonoBehaviour':continue
        t=safe_tree(o)
        if not isinstance(t,dict):continue
        scr=t.get('m_Script')
        if scr is None:continue
        so=resolve(o.assets_file,scr)
        if so is None:
            unresolved_script_pptr+=1;continue
        if key(so) not in script_keys:continue
        k=key(o);go_name='';go=t.get('m_GameObject')
        if go is not None:
            goo=resolve(o.assets_file,go)
            if goo is not None:go_name=read_name(goo)
        row={'assetsFile':k[0],'pathID':k[1],'gameObjectName':go_name,'containerPaths':container_paths.get(k,[]),'scriptTarget':{'assetsFile':key(so)[0],'pathID':key(so)[1]},'textAssets':[]}
        seen_t=set()
        for pth,pp in walk_pptr(t):
            to=resolve(o.assets_file,pp)
            if to is None or str(to.type.name)!='TextAsset':continue
            tk=key(to)
            if tk in seen_t:continue
            seen_t.add(tk);tt=safe_tree(to);name=read_name(to,tt)
            tr={'fieldPath':pth,'assetsFile':tk[0],'pathID':tk[1],'name':name,'containerPaths':container_paths.get(tk,[])}
            row['textAssets'].append(tr);text_refs.append({'behaviour':{'assetsFile':k[0],'pathID':k[1],'gameObjectName':go_name},**tr})
        behaviours.append(row)

nonzero=[x for x in family if x['deltaCount']>0]
smallest=min(nonzero,key=lambda x:(x['deltaCount'],x['bundleId'])) if nonzero else None
if text_refs:
    next_strategy='inspect_exact_luauiformlogic_textasset_source'
elif behaviours:
    next_strategy='inspect_exact_luauiformlogic_behaviour_fields_without_textasset_guessing'
elif exact_scripts:
    next_strategy='trace_exact_monoscript_usage_outside_baseline_with_family_delta_first'
elif smallest:
    next_strategy='audit_smallest_exact_formation_family_closure_delta'
else:
    next_strategy='targeted_locator_v4_generic_luauiformlogic_ui_form_prefab_required'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V3',
 'target':{'assetPath':target_asset,'bundleId':target_bid},
 'baseline':{'closureCount':len(baseline),'objectCount':len(objects),'monoScriptCount':sum(1 for o in objects if str(o.type.name)=='MonoScript'),'monoBehaviourCount':sum(1 for o in objects if str(o.type.name)=='MonoBehaviour')},
 'formationFamily':{'selectionRule':'current gameres asset path contains UIHeroPVPFormation/HeroPVPFormation/PVPFormation; scope heuristic only','bundleCount':len(family),'groups':family,'smallestNonzeroDelta':smallest},
 'exactBaselineEvidence':{'luaUIFormLogicMonoScripts':exact_scripts,'matchingMonoBehaviours':behaviours,'exactTextAssetRefs':text_refs,'unresolvedMonoBehaviourScriptPPtrs':unresolved_script_pptr},
 'counts':{'exactScripts':len(exact_scripts),'matchingBehaviours':len(behaviours),'exactTextAssetRefs':len(text_refs),'familyBundles':len(family),'familyNonzeroDeltaGroups':len(nonzero)},
 'conclusion':{'foundExactScript':bool(exact_scripts),'foundMatchingBehaviour':bool(behaviours),'foundExactTextAsset':bool(text_refs),'nextStrategy':next_strategy},
 'guardrails':{'apkAccess':False,'newBundleCarving':False,'globalBundleScan':False,'candidatePromotion':False,'baselineOnlyInspection':True,'mainUntouched':True,'previewUntouched':True}
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V3','',
 f'baselineClosure={len(baseline)} objects={len(objects)} familyBundles={len(family)} nonzeroFamilyDeltas={len(nonzero)}',
 f'exactScripts={len(exact_scripts)} matchingBehaviours={len(behaviours)} exactTextAssetRefs={len(text_refs)}',
 f'nextStrategy={next_strategy}','',
 'FORMATION FAMILY CLOSURE DELTAS']
for x in family:
    lines.append(f"  bundle={x['bundleId']} closure={x['closureCount']} overlap={x['baselineOverlapCount']} delta={x['deltaCount']}")
    for p in x['assetPaths'][:8]:lines.append('    ASSET '+p)
if smallest:
    lines += ['',f"SMALLEST NONZERO FAMILY DELTA bundle={smallest['bundleId']} delta={smallest['deltaCount']} closure={smallest['closureCount']}", '  DELTA '+(' '.join(map(str,smallest['deltaBundleIds'][:120])) or 'NONE')]
lines += ['', 'EXACT LUAUIFORMLOGIC MONOSCRIPTS']
if exact_scripts:
    for x in exact_scripts:lines.append(f"  assetsFile={x['assetsFile']} pathID={x['pathID']} class={x['className']} assembly={x.get('assemblyName')}")
else:lines.append('  NONE')
lines += ['', 'MATCHING MONOBEHAVIOURS']
if behaviours:
    for x in behaviours:
        lines.append(f"  assetsFile={x['assetsFile']} pathID={x['pathID']} gameObject={x['gameObjectName']!r} textAssets={len(x['textAssets'])}")
else:lines.append('  NONE')
lines += ['', 'EXACT TEXTASSET REFS']
if text_refs:
    for x in text_refs:
        lines.append(f"  field={x['fieldPath']} assetsFile={x['assetsFile']} pathID={x['pathID']} name={x['name']!r} behaviour={x['behaviour']['pathID']}")
else:lines.append('  NONE')
lines += ['', 'NEXT '+next_strategy,
 'RULE: catalog-path family membership is scope selection only; exact MonoScript/MonoBehaviour/TextAsset PPtrs are evidence.',
 'RULE: no APK read, no new bundle carving, no global scan, no candidate promotion, main/preview untouched.']
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('LUAUIFORM_V3_OK',f'baseline={len(baseline)}',f'family={len(family)}',f'nonzeroDelta={len(nonzero)}',f'exactScripts={len(exact_scripts)}',f'behaviours={len(behaviours)}',f'textAssets={len(text_refs)}')
if smallest:print('LUAUIFORM_V3_SMALLEST_DELTA',f"bundle={smallest['bundleId']}",f"delta={smallest['deltaCount']}",f"closure={smallest['closureCount']}")
for x in exact_scripts:print('LUAUIFORM_V3_EXACT_SCRIPT',x['assetsFile'],x['pathID'],x.get('assemblyName'))
for x in behaviours:print('LUAUIFORM_V3_EXACT_BEHAVIOUR',x['assetsFile'],x['pathID'],repr(x['gameObjectName']),f"textAssets={len(x['textAssets'])}")
for x in text_refs:print('LUAUIFORM_V3_EXACT_TEXTASSET',x['assetsFile'],x['pathID'],repr(x['name']),x['fieldPath'])
print('LUAUIFORM_V3_NEXT',next_strategy)
print('LUAUIFORM_V3_JSON',out_p)
print('LUAUIFORM_V3_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: inspect exact Formation family closures for LuaUIFormLogic"
  git push origin "$BRANCH"
fi
