#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — LuaUIFormLogic current-install locator V2.
# V1 aborted because the union of Formation-family direct dependents + their deps was 257 bundles.
# V2 does NOT raise that cap. It reuses the already-proven target dependency closure as a local baseline
# and inspects each exact direct dependent incrementally, loading only that dependent's delta.
# Exact identity only: MonoScript.m_ClassName == LuaUIFormLogic, then MonoBehaviour.m_Script PPtr to it.
# APK is read-only and only missing delta bundles are carved from exact current offset-table coordinates.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
BASE_BUNDLE_DIR="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v2/bundles"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-luauiformlogic-current-install-v2"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V2.txt"
UNITY_VERSION="2019.4.41f1"
TARGET_ASSET='Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab'

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent: $GAMERES"
[[ -d "$BASE_BUNDLE_DIR" ]] || fail "socle V4/V2 local absent: $BASE_BUNDLE_DIR"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL/bundles" "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$GAMERES" "$BASE_BUNDLE_DIR" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" "$TARGET_ASSET" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,deque
import json,re,struct,sys,zipfile
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION=sys.argv[6]
gameres=Path(sys.argv[1]); base_dir=Path(sys.argv[2]); local=Path(sys.argv[3]); out=Path(sys.argv[4]); report=Path(sys.argv[5]); target_asset=sys.argv[7]; apks=[Path(x) for x in sys.argv[8:]]
text=gameres.read_text('utf-8',errors='replace')

# ---------- current canonical gameres ----------
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
    seen=set(); q=deque([int(seed)])
    while q:
        bid=q.popleft()
        if bid in seen:continue
        seen.add(bid)
        for d in bundles.get(bid,{}).get('dependencyBundleIds',[]):
            if d not in seen:q.append(d)
    return seen

baseline=closure(target_bid)
# V4 had proven this closure and local bundle files were retained. Require exact local presence; do not silently recarve it.
missing_baseline=[bid for bid in sorted(baseline) if not (base_dir/f'bundle-{bid}.bundle').is_file()]
if missing_baseline:
    result={'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V2','aborted':True,'reason':'proven_baseline_bundle_files_missing','targetBundleId':target_bid,'baselineClosureCount':len(baseline),'missingBaselineBundleIds':missing_baseline[:200]}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    report.write_text('WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V2\n\nABORTED proven baseline bundle files missing\nmissing='+str(len(missing_baseline))+' baseline='+str(len(baseline))+'\n','utf-8')
    print('LUAUIFORM_V2_ABORT missingBaseline',len(missing_baseline)); raise SystemExit(3)

terms=('uiheropvpformation','heropvpformation','pvpformation')
family_bids=set(); family_paths=[]
for bid,b in bundles.items():
    hits=[p for p in b.get('assetPaths',[]) if any(t in p.lower() for t in terms)]
    if hits:
        family_bids.add(bid)
        family_paths.extend({'bundleId':bid,'assetPath':p} for p in hits)
family_bids.add(target_bid)
# Exact graph relation only: bundle directly depends on any Formation-family bundle.
direct_dependents=sorted(bid for bid,b in bundles.items() if bid not in family_bids and set(b.get('dependencyBundleIds',[])) & family_bids)

groups=[]; union_delta=set()
for dep in direct_dependents:
    c=closure(dep); delta=sorted(c-baseline)
    union_delta.update(delta)
    groups.append({'dependentBundleId':dep,'closureCount':len(c),'deltaCount':len(delta),'deltaBundleIds':delta,'assetPaths':bundles.get(dep,{}).get('assetPaths',[])[:80]})
# smallest delta first is an execution-order heuristic only; never evidence.
groups.sort(key=lambda x:(x['deltaCount'],x['dependentBundleId']))
MAX_TOTAL_NEW=80
MAX_GROUP_DELTA=48
if len(union_delta)>MAX_TOTAL_NEW:
    result={'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V2','aborted':True,'reason':'incremental_delta_union_exceeds_safety_cap','targetBundleId':target_bid,'baselineClosureCount':len(baseline),'directDependentCount':len(direct_dependents),'unionDeltaCount':len(union_delta),'cap':MAX_TOTAL_NEW,'groups':groups,'guardrails':{'globalBundleScan':False,'candidatePromotion':False,'apkReadOnly':True,'mainUntouched':True,'previewUntouched':True}}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    report.write_text('WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V2\n\nABORTED incremental delta union exceeds safety cap\nunionDelta='+str(len(union_delta))+' cap='+str(MAX_TOTAL_NEW)+' dependents='+str(len(direct_dependents))+' baseline='+str(len(baseline))+'\n','utf-8')
    print('LUAUIFORM_V2_ABORT unionDelta',len(union_delta),'cap',MAX_TOTAL_NEW); raise SystemExit(3)

# ---------- exact current APK offset tables; only used for missing delta bundles ----------
def read7(buf,pos):
    outv=0;shift=0
    while True:
        if pos>=len(buf):raise ValueError('7bit EOF')
        x=buf[pos];pos+=1;outv|=(x&0x7f)<<shift
        if not x&0x80:return outv,pos
        shift+=7

def parse_offsets(buf):
    pos=0; fc=struct.unpack_from('<I',buf,pos)[0];pos+=4; groups=[]
    for gi in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4; rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,int(off)))
        groups.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return groups

def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())
tables={'logical':[],'alias':[]};physical=[]
for apk in apks:
    with zipfile.ZipFile(apk) as z:
        ns=set(z.namelist())
        for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
            if entry in ns:
                for g in parse_offsets(z.read(entry)):tables[kind].append({**g,'tableApk':str(apk)})
        for n in z.namelist():
            lo=n.lower()
            if 'assets/assetbundles/' in lo and 'bundlefragment' in lo and lo.endswith('.bytes'):
                physical.append({'apk':str(apk),'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})

def map_physical(g):
    nf=norm(g.get('fragment',''));gi=int(g.get('group',0));rank=[]
    for p in physical:
        score=0;nb=norm(p['base']);ns=norm(p['stem'])
        if nf and (nf==nb or nf==ns):score=100
        elif nf and (nf in nb or nb in nf or nf in ns or ns in nf):score=80
        if re.search(rf'fragment0*{gi}(?:\D|$)',p['base'],re.I):score=max(score,60)
        if p['apk']==g.get('tableApk'):score+=5
        if score:rank.append((score,p))
    if not rank:return None
    rank.sort(key=lambda x:(-x[0],x[1]['apk'],x[1]['entry']));best=rank[0][0];tops=[p for s,p in rank if s==best]
    return tops[0] if len({(p['apk'],p['entry']) for p in tops})==1 else None

def rows(kind,name):
    out=[]
    if not name:return out
    for g in tables[kind]:
        rr=sorted(g['rows'],key=lambda x:x[1])
        for i,(n,off) in enumerate(rr):
            if n!=name:continue
            p=map_physical(g);end=rr[i+1][1] if i+1<len(rr) else (p['size'] if p else None)
            if p and end is not None and end>off:out.append({'offset':off,'end':end,'spanBytes':end-off,'physical':p})
    ded={}
    for r in out:
        p=r['physical'];ded[(p['apk'],p['entry'],r['offset'],r['end'])]=r
    return list(ded.values())

def location(rec):
    lm=rows('logical',rec['logicalName']);am=rows('alias',rec.get('aliasName')) if rec.get('aliasName') else []
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

carve_log=[];carve_errors=[]
def bundle_path(bid):
    p=base_dir/f'bundle-{bid}.bundle'
    if p.is_file():return p,'reused-proven-baseline'
    p=local/'bundles'/f'bundle-{bid}.bundle'
    if p.is_file() and p.read_bytes()[:7]==b'UnityFS':return p,'reused-v2-delta'
    rec=bundles.get(bid)
    if not rec:return None,'bundle_not_in_gameres'
    loc,err=location(rec)
    if not loc:return None,err
    span=int(loc['spanBytes']);decl=int(rec.get('declaredBytes') or 0);n=decl if 0<decl<=span else span
    try:
        ph=loc['physical'];p.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(ph['apk']) as z,z.open(ph['entry'],'r') as src,p.open('wb') as fh:
            try:src.seek(int(loc['offset']))
            except Exception:
                left=int(loc['offset'])
                while left:
                    c=src.read(min(left,1024*1024))
                    if not c:raise EOFError('offset EOF')
                    left-=len(c)
            left=n
            while left:
                c=src.read(min(left,1024*1024))
                if not c:raise EOFError('bundle EOF')
                fh.write(c);left-=len(c)
        if p.read_bytes()[:7]!=b'UnityFS':raise ValueError('invalid UnityFS signature')
        carve_log.append({'bundleId':bid,'bytes':p.stat().st_size,'logicalName':rec['logicalName']})
        return p,'current-apk-exact-offset'
    except Exception as e:
        p.unlink(missing_ok=True);carve_errors.append({'bundleId':bid,'error':f'{type(e).__name__}:{e}'});return None,'carve_failed'

# ---------- exact object identity helpers ----------
def inspect_bundle_set(bundle_ids,group_label):
    files=[];source_rows=[]
    for bid in sorted(bundle_ids):
        p,src=bundle_path(bid)
        if p is None:return {'group':group_label,'loaded':False,'reason':src,'bundleId':bid}
        files.append(str(p));source_rows.append({'bundleId':bid,'source':src})
    env=UnityPy.load(*files)
    objects=list(env.objects)
    def af_name(af):return str(getattr(af,'name',None) or getattr(af,'path',None) or '')
    def key(o):return (af_name(o.assets_file),int(o.path_id))
    obj_by_key={key(o):o for o in objects};af_names=sorted({k[0] for k in obj_by_key})
    def ext_path(af,fid):
        exts=getattr(af,'externals',None) or [];i=int(fid)-1
        if i<0 or i>=len(exts):return None
        e=exts[i];return str(getattr(e,'path',None) or getattr(e,'name',None) or '')
    def resolve(af,pp):
        if not isinstance(pp,dict):return None
        fid=pp.get('m_FileID',pp.get('fileID',pp.get('fileId',0)));pid=pp.get('m_PathID',pp.get('pathID',pp.get('pathId',0)))
        try:fid=int(fid or 0);pid=int(pid or 0)
        except:return None
        if not pid:return None
        if fid==0:return (af_name(af),pid)
        ep=ext_path(af,fid)
        if not ep:return None
        base=Path(ep).name.lower();matches=[n for n in af_names if Path(n).name.lower()==base or n.lower()==ep.lower()]
        return (matches[0],pid) if len(matches)==1 else None
    def tree(o):
        try:return o.read_typetree()
        except:return None
    scripts=[];script_keys=set()
    for o in objects:
        if str(o.type.name)!='MonoScript':continue
        t=tree(o)
        if isinstance(t,dict) and str(t.get('m_ClassName') or '')=='LuaUIFormLogic':
            k=key(o);script_keys.add(k);scripts.append({'assetsFile':k[0],'pathID':k[1],'name':t.get('m_Name'),'className':'LuaUIFormLogic','namespace':t.get('m_Namespace'),'assemblyName':t.get('m_AssemblyName')})
    def walk(x,path='$'):
        if isinstance(x,dict):
            if ('m_PathID' in x or 'pathID' in x or 'pathId' in x) and ('m_FileID' in x or 'fileID' in x or 'fileId' in x):yield path,x
            for k,v in x.items():
                if isinstance(v,(dict,list)):yield from walk(v,path+'.'+str(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):
                if isinstance(v,(dict,list)):yield from walk(v,path+f'[{i}]')
    behaviours=[];textassets=[];unresolved=[]
    if script_keys:
        for o in objects:
            if str(o.type.name)!='MonoBehaviour':continue
            t=tree(o)
            if not isinstance(t,dict):continue
            sp=t.get('m_Script')
            sk=resolve(o.assets_file,sp) if isinstance(sp,dict) else None
            if sk not in script_keys:continue
            ok=key(o);br={'assetsFile':ok[0],'pathID':ok[1],'name':t.get('m_Name'),'scriptTarget':{'assetsFile':sk[0],'pathID':sk[1]},'textAssetRefs':[],'unresolvedPPtrs':[]}
            for field,pp in walk(t):
                if field=='$.m_Script':continue
                rk=resolve(o.assets_file,pp)
                if rk is None:
                    br['unresolvedPPtrs'].append({'field':field,'pptr':pp});continue
                ro=obj_by_key.get(rk)
                if ro is None:continue
                if str(ro.type.name)=='TextAsset':
                    rt=tree(ro);name=rt.get('m_Name') if isinstance(rt,dict) else None
                    row={'field':field,'assetsFile':rk[0],'pathID':rk[1],'name':name}
                    br['textAssetRefs'].append(row);textassets.append(row)
            behaviours.append(br)
    return {'group':group_label,'loaded':True,'bundleCount':len(bundle_ids),'objectCount':len(objects),'sources':source_rows,'exactLuaUIFormLogicScripts':scripts,'matchingBehaviours':behaviours,'exactTextAssetRefs':textassets,'unresolvedPPtrCount':sum(len(x['unresolvedPPtrs']) for x in behaviours)}

# Inspect proven baseline once first. This performs no APK carving.
baseline_result=inspect_bundle_set(baseline,'proven-target-closure')
results=[];found=False;found_group=None
if baseline_result.get('matchingBehaviours'):
    found=True;found_group='proven-target-closure'
else:
    for g in groups:
        if g['deltaCount']>MAX_GROUP_DELTA:
            results.append({'group':f"dependent-{g['dependentBundleId']}",'loaded':False,'reason':'group_delta_exceeds_cap','deltaCount':g['deltaCount'],'cap':MAX_GROUP_DELTA});continue
        group_ids=baseline|set(g['deltaBundleIds'])
        r=inspect_bundle_set(group_ids,f"dependent-{g['dependentBundleId']}")
        r['dependentBundleId']=g['dependentBundleId'];r['deltaCount']=g['deltaCount'];r['dependentAssetPaths']=g['assetPaths']
        results.append(r)
        if r.get('matchingBehaviours'):
            found=True;found_group=r['group'];break

all_scripts=list(baseline_result.get('exactLuaUIFormLogicScripts') or [])
all_beh=list(baseline_result.get('matchingBehaviours') or [])
all_text=list(baseline_result.get('exactTextAssetRefs') or [])
for r in results:
    all_scripts.extend(r.get('exactLuaUIFormLogicScripts') or []);all_beh.extend(r.get('matchingBehaviours') or []);all_text.extend(r.get('exactTextAssetRefs') or [])
# dedupe exact identity rows
sd={(x['assetsFile'],x['pathID']):x for x in all_scripts};bd={(x['assetsFile'],x['pathID']):x for x in all_beh};td={(x['assetsFile'],x['pathID'],x.get('field')):x for x in all_text}
all_scripts=list(sd.values());all_beh=list(bd.values());all_text=list(td.values())
next_strategy=('inspect_exact_luauiformlogic_textasset_payload' if all_text else 'inspect_exact_luauiformlogic_behaviour_fields' if all_beh else 'targeted_locator_v3_needed_without_candidate_promotion')

result={
 'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V2',
 'targetAsset':target_asset,'targetBundleId':target_bid,
 'counts':{'baselineClosure':len(baseline),'familyBundles':len(family_bids),'directDependents':len(direct_dependents),'unionDelta':len(union_delta),'groupsAttempted':len(results),'newBundlesCarved':len(carve_log),'exactScripts':len(all_scripts),'matchingBehaviours':len(all_beh),'exactTextAssetRefs':len(all_text)},
 'familyPaths':family_paths,'groups':groups,'baselineInspection':baseline_result,'incrementalInspections':results,
 'exactLuaUIFormLogicScripts':all_scripts,'matchingBehaviours':all_beh,'exactTextAssetRefs':all_text,
 'foundExact':found,'foundGroup':found_group,'nextStrategy':next_strategy,'carveLog':carve_log,'carveErrors':carve_errors,
 'guardrails':{'baselineReused':True,'globalBundleScan':False,'candidatePromotion':False,'apkReadOnly':True,'incrementalDirectDependentsOnly':True,'mainUntouched':True,'previewUntouched':True}
}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V2','',
 f"baselineClosure={len(baseline)} familyBundles={len(family_bids)} directDependents={len(direct_dependents)} unionDelta={len(union_delta)}",
 f"groupsAttempted={len(results)} newBundlesCarved={len(carve_log)} exactScripts={len(all_scripts)} matchingBehaviours={len(all_beh)} exactTextAssetRefs={len(all_text)}",
 f"foundExact={found} foundGroup={found_group}",f"nextStrategy={next_strategy}",'',
 'DIRECT DEPENDENT DELTAS']
for g in groups:
    lines.append(f"  bundle={g['dependentBundleId']} delta={g['deltaCount']} closure={g['closureCount']}")
    for p in g['assetPaths'][:8]:lines.append('    ASSET '+p)
lines+=['','EXACT LUAUIFORMLOGIC MONOSCRIPTS']
if all_scripts:
    for x in all_scripts:lines.append(f"  {x['assetsFile']}#{x['pathID']} assembly={x.get('assemblyName')} name={x.get('name')}")
else:lines.append('  NONE')
lines+=['','MATCHING MONOBEHAVIOURS']
if all_beh:
    for x in all_beh:
        lines.append(f"  {x['assetsFile']}#{x['pathID']} name={x.get('name')} textAssetRefs={len(x.get('textAssetRefs',[]))} unresolvedPPtrs={len(x.get('unresolvedPPtrs',[]))}")
        for t in x.get('textAssetRefs',[]):lines.append(f"    TEXT field={t['field']} target={t['assetsFile']}#{t['pathID']} name={t.get('name')}")
else:lines.append('  NONE')
lines+=['','INCREMENTAL GROUP RESULTS']
for r in results:
    lines.append(f"  {r.get('group')} loaded={r.get('loaded')} delta={r.get('deltaCount')} scripts={len(r.get('exactLuaUIFormLogicScripts') or [])} behaviours={len(r.get('matchingBehaviours') or [])} textAssets={len(r.get('exactTextAssetRefs') or [])} reason={r.get('reason')}")
lines+=['','NEXT '+next_strategy,
 'RULE: only exact direct-dependent graph relations and exact MonoScript/MonoBehaviour PPtrs are evidence.',
 'RULE: execution order by delta size is only a resource heuristic, never evidence.',
 'RULE: no global bundle scan, no candidate promotion, APK read-only, main/preview untouched.']
report.write_text('\n'.join(lines)+'\n','utf-8')

print('LUAUIFORM_V2_OK',f'baseline={len(baseline)}',f'dependents={len(direct_dependents)}',f'unionDelta={len(union_delta)}',f'groups={len(results)}',f'newCarved={len(carve_log)}')
print('LUAUIFORM_V2_EXACT',f'scripts={len(all_scripts)}',f'behaviours={len(all_beh)}',f'textAssets={len(all_text)}',f'found={found}')
print('LUAUIFORM_V2_NEXT',next_strategy)
print('LUAUIFORM_V2_JSON',out)
print('LUAUIFORM_V2_REPORT',report)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: incrementally locate LuaUIFormLogic from Formation dependents"
  git push origin "$BRANCH"
else
  echo "LUAUIFORM_V2_GIT no-change"
fi
