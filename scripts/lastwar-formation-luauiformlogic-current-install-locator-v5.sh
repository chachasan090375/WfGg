#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — LuaUIFormLogic current-install locator V5.
# V4 audited the smallest prefab-family delta (6934) and found no LuaUIFormLogic.
# V5 selects ONLY the next-smallest exact prefab-family group from V3, excluding V4's group.
# Expected current case: bundle 6929 / UIHeroFakePVPFormationPanel.prefab / delta=9.
# Only missing delta bundles are carved from CURRENT APK offset-table coordinates.
# Exact evidence only:
#   MonoScript.m_ClassName == LuaUIFormLogic
#   MonoBehaviour.m_Script -> exact MonoScript
#   exact prefab-root reachability through serialized PPtrs
#   exact TextAsset PPtrs from matching MonoBehaviour.
# Prefab/catalog names and delta size are scope/resource heuristics only.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
BASE_BUNDLE_DIR="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v2/bundles"
V3="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v3.json"
V4="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v4.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-luauiformlogic-current-install-v5"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v5.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V5.txt"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent: $GAMERES"
[[ -s "$V3" ]] || fail "JSON V3 absent: $V3"
[[ -s "$V4" ]] || fail "JSON V4 absent: $V4"
[[ -d "$BASE_BUNDLE_DIR" ]] || fail "socle Formation absent: $BASE_BUNDLE_DIR"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL/bundles" "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$GAMERES" "$BASE_BUNDLE_DIR" "$V3" "$V4" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import hashlib, json, re, struct, sys, zipfile
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION=sys.argv[8]
gameres=Path(sys.argv[1]); base_dir=Path(sys.argv[2]); v3p=Path(sys.argv[3]); v4p=Path(sys.argv[4]); local=Path(sys.argv[5]); outp=Path(sys.argv[6]); reportp=Path(sys.argv[7]); apks=[Path(x) for x in sys.argv[9:]]
text=gameres.read_text('utf-8',errors='replace')
v3=json.loads(v3p.read_text('utf-8')); v4=json.loads(v4p.read_text('utf-8'))
if v3.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V3': raise SystemExit('V3_FORMAT_MISMATCH')
if v4.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V4': raise SystemExit('V4_FORMAT_MISMATCH')
prev_bid=int(v4.get('selectedBundleId') or v4.get('selectedBundle') or 0)

# ---------- current canonical gameres ----------
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end(); n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M); e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,n=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
    except:pass
bundles={};asset_to_bid={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); rec={'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':[x for x in p[6].split('|') if x],'aliasName':p[7]}
        rec['assetPaths']=[paths[x] for x in rec['assetPathIds'] if x in paths];bundles[bid]=rec
        for ap in rec['assetPaths']:asset_to_bid[ap]=bid
    except:pass

def closure(seed):
    seen=set();q=deque([int(seed)])
    while q:
        bid=q.popleft()
        if bid in seen:continue
        seen.add(bid)
        for d in bundles.get(bid,{}).get('dependencyBundleIds',[]):
            if d not in seen:q.append(int(d))
    return seen

target=v3.get('target') or {}; target_asset=str(target.get('assetPath') or ''); target_bid=int(target.get('bundleId'))
baseline=closure(target_bid)
# Select next prefab-family group only. Ignore image/texture-only groups.
groups=((v3.get('formationFamily') or {}).get('groups') or [])
candidates=[]
for g in groups:
    bid=int(g.get('bundleId'))
    aps=[str(x) for x in (g.get('assetPaths') or [])]
    if bid==prev_bid or bid==target_bid:continue
    if int(g.get('deltaCount') or 0)<=0:continue
    pref=[p for p in aps if p.lower().endswith('.prefab')]
    if not pref:continue
    candidates.append((int(g.get('deltaCount')),bid,g,pref))
if not candidates:raise SystemExit('NO_NEXT_PREFAB_FAMILY_DELTA')
candidates.sort(key=lambda x:(x[0],x[1])); expected_delta,selected_bid,selected_v3,prefab_paths=candidates[0]
selected_closure=closure(selected_bid); actual_delta=sorted(selected_closure-baseline); overlap=selected_closure & baseline
if len(actual_delta)!=expected_delta or actual_delta!=sorted(int(x) for x in (selected_v3.get('deltaBundleIds') or [])):
    raise SystemExit(f'V3_DELTA_RECOMPUTE_MISMATCH bundle={selected_bid} expected={selected_v3.get("deltaBundleIds")} actual={actual_delta}')
MAX_DELTA=12
if len(actual_delta)>MAX_DELTA:
    result={'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V5','aborted':True,'reason':'next_prefab_delta_exceeds_cap','selectedBundleId':selected_bid,'deltaBundleIds':actual_delta,'cap':MAX_DELTA}
    outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    reportp.write_text('WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V5\n\nABORTED next prefab delta exceeds cap\n','utf-8')
    raise SystemExit(3)
missing_overlap=[bid for bid in sorted(overlap) if not (base_dir/f'bundle-{bid}.bundle').is_file()]
if missing_overlap:raise SystemExit('PROVEN_BASELINE_FILES_MISSING '+repr(missing_overlap[:50]))

# ---------- exact current APK offset-table carving for delta only ----------
def read7(buf,pos):
    outv=0;shift=0
    while True:
        if pos>=len(buf):raise ValueError('7bit EOF')
        x=buf[pos];pos+=1;outv|=(x&0x7f)<<shift
        if not x&0x80:return outv,pos
        shift+=7

def parse_offsets(buf):
    pos=0;fc=struct.unpack_from('<I',buf,pos)[0];pos+=4;out=[]
    for gi in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4;rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,int(off)))
        out.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return out

def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())
tables={'logical':[],'alias':[]};physical=[]
for apk in apks:
    with zipfile.ZipFile(apk) as z:
        ns=set(z.namelist())
        for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
            if entry in ns:
                for g in parse_offsets(z.read(entry)):tables[kind].append({**g,'tableApk':str(apk),'tableEntry':entry})
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
            ph=map_physical(g);end=rr[i+1][1] if i+1<len(rr) else (ph['size'] if ph else None)
            if ph and end is not None and end>off:out.append({'offset':off,'end':end,'spanBytes':end-off,'physical':ph,'group':g['group'],'fragment':g['fragment'],'tableApk':g['tableApk']})
    ded={}
    for r in out:
        ph=r['physical'];ded[(ph['apk'],ph['entry'],r['offset'],r['end'])]=r
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

carve=[];carve_errors=[]
def get_bundle(bid):
    p=base_dir/f'bundle-{bid}.bundle'
    if p.is_file():return p,'reused-proven-baseline'
    p=local/'bundles'/f'bundle-{bid}.bundle'
    if p.is_file() and p.read_bytes()[:7]==b'UnityFS':return p,'reused-v5-delta'
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
        row={'bundleId':bid,'source':'current-apk-exact-offset','bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'logicalName':rec['logicalName'],'aliasName':rec.get('aliasName'),'location':loc}
        carve.append(row);return p,row['source']
    except Exception as e:
        p.unlink(missing_ok=True);carve_errors.append({'bundleId':bid,'error':f'{type(e).__name__}:{e}'});return None,'carve_failed'

bundle_files=[]
for bid in sorted(selected_closure):
    p,src=get_bundle(bid)
    if p is None:raise SystemExit(f'BUNDLE_RESOLVE_FAILED {bid} {src}')
    bundle_files.append(str(p))

env=UnityPy.load(*bundle_files);objects=list(env.objects)
def af_name(af):return str(getattr(af,'name',None) or getattr(af,'path',None) or '')
def key(o):return (af_name(o.assets_file),int(o.path_id))
obj_by_key={key(o):o for o in objects};af_names=sorted({k[0] for k in obj_by_key})
def safe_tree(o):
    try:return o.read_typetree()
    except:return None

def pptr_vals(pp):
    if isinstance(pp,dict):fid=pp.get('m_FileID',pp.get('fileID',pp.get('fileId',0)));pid=pp.get('m_PathID',pp.get('pathID',pp.get('pathId',0)))
    else:fid=getattr(pp,'file_id',getattr(pp,'m_FileID',0));pid=getattr(pp,'path_id',getattr(pp,'m_PathID',0))
    try:return int(fid or 0),int(pid or 0)
    except:return 0,0

def ext_path(af,fid):
    exts=getattr(af,'externals',None) or [];i=int(fid)-1
    if i<0 or i>=len(exts):return None
    e=exts[i];return str(getattr(e,'path',None) or getattr(e,'name',None) or '')

def resolve_key(af,pp):
    fid,pid=pptr_vals(pp)
    if not pid:return None
    if fid==0:return (af_name(af),pid) if (af_name(af),pid) in obj_by_key else None
    ep=ext_path(af,fid)
    if not ep:return None
    base=Path(ep).name.lower();matches=[n for n in af_names if n.lower()==ep.lower() or Path(n).name.lower()==base or n.lower().endswith('/'+base)]
    if len(matches)!=1:return None
    k=(matches[0],pid);return k if k in obj_by_key else None

def walk_pptr(x,path='$'):
    if isinstance(x,dict):
        if any(k in x for k in ('m_PathID','pathID','pathId')) and any(k in x for k in ('m_FileID','fileID','fileId')):yield path,x
        for k,v in x.items():
            if isinstance(v,(dict,list)):yield from walk_pptr(v,path+'.'+str(k))
    elif isinstance(x,list):
        for i,v in enumerate(x):
            if isinstance(v,(dict,list)):yield from walk_pptr(v,f'{path}[{i}]')

def obj_name(o,t=None):
    t=t if isinstance(t,dict) else safe_tree(o)
    if isinstance(t,dict):
        for k in ('m_Name','name'):
            if isinstance(t.get(k),str):return t[k]
    return ''

# ---------- exact prefab root resolution ----------
container_paths=defaultdict(list);root_candidates=defaultdict(set)
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
    if hasattr(r,'assets_file'):
        k=key(r);container_paths[k].append(str(p))
        for target_path in prefab_paths:
            if str(p)==target_path:root_candidates[target_path].add(k)

# Fallback: exact serialized AssetBundle container key -> PPtr in SAME structural record.
def collect_pptrs(x):return [pp for _,pp in walk_pptr(x)]
def scan_container_records(x,target_path,af,acc):
    if isinstance(x,dict):
        string_hit=any(isinstance(v,str) and v==target_path for v in x.values())
        if string_hit:
            ks=[]
            for pp in collect_pptrs(x):
                rk=resolve_key(af,pp)
                if rk:ks.append(rk)
            for rk in set(ks):acc.add(rk)
        for v in x.values():
            if isinstance(v,(dict,list)):scan_container_records(v,target_path,af,acc)
    elif isinstance(x,list):
        for v in x:
            if isinstance(v,(dict,list)):scan_container_records(v,target_path,af,acc)

for o in objects:
    if str(o.type.name)!='AssetBundle':continue
    t=safe_tree(o)
    if not isinstance(t,(dict,list)):continue
    for target_path in prefab_paths:
        scan_container_records(t,target_path,o.assets_file,root_candidates[target_path])

roots=[];root_rows=[]
for p in prefab_paths:
    ks=sorted(root_candidates[p])
    row={'assetPath':p,'candidateCount':len(ks),'resolved':len(ks)==1,'candidates':[{'assetsFile':a,'pathID':pid} for a,pid in ks]}
    root_rows.append(row)
    if len(ks)==1:roots.append(ks[0])

# ---------- exact serialized graph ----------
adj=defaultdict(set);edge_count=0;unresolved=0;trees={}
for o in objects:
    t=safe_tree(o);trees[key(o)]=t
    if not isinstance(t,(dict,list)):continue
    for pth,pp in walk_pptr(t):
        rk=resolve_key(o.assets_file,pp)
        if rk is None:unresolved+=1;continue
        adj[key(o)].add(rk);edge_count+=1
reachable=set();q=deque(roots)
while q:
    k=q.popleft()
    if k in reachable:continue
    reachable.add(k)
    for n in adj.get(k,()):
        if n not in reachable:q.append(n)

# ---------- exact LuaUIFormLogic identity ----------
scripts=[];script_keys=set()
for o in objects:
    if str(o.type.name)!='MonoScript':continue
    t=trees.get(key(o));
    if isinstance(t,dict) and str(t.get('m_ClassName') or '')=='LuaUIFormLogic':
        k=key(o);script_keys.add(k);scripts.append({'assetsFile':k[0],'pathID':k[1],'name':t.get('m_Name'),'namespace':t.get('m_Namespace'),'assemblyName':t.get('m_AssemblyName'),'reachableFromPrefab':k in reachable,'containerPaths':container_paths.get(k,[])})

beh=[];family_beh=[];textrefs=[];family_text=[]
if script_keys:
    for o in objects:
        if str(o.type.name)!='MonoBehaviour':continue
        t=trees.get(key(o))
        if not isinstance(t,dict):continue
        sp=t.get('m_Script');sk=resolve_key(o.assets_file,sp) if sp is not None else None
        if sk not in script_keys:continue
        ok=key(o);go_name='';go=t.get('m_GameObject')
        if go is not None:
            gk=resolve_key(o.assets_file,go);goo=obj_by_key.get(gk) if gk else None
            if goo:go_name=obj_name(goo,trees.get(gk))
        row={'assetsFile':ok[0],'pathID':ok[1],'gameObjectName':go_name,'scriptTarget':{'assetsFile':sk[0],'pathID':sk[1]},'reachableFromPrefab':ok in reachable,'containerPaths':container_paths.get(ok,[]),'textAssets':[]}
        seen=set()
        for pth,pp in walk_pptr(t):
            if pth=='$.m_Script':continue
            rk=resolve_key(o.assets_file,pp);ro=obj_by_key.get(rk) if rk else None
            if ro is None or str(ro.type.name)!='TextAsset' or rk in seen:continue
            seen.add(rk);rt=trees.get(rk);tr={'fieldPath':pth,'assetsFile':rk[0],'pathID':rk[1],'name':obj_name(ro,rt),'reachableFromPrefab':rk in reachable,'containerPaths':container_paths.get(rk,[])}
            row['textAssets'].append(tr);full={'behaviour':{'assetsFile':ok[0],'pathID':ok[1],'gameObjectName':go_name},**tr};textrefs.append(full)
            if ok in reachable:family_text.append(full)
        beh.append(row)
        if ok in reachable:family_beh.append(row)

# next prefab delta after this one
rest=[]
for g in groups:
    bid=int(g.get('bundleId'));d=int(g.get('deltaCount') or 0);aps=[str(x) for x in (g.get('assetPaths') or [])]
    if bid in (target_bid,prev_bid,selected_bid) or d<=0:continue
    pref=[p for p in aps if p.lower().endswith('.prefab')]
    if pref:rest.append((d,bid,pref))
rest.sort(key=lambda x:(x[0],x[1]));next_prefab={'bundleId':rest[0][1],'deltaCount':rest[0][0],'assetPaths':rest[0][2]} if rest else None
if family_text:next_strategy='inspect_family_linked_exact_luauiformlogic_textasset_payload'
elif family_beh:next_strategy='inspect_family_linked_exact_luauiformlogic_behaviour_fields'
elif beh:next_strategy='resolve_why_exact_luauiformlogic_behaviour_is_not_prefab_reachable'
elif scripts:next_strategy='trace_exact_luauiformlogic_monoscript_usage_within_selected_closure'
elif next_prefab:next_strategy='audit_next_smallest_exact_formation_prefab_family_delta'
else:next_strategy='targeted_non_prefab_luauiformlogic_locator_required'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V5',
 'previousV4BundleId':prev_bid,'selectedBundleId':selected_bid,'selectedAssetPaths':prefab_paths,
 'closure':{'count':len(selected_closure),'baselineOverlap':len(overlap),'deltaCount':len(actual_delta),'deltaBundleIds':actual_delta},
 'counts':{'objects':len(objects),'roots':len(roots),'reachable':len(reachable),'graphEdges':edge_count,'unresolvedPPtrs':unresolved,'exactScripts':len(scripts),'matchingBehaviours':len(beh),'familyLinkedBehaviours':len(family_beh),'exactTextAssetRefs':len(textrefs),'familyLinkedTextAssetRefs':len(family_text)},
 'prefabRoots':root_rows,'deltaBundles':carve,'carveErrors':carve_errors,
 'exactLuaUIFormLogicMonoScripts':scripts,'matchingMonoBehaviours':beh,'familyLinkedMonoBehaviours':family_beh,'exactTextAssetRefs':textrefs,'familyLinkedTextAssetRefs':family_text,
 'nextPrefabFamilyDelta':next_prefab,'nextStrategy':next_strategy,
 'guardrails':{'catalogFamilyMembershipIsScopeOnly':True,'deltaSizeIsResourceHeuristicOnly':True,'exactPPtrRequiredForEvidence':True,'apkReadOnly':True,'globalBundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V5','',
 f'selectedBundle={selected_bid} closure={len(selected_closure)} baselineOverlap={len(overlap)} delta={len(actual_delta)} deltaIds={" ".join(map(str,actual_delta))}',
 f'objects={len(objects)} roots={len(roots)} reachable={len(reachable)} graphEdges={edge_count} unresolvedPPtrs={unresolved}',
 f'exactScripts={len(scripts)} matchingBehaviours={len(beh)} familyLinkedBehaviours={len(family_beh)} exactTextAssetRefs={len(textrefs)} familyLinkedTextAssetRefs={len(family_text)}',
 f'nextStrategy={next_strategy}','','FAMILY PREFAB ROOTS']
for x in root_rows:lines.append('  '+json.dumps(x,ensure_ascii=False,separators=(',',':')))
lines+=['','DELTA BUNDLES']
for x in carve:lines.append('  '+json.dumps(x,ensure_ascii=False,separators=(',',':')))
if carve_errors:
    lines+=['','CARVE ERRORS']+[ '  '+json.dumps(x,ensure_ascii=False,separators=(',',':')) for x in carve_errors]
lines+=['','EXACT LUAUIFORMLOGIC MONOSCRIPTS']
if scripts:
    for x in scripts:lines.append(f"  {x['assetsFile']}#{x['pathID']} assembly={x.get('assemblyName')} reachable={x['reachableFromPrefab']}")
else:lines.append('  NONE')
lines+=['','MATCHING MONOBEHAVIOURS']
if beh:
    for x in beh:lines.append(f"  {x['assetsFile']}#{x['pathID']} gameObject={x['gameObjectName']!r} reachable={x['reachableFromPrefab']} textAssets={len(x['textAssets'])}")
else:lines.append('  NONE')
lines+=['','FAMILY-LINKED EXACT EVIDENCE']
if family_beh:
    for x in family_beh:
        lines.append(f"  BEHAVIOUR {x['assetsFile']}#{x['pathID']} gameObject={x['gameObjectName']!r} textAssets={len(x['textAssets'])}")
        for t in x['textAssets']:lines.append(f"    TEXT field={t['fieldPath']} target={t['assetsFile']}#{t['pathID']} name={t.get('name')!r}")
else:lines.append('  NONE')
if next_prefab:
    lines+=['',f"NEXT PREFAB FAMILY DELTA bundle={next_prefab['bundleId']} delta={next_prefab['deltaCount']}"]
    for p in next_prefab['assetPaths']:lines.append('  ASSET '+p)
lines+=['','NEXT '+next_strategy,
 'RULE: catalog family membership/delta size are scope heuristics only; exact serialized PPtr identity/reachability is evidence.',
 'RULE: only selected closure delta bundles are read from current APK; APK remains read-only.',
 'RULE: no global bundle scan, no candidate promotion, main/preview untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('LUAUIFORM_V5_OK',f'bundle={selected_bid}',f'closure={len(selected_closure)}',f'delta={len(actual_delta)}',f'newCarved={len(carve)}')
print('LUAUIFORM_V5_EXACT',f'scripts={len(scripts)}',f'behaviours={len(beh)}',f'familyBehaviours={len(family_beh)}',f'textAssets={len(textrefs)}',f'familyTextAssets={len(family_text)}')
print('LUAUIFORM_V5_NEXT',next_strategy)
print('LUAUIFORM_V5_JSON',outp)
print('LUAUIFORM_V5_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: audit next exact Formation prefab delta for LuaUIFormLogic"
  git push origin "$BRANCH"
else
  echo "LUAUIFORM_V5_GIT no-change"
fi
