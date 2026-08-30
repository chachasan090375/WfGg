#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — LuaUIFormLogic current-install locator V4.
# Consumes V3's exact smallest non-zero Formation-family closure delta.
# Current expected case: bundle 6934 / UIHeroPVPFormationPanelHeroCell.prefab / delta={6934}.
# Only delta bundles absent from the proven baseline are carved from CURRENT APK offset tables.
# Evidence is exact serialized identity only:
#   MonoScript.m_ClassName == LuaUIFormLogic
#   MonoBehaviour.m_Script -> that exact MonoScript
#   optional reachability from the exact family prefab root through resolved serialized PPtrs
#   optional TextAsset PPtrs from that exact matching MonoBehaviour.
# Catalog path membership and delta size are scope/resource heuristics only, never runtime proof.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
BASE_BUNDLE_DIR="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v2/bundles"
V3="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v3.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-luauiformlogic-current-install-v4"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v4.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V4.txt"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent: $GAMERES"
[[ -s "$V3" ]] || fail "rapport JSON V3 absent: $V3"
[[ -d "$BASE_BUNDLE_DIR" ]] || fail "socle Formation V4/V2 absent: $BASE_BUNDLE_DIR"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL/bundles" "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$GAMERES" "$BASE_BUNDLE_DIR" "$V3" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import hashlib, json, re, struct, sys, zipfile
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION=sys.argv[7]
gameres=Path(sys.argv[1]); base_dir=Path(sys.argv[2]); v3p=Path(sys.argv[3]); local=Path(sys.argv[4]); outp=Path(sys.argv[5]); reportp=Path(sys.argv[6]); apks=[Path(x) for x in sys.argv[8:]]
text=gameres.read_text('utf-8',errors='replace')
v3=json.loads(v3p.read_text('utf-8'))

if v3.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V3':
    raise SystemExit('V3_FORMAT_MISMATCH')
small=((v3.get('formationFamily') or {}).get('smallestNonzeroDelta'))
if not isinstance(small,dict):
    raise SystemExit('V3_SMALLEST_NONZERO_DELTA_MISSING')
selected_bid=int(small.get('bundleId'))
delta_ids=sorted({int(x) for x in (small.get('deltaBundleIds') or [])})
family_paths=[str(x) for x in (small.get('assetPaths') or [])]
if not delta_ids:
    raise SystemExit('V3_DELTA_EMPTY')
# Keep this pass deliberately tiny. If V3 ever changes to a large smallest delta, abort instead of widening.
MAX_DELTA=4
if len(delta_ids)>MAX_DELTA:
    result={'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V4','aborted':True,'reason':'v3_smallest_delta_exceeds_v4_cap','selectedBundleId':selected_bid,'deltaBundleIds':delta_ids,'cap':MAX_DELTA}
    outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    reportp.write_text('WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V4\n\nABORTED V3 smallest delta exceeds V4 cap\ndelta='+str(len(delta_ids))+' cap='+str(MAX_DELTA)+'\n','utf-8')
    print('LUAUIFORM_V4_ABORT delta',len(delta_ids),'cap',MAX_DELTA)
    raise SystemExit(3)

# ---------- canonical current gameres ----------
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
        bid=int(p[0]);rec={'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':[x for x in p[6].split('|') if x],'aliasName':p[7]}
        rec['assetPaths']=[paths[x] for x in rec['assetPathIds'] if x in paths];bundles[bid]=rec
        for ap in rec['assetPaths']:asset_to_bid[ap]=bid
    except:pass

if selected_bid not in bundles:raise SystemExit('SELECTED_BUNDLE_NOT_IN_GAMERES')
# Recompute selected closure independently and verify V3's exact delta claim.
def closure(seed):
    seen=set();q=deque([int(seed)])
    while q:
        bid=q.popleft()
        if bid in seen:continue
        seen.add(bid)
        for d in bundles.get(bid,{}).get('dependencyBundleIds',[]):
            if d not in seen:q.append(int(d))
    return seen
selected_closure=closure(selected_bid)
target_asset=((v3.get('target') or {}).get('assetPath'))
target_bid=int((v3.get('target') or {}).get('bundleId'))
baseline=closure(target_bid)
actual_delta=sorted(selected_closure-baseline)
if actual_delta!=delta_ids:
    raise SystemExit('V3_DELTA_RECOMPUTE_MISMATCH expected='+repr(delta_ids)+' actual='+repr(actual_delta))
missing_baseline=[bid for bid in sorted(selected_closure & baseline) if not (base_dir/f'bundle-{bid}.bundle').is_file()]
if missing_baseline:
    raise SystemExit('PROVEN_BASELINE_FILES_MISSING '+repr(missing_baseline[:50]))

# Exact family prefab path(s) inside the selected V3 group. This is selection scope only.
prefab_paths=[p for p in family_paths if p.lower().endswith('.prefab')]
if not prefab_paths:
    prefab_paths=[p for p in bundles[selected_bid].get('assetPaths',[]) if p.lower().endswith('.prefab') and 'pvpformation' in p.lower()]
# We can still inspect exact script identity if no prefab path exists, but target reachability then remains unresolved.

# ---------- CURRENT APK exact offset-table resolution, delta only ----------
def read7(buf,pos):
    outv=0;shift=0
    while True:
        if pos>=len(buf):raise ValueError('7bit EOF')
        x=buf[pos];pos+=1;outv|=(x&0x7f)<<shift
        if not x&0x80:return outv,pos
        shift+=7

def parse_offsets(buf):
    pos=0;fc=struct.unpack_from('<I',buf,pos)[0];pos+=4;groups=[]
    for gi in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4;rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,int(off)))
        groups.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return groups

def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())
tables={'logical':[],'alias':[]};physical=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            ns=set(z.namelist())
            for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
                if entry in ns:
                    for g in parse_offsets(z.read(entry)):tables[kind].append({**g,'tableApk':str(apk),'tableEntry':entry})
            for n in z.namelist():
                lo=n.lower()
                if 'assets/assetbundles/' in lo and 'bundlefragment' in lo and lo.endswith('.bytes'):
                    physical.append({'apk':str(apk),'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})
    except Exception as e:
        print('LUAUIFORM_V4_APK_WARNING',apk,type(e).__name__,str(e)[:160])
if not tables['logical']:raise SystemExit('NO_CURRENT_BUNDLE_OFFSET_TABLE')
if not physical:raise SystemExit('NO_CURRENT_BUNDLE_FRAGMENTS')

def map_physical(g):
    nf=norm(g.get('fragment',''));gi=int(g.get('group',0));rank=[]
    for p in physical:
        score=0;nb=norm(p['base']);ns=norm(p['stem'])
        if nf and (nf==nb or nf==ns):score=100
        elif nf and (nf in nb or nb in nf or nf in ns or ns in nf):score=80
        if re.search(rf'fragment0*{gi}(?:\D|$)',p['base'],re.I):score=max(score,60)
        if p['apk']==g.get('tableApk'):score+=5
        if score:rank.append((score,p))
    if not rank:return None,'no_physical_fragment_match'
    rank.sort(key=lambda x:(-x[0],x[1]['apk'],x[1]['entry']))
    best=rank[0][0];tops=[p for s,p in rank if s==best]
    if len({(p['apk'],p['entry']) for p in tops})!=1:return None,'ambiguous_physical_fragment'
    return tops[0],None

def row_matches(kind,name):
    out=[]
    if not name:return out
    for g in tables[kind]:
        rr=sorted(g['rows'],key=lambda x:x[1])
        for i,(n,off) in enumerate(rr):
            if n!=name:continue
            ph,err=map_physical(g);end=rr[i+1][1] if i+1<len(rr) else (ph['size'] if ph else None)
            if ph and end is not None and end>off:
                out.append({'offset':int(off),'end':int(end),'spanBytes':int(end-off),'physical':ph,'group':g['group'],'fragment':g['fragment'],'tableApk':g['tableApk']})
    ded={}
    for r in out:
        p=r['physical'];ded[(p['apk'],p['entry'],r['offset'],r['end'])]=r
    return list(ded.values())

def exact_location(rec):
    lm=row_matches('logical',rec['logicalName']);am=row_matches('alias',rec.get('aliasName')) if rec.get('aliasName') else []
    if not lm:return None,'logical_row_not_found'
    if am:
        keep=[]
        for l in lm:
            lp=l['physical']
            for a in am:
                ap=a['physical']
                if a['offset']==l['offset'] and ap['apk']==lp['apk'] and ap['entry']==lp['entry']:
                    keep.append(l);break
        lm=keep
    coords={(x['physical']['apk'],x['physical']['entry'],x['offset'],x['spanBytes']) for x in lm}
    if len(coords)!=1:return None,'ambiguous_or_alias_mismatch'
    return lm[0],None

carved=[];carve_errors=[]
def carve_delta(bid):
    dst=local/'bundles'/f'bundle-{bid}.bundle'
    if dst.is_file() and dst.read_bytes()[:7]==b'UnityFS':
        return dst,{'bundleId':bid,'source':'reused-v4-delta','bytes':dst.stat().st_size,'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()}
    rec=bundles.get(bid)
    if not rec:return None,{'bundleId':bid,'reason':'bundle_not_in_gameres'}
    loc,err=exact_location(rec)
    if not loc:return None,{'bundleId':bid,'reason':err,'logicalName':rec['logicalName'],'aliasName':rec.get('aliasName')}
    span=int(loc['spanBytes']);decl=int(rec.get('declaredBytes') or 0);n=decl if 0<decl<=span else span
    try:
        ph=loc['physical'];dst.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(ph['apk']) as z,z.open(ph['entry'],'r') as src,dst.open('wb') as fh:
            try:src.seek(int(loc['offset']))
            except Exception:
                left=int(loc['offset'])
                while left:
                    c=src.read(min(left,1024*1024))
                    if not c:raise EOFError('EOF before exact bundle offset')
                    left-=len(c)
            left=n
            while left:
                c=src.read(min(left,1024*1024))
                if not c:raise EOFError('EOF during exact bundle carve')
                fh.write(c);left-=len(c)
        if dst.read_bytes()[:7]!=b'UnityFS':raise ValueError('invalid UnityFS signature')
        row={'bundleId':bid,'source':'current-apk-exact-offset','bytes':dst.stat().st_size,'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'logicalName':rec['logicalName'],'aliasName':rec.get('aliasName'),'location':loc}
        carved.append(row);return dst,row
    except Exception as e:
        dst.unlink(missing_ok=True);row={'bundleId':bid,'reason':f'{type(e).__name__}:{e}'};carve_errors.append(row);return None,row

bundle_paths={};source_rows=[]
for bid in sorted(selected_closure):
    bp=base_dir/f'bundle-{bid}.bundle'
    if bid in baseline and bp.is_file():
        bundle_paths[bid]=bp;source_rows.append({'bundleId':bid,'source':'reused-proven-baseline'})
    else:
        p,row=carve_delta(bid)
        if p is None:
            result={'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V4','aborted':True,'reason':'delta_carve_failed','selectedBundleId':selected_bid,'failed':row,'deltaBundleIds':delta_ids,'guardrails':{'apkReadOnly':True,'globalBundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}}
            outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
            reportp.write_text('WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V4\n\nABORTED delta carve failed\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n','utf-8')
            print('LUAUIFORM_V4_ABORT carveFailed',bid,row.get('reason'))
            raise SystemExit(3)
        bundle_paths[bid]=p;source_rows.append(row)

# ---------- exact serialized inspection ----------
env=UnityPy.load(*[str(bundle_paths[bid]) for bid in sorted(selected_closure)])
objects=list(env.objects)

def af_name(af):return str(getattr(af,'name',None) or getattr(af,'path',None) or '')
def obj_key(o):return (af_name(o.assets_file),int(o.path_id))
obj_by_key={obj_key(o):o for o in objects};af_names=sorted({k[0] for k in obj_by_key})

def safe_tree(o):
    try:return o.read_typetree()
    except:return None

def external_path(af,fid):
    exts=getattr(af,'externals',None) or [];i=int(fid)-1
    if i<0 or i>=len(exts):return None
    e=exts[i];return str(getattr(e,'path',None) or getattr(e,'name',None) or '')

def pptr_vals(pp):
    if isinstance(pp,dict):
        fid=pp.get('m_FileID',pp.get('fileID',pp.get('fileId',0)));pid=pp.get('m_PathID',pp.get('pathID',pp.get('pathId',0)))
    else:
        fid=getattr(pp,'file_id',getattr(pp,'m_FileID',0));pid=getattr(pp,'path_id',getattr(pp,'m_PathID',0))
    try:return int(fid or 0),int(pid or 0)
    except:return 0,0

def resolve_key(af,pp):
    fid,pid=pptr_vals(pp)
    if not pid:return None
    if fid==0:return (af_name(af),pid) if (af_name(af),pid) in obj_by_key else None
    ep=external_path(af,fid)
    if not ep:return None
    base=Path(ep).name.lower();matches=[n for n in af_names if n.lower()==ep.lower() or Path(n).name.lower()==base or n.lower().endswith('/'+base)]
    if len(matches)!=1:return None
    k=(matches[0],pid);return k if k in obj_by_key else None

def walk_pptrs(x,path='$'):
    if isinstance(x,dict):
        hasp=any(k in x for k in ('m_PathID','pathID','pathId'));hasf=any(k in x for k in ('m_FileID','fileID','fileId'))
        if hasp and hasf:yield path,x
        for k,v in x.items():
            if isinstance(v,(dict,list)):yield from walk_pptrs(v,path+'.'+str(k))
    elif isinstance(x,list):
        for i,v in enumerate(x):
            if isinstance(v,(dict,list)):yield from walk_pptrs(v,f'{path}[{i}]')

def read_name(o,t=None):
    t=t if isinstance(t,dict) else safe_tree(o)
    if isinstance(t,dict):
        for k in ('m_Name','name'):
            if isinstance(t.get(k),str):return t[k]
    try:
        d=o.read();return str(getattr(d,'m_Name','') or getattr(d,'name','') or '')
    except:return ''

# Exact container path lookup.
container_paths=defaultdict(list);container_obj={}
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
        k=obj_key(r);container_paths[k].append(str(p));container_obj[str(p)]=r

# Build exact resolved-PPtr adjacency once. Unresolved PPtrs stay explicit.
tree_cache={};adj=defaultdict(set);unresolved_pptrs=[]
for o in objects:
    t=safe_tree(o);tree_cache[obj_key(o)]=t
    if not isinstance(t,(dict,list)):continue
    for field,pp in walk_pptrs(t):
        rk=resolve_key(o.assets_file,pp)
        if rk is None:
            fid,pid=pptr_vals(pp)
            if pid:unresolved_pptrs.append({'source':{'assetsFile':obj_key(o)[0],'pathID':obj_key(o)[1]},'field':field,'fileID':fid,'pathID':pid})
        else:adj[obj_key(o)].add(rk)

root_rows=[];root_keys=[]
for p in prefab_paths:
    r=container_obj.get(p)
    if r is None:
        root_rows.append({'assetPath':p,'resolved':False})
        continue
    k=obj_key(r);root_keys.append(k);root_rows.append({'assetPath':p,'resolved':True,'assetsFile':k[0],'pathID':k[1],'type':str(r.type.name)})

reachable=set();q=deque(root_keys)
while q:
    k=q.popleft()
    if k in reachable:continue
    reachable.add(k)
    for d in adj.get(k,()):
        if d not in reachable:q.append(d)

exact_scripts=[];script_keys=set()
for o in objects:
    if str(o.type.name)!='MonoScript':continue
    t=tree_cache.get(obj_key(o))
    if isinstance(t,dict) and str(t.get('m_ClassName') or '')=='LuaUIFormLogic':
        k=obj_key(o);script_keys.add(k)
        exact_scripts.append({'assetsFile':k[0],'pathID':k[1],'name':t.get('m_Name'),'className':'LuaUIFormLogic','namespace':t.get('m_Namespace'),'assemblyName':t.get('m_AssemblyName'),'containerPaths':container_paths.get(k,[]),'reachableFromFamilyPrefab':k in reachable})

matching=[];text_refs=[]
for o in objects:
    if str(o.type.name)!='MonoBehaviour':continue
    t=tree_cache.get(obj_key(o))
    if not isinstance(t,dict):continue
    sk=resolve_key(o.assets_file,t.get('m_Script')) if t.get('m_Script') is not None else None
    if sk not in script_keys:continue
    k=obj_key(o);go_name='';gk=None
    if t.get('m_GameObject') is not None:
        gk=resolve_key(o.assets_file,t.get('m_GameObject'))
        if gk in obj_by_key:go_name=read_name(obj_by_key[gk],tree_cache.get(gk))
    row={'assetsFile':k[0],'pathID':k[1],'gameObjectName':go_name,'gameObjectTarget':({'assetsFile':gk[0],'pathID':gk[1]} if gk else None),'scriptTarget':{'assetsFile':sk[0],'pathID':sk[1]},'containerPaths':container_paths.get(k,[]),'reachableFromFamilyPrefab':k in reachable,'textAssets':[]}
    seen=set()
    for field,pp in walk_pptrs(t):
        if field=='$.m_Script':continue
        rk=resolve_key(o.assets_file,pp)
        ro=obj_by_key.get(rk) if rk else None
        if ro is None or str(ro.type.name)!='TextAsset' or rk in seen:continue
        seen.add(rk);tt=tree_cache.get(rk);tr={'fieldPath':field,'assetsFile':rk[0],'pathID':rk[1],'name':read_name(ro,tt),'containerPaths':container_paths.get(rk,[]),'reachableFromFamilyPrefab':rk in reachable}
        row['textAssets'].append(tr);text_refs.append({'behaviour':{'assetsFile':k[0],'pathID':k[1],'gameObjectName':go_name,'reachableFromFamilyPrefab':k in reachable},**tr})
    matching.append(row)

linked_beh=[x for x in matching if x['reachableFromFamilyPrefab']]
linked_text=[x for x in text_refs if x['behaviour']['reachableFromFamilyPrefab']]

# Determine the next exact family-prefab delta to audit if this one is negative.
groups=((v3.get('formationFamily') or {}).get('groups') or [])
prefab_groups=[]
for g in groups:
    try:bid=int(g.get('bundleId'));dc=int(g.get('deltaCount') or 0)
    except:continue
    if bid==selected_bid or dc<=0:continue
    aps=[str(x) for x in (g.get('assetPaths') or [])]
    if any(p.lower().endswith('.prefab') for p in aps):prefab_groups.append(g)
prefab_groups.sort(key=lambda g:(int(g.get('deltaCount') or 0),int(g.get('bundleId'))))
next_prefab=prefab_groups[0] if prefab_groups else None

if linked_text:
    next_strategy='inspect_exact_family_linked_luauiformlogic_textasset_payload'
elif linked_beh:
    next_strategy='inspect_exact_family_linked_luauiformlogic_behaviour_fields'
elif matching:
    next_strategy='luauiformlogic_found_in_closure_but_not_reachable_from_exact_family_prefab'
elif exact_scripts:
    next_strategy='luauiformlogic_script_found_but_no_matching_behaviour_in_selected_closure'
elif next_prefab:
    next_strategy='audit_next_smallest_exact_formation_prefab_family_delta'
else:
    next_strategy='targeted_locator_v5_generic_luauiformlogic_ui_form_prefab_required'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V4',
 'sourceV3':str(v3p),
 'selection':{'bundleId':selected_bid,'familyAssetPaths':family_paths,'prefabAssetPaths':prefab_paths,'closureCount':len(selected_closure),'baselineOverlapCount':len(selected_closure&baseline),'deltaCount':len(delta_ids),'deltaBundleIds':delta_ids,'actualDeltaVerified':actual_delta==delta_ids},
 'sources':source_rows,'carvedDeltaBundles':carved,'carveErrors':carve_errors,
 'inspection':{'objectCount':len(objects),'rootObjects':root_rows,'reachableObjectCount':len(reachable),'resolvedGraphEdges':sum(len(v) for v in adj.values()),'unresolvedPPtrCount':len(unresolved_pptrs),'unresolvedPPtrsSample':unresolved_pptrs[:100]},
 'exactEvidence':{'luaUIFormLogicMonoScripts':exact_scripts,'matchingMonoBehaviours':matching,'familyLinkedMonoBehaviours':linked_beh,'exactTextAssetRefs':text_refs,'familyLinkedTextAssetRefs':linked_text},
 'counts':{'exactScripts':len(exact_scripts),'matchingBehaviours':len(matching),'familyLinkedBehaviours':len(linked_beh),'exactTextAssetRefs':len(text_refs),'familyLinkedTextAssetRefs':len(linked_text)},
 'nextPrefabFamilyGroup':next_prefab,
 'conclusion':{'foundExactScript':bool(exact_scripts),'foundMatchingBehaviour':bool(matching),'foundFamilyLinkedBehaviour':bool(linked_beh),'foundFamilyLinkedTextAsset':bool(linked_text),'nextStrategy':next_strategy},
 'guardrails':{'currentApkAccess':True,'apkReadOnly':True,'deltaOnlyCarving':True,'deltaCap':MAX_DELTA,'globalBundleScan':False,'candidatePromotion':False,'exactSerializedIdentityRequired':True,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — LUAUIFORMLOGIC CURRENT INSTALL LOCATOR V4','',
 f'selectedBundle={selected_bid} closure={len(selected_closure)} baselineOverlap={len(selected_closure&baseline)} delta={len(delta_ids)} deltaIds={" ".join(map(str,delta_ids))}',
 f'objects={len(objects)} roots={len(root_keys)} reachable={len(reachable)} graphEdges={sum(len(v) for v in adj.values())} unresolvedPPtrs={len(unresolved_pptrs)}',
 f'exactScripts={len(exact_scripts)} matchingBehaviours={len(matching)} familyLinkedBehaviours={len(linked_beh)} exactTextAssetRefs={len(text_refs)} familyLinkedTextAssetRefs={len(linked_text)}',
 f'nextStrategy={next_strategy}','',
 'FAMILY PREFAB ROOTS']
if root_rows:
    for x in root_rows:lines.append('  '+json.dumps(x,ensure_ascii=False,separators=(',',':')))
else:lines.append('  NONE')
lines += ['', 'DELTA BUNDLES']
for x in source_rows:
    if x['bundleId'] in delta_ids:lines.append('  '+json.dumps(x,ensure_ascii=False,separators=(',',':')))
lines += ['', 'EXACT LUAUIFORMLOGIC MONOSCRIPTS']
if exact_scripts:
    for x in exact_scripts:lines.append(f"  assetsFile={x['assetsFile']} pathID={x['pathID']} assembly={x.get('assemblyName')} reachable={x['reachableFromFamilyPrefab']}")
else:lines.append('  NONE')
lines += ['', 'MATCHING MONOBEHAVIOURS']
if matching:
    for x in matching:
        lines.append(f"  assetsFile={x['assetsFile']} pathID={x['pathID']} gameObject={x['gameObjectName']!r} reachable={x['reachableFromFamilyPrefab']} textAssets={len(x['textAssets'])}")
        for t in x['textAssets']:lines.append(f"    TEXT field={t['fieldPath']} target={t['assetsFile']}#{t['pathID']} name={t['name']!r} reachable={t['reachableFromFamilyPrefab']}")
else:lines.append('  NONE')
lines += ['', 'FAMILY-LINKED EXACT EVIDENCE']
if linked_beh:
    for x in linked_beh:lines.append(f"  BEHAVIOUR {x['assetsFile']}#{x['pathID']} gameObject={x['gameObjectName']!r}")
else:lines.append('  NONE')
if next_prefab:
    lines += ['',f"NEXT PREFAB FAMILY DELTA bundle={next_prefab.get('bundleId')} delta={next_prefab.get('deltaCount')}"]
    for p in (next_prefab.get('assetPaths') or [])[:8]:lines.append('  ASSET '+str(p))
lines += ['', 'NEXT '+next_strategy,
 'RULE: catalog family membership/delta size are scope heuristics only; exact serialized PPtr reachability is evidence.',
 'RULE: only V3-selected delta bundles are read from current APK; APK remains read-only.',
 'RULE: no global bundle scan, no candidate promotion, main/preview untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')

print('LUAUIFORM_V4_OK',f'bundle={selected_bid}',f'closure={len(selected_closure)}',f'delta={len(delta_ids)}',f'newCarved={len(carved)}')
print('LUAUIFORM_V4_EXACT',f'scripts={len(exact_scripts)}',f'behaviours={len(matching)}',f'linked={len(linked_beh)}',f'textAssets={len(text_refs)}',f'linkedText={len(linked_text)}')
print('LUAUIFORM_V4_NEXT',next_strategy)
print('LUAUIFORM_V4_JSON',outp)
print('LUAUIFORM_V4_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: audit smallest exact Formation family delta for LuaUIFormLogic"
  git push origin "$BRANCH"
else
  echo "LUAUIFORM_V4_GIT no-change"
fi
