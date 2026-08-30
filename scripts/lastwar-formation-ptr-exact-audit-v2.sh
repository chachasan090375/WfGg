#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation exact serialized PPtr audit V2.
# Resolves bundle bytes from CURRENT installed APK BundleOffset/AliasOffset tables.
# No global bundle scan. No candidate/name substitution. Game remains read-only.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
TARGET_ASSET='Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab'
EXPECTED_BUNDLE=6933
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v2"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PTR_EXACT_V2.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-lastwar-formation-ptr-exact-v2.py"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque, Counter
import hashlib, json, re, struct, sys, time, zipfile
import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION=sys.argv[7]
gameres=Path(sys.argv[1]); target_asset=sys.argv[2]; expected_bundle=int(sys.argv[3]); local=Path(sys.argv[4]); out=Path(sys.argv[5]); report=Path(sys.argv[6]); apks=[Path(x) for x in sys.argv[8:]]
t0=time.time(); text=gameres.read_text('utf-8',errors='replace')

# ---------------- canonical gameres catalog ----------------
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end();n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M);e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,n=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
    except:pass
bundles={}; asset_to_bid={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); rec={'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':[x for x in p[6].split('|') if x],'aliasName':p[7]}
        rec['assetPaths']=[paths[x] for x in rec['assetPathIds'] if x in paths];bundles[bid]=rec
        for ap in rec['assetPaths']:asset_to_bid[ap]=bid
    except:pass

target_bid=asset_to_bid.get(target_asset)
if target_bid is None:raise SystemExit('TARGET_ASSET_NOT_IN_GAMERES')
if int(target_bid)!=expected_bundle:raise SystemExit(f'TARGET_BUNDLE_MISMATCH expected={expected_bundle} actual={target_bid}')
target_bid=int(target_bid)

# Closure selection: exactness first. Load full closure only when reasonably small.
def closure(root):
    seen=set();q=deque([root])
    while q:
        bid=q.popleft()
        if bid in seen:continue
        seen.add(bid);b=bundles.get(bid)
        if not b:continue
        for d in b.get('dependencyBundleIds',[]):
            if d not in seen:q.append(d)
    return sorted(seen)
full_closure=closure(target_bid)
direct=sorted(set([target_bid]+bundles[target_bid].get('dependencyBundleIds',[])))
LOAD_ALL_LIMIT=96
selected=full_closure if len(full_closure)<=LOAD_ALL_LIMIT else direct
selection_mode='full_dependency_closure' if selected==full_closure else 'target_plus_direct_dependencies'

# ---------------- CURRENT APK offset tables ----------------
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

tables={'logical':[],'alias':[]}; physical=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            names=z.namelist(); ns=set(names)
            for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
                if entry in ns:
                    for g in parse_offsets(z.read(entry)):
                        tables[kind].append({**g,'tableApk':str(apk),'tableEntry':entry})
            for n in names:
                lo=n.lower()
                if 'assets/assetbundles/' in lo and 'bundlefragment' in lo and lo.endswith('.bytes'):
                    physical.append({'apk':str(apk),'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})
    except Exception as e:
        print('FORMATION_PTR_APK_WARNING',apk,type(e).__name__,str(e)[:160])
if not physical:raise SystemExit('NO_PHYSICAL_BUNDLE_FRAGMENTS_IN_CURRENT_APKS')
if not tables['logical']:raise SystemExit('NO_BUNDLE_OFFSET_TABLE_IN_CURRENT_APKS')

# Map a table group to a physical BundleFragment. Ambiguous top score is rejected, never guessed.
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
    uniq={(p['apk'],p['entry']) for p in tops}
    if len(uniq)!=1:return None,f'ambiguous_physical_fragment topScore={best} count={len(uniq)}'
    return tops[0],None

# Find all exact table rows for a given identity, including span to next row in SAME group.
def row_matches(kind,name):
    out=[]
    if not name:return out
    for g in tables[kind]:
        rows=sorted(g['rows'],key=lambda x:x[1])
        for i,(n,off) in enumerate(rows):
            if n!=name:continue
            phys,perr=map_physical(g)
            end=rows[i+1][1] if i+1<len(rows) else (phys['size'] if phys else None)
            out.append({'kind':kind,'name':name,'group':g['group'],'fragment':g['fragment'],'offset':off,'end':end,'spanBytes':(end-off if end is not None and end>=off else None),'tableApk':g['tableApk'],'physical':phys,'physicalError':perr})
    # Deduplicate identical physical coordinates repeated across table copies.
    ded={}
    for r in out:
        p=r.get('physical') or {};key=(p.get('apk'),p.get('entry'),r.get('offset'),r.get('end'))
        ded[key]=r
    return list(ded.values())

bundle_dir=local/'bundles';bundle_dir.mkdir(parents=True,exist_ok=True)
extract_log=[];unresolved_extract=[]

def valid_unityfs(p):
    try:
        with p.open('rb') as f:return f.read(7)==b'UnityFS'
    except:return False

def resolve_location(rec):
    lm=row_matches('logical',rec['logicalName']);am=row_matches('alias',rec.get('aliasName')) if rec.get('aliasName') else []
    if not lm:return None,{'reason':'logical_row_not_found','logicalName':rec['logicalName'],'aliasName':rec.get('aliasName')}
    # Keep only rows with physical fragment + positive span.
    lm=[x for x in lm if x.get('physical') and isinstance(x.get('spanBytes'),int) and x['spanBytes']>0]
    if not lm:return None,{'reason':'logical_row_has_no_resolvable_physical_fragment','logicalName':rec['logicalName']}
    # If alias exists in table, require concordance with logical coordinate.
    if am:
        concord=[]
        for l in lm:
            lp=l['physical']
            for a in am:
                ap=a.get('physical') or {}
                if a.get('offset')==l.get('offset') and ap.get('apk')==lp.get('apk') and ap.get('entry')==lp.get('entry'):
                    concord.append(l);break
        if not concord:
            return None,{'reason':'logical_alias_offset_mismatch','logicalMatches':lm,'aliasMatches':am}
        lm=concord
    # Exact physical coordinate must be unique.
    coords={(x['physical']['apk'],x['physical']['entry'],x['offset'],x['spanBytes']) for x in lm}
    if len(coords)!=1:return None,{'reason':'ambiguous_logical_physical_coordinates','matches':lm}
    return lm[0],None

def carve_bundle(bid):
    rec=bundles.get(bid)
    if not rec:
        unresolved_extract.append({'bundleId':bid,'reason':'bundle_not_in_gameres'});return None
    dst=bundle_dir/f'bundle-{bid}.bundle'
    if dst.is_file() and valid_unityfs(dst):
        extract_log.append({'bundleId':bid,'source':'reused-local-unityfs','path':str(dst),'bytes':dst.stat().st_size});return dst
    loc,err=resolve_location(rec)
    if not loc:
        unresolved_extract.append({'bundleId':bid,**(err or {'reason':'location_unresolved'})});return None
    phys=loc['physical'];off=int(loc['offset']);span=int(loc['spanBytes']);decl=int(rec.get('declaredBytes') or 0)
    # The canonical declared bundle size is preferred only when it fits inside the exact table span.
    n=decl if 0<decl<=span else span
    try:
        with zipfile.ZipFile(phys['apk']) as z,z.open(phys['entry'],'r') as src,dst.open('wb') as fh:
            try:src.seek(off)
            except Exception:
                left=off
                while left:
                    c=src.read(min(left,1024*1024))
                    if not c:raise EOFError('EOF before bundle offset')
                    left-=len(c)
            remaining=n
            while remaining:
                c=src.read(min(remaining,1024*1024))
                if not c:raise EOFError('EOF during bundle carve')
                fh.write(c);remaining-=len(c)
    except Exception as e:
        dst.unlink(missing_ok=True);unresolved_extract.append({'bundleId':bid,'reason':'carve_exception','error':f'{type(e).__name__}:{e}','location':loc});return None
    sig=dst.read_bytes()[:7] if dst.is_file() else b''
    if sig!=b'UnityFS':
        bad={'bundleId':bid,'reason':'invalid_unityfs_signature','signatureHex':sig.hex(),'bytes':dst.stat().st_size if dst.exists() else 0,'location':loc,'declaredBytes':decl,'carveBytes':n}
        unresolved_extract.append(bad);dst.unlink(missing_ok=True);return None
    extract_log.append({'bundleId':bid,'source':'current-apk-offset-table','path':str(dst),'bytes':dst.stat().st_size,'declaredBytes':decl,'tableSpanBytes':span,'logicalName':rec['logicalName'],'aliasName':rec.get('aliasName'),'location':loc})
    return dst

bundle_files=[]
for bid in selected:
    p=carve_bundle(bid)
    if p:bundle_files.append((bid,p))
if not any(bid==target_bid for bid,_ in bundle_files):
    diag=next((x for x in unresolved_extract if x.get('bundleId')==target_bid),{'reason':'unknown'})
    report.write_text('WfGg Last War — FORMATION EXACT PPtr AUDIT V2\n\nTARGET EXTRACTION FAILED\n'+json.dumps(diag,ensure_ascii=False,indent=2)+'\n','utf-8')
    raise SystemExit('TARGET_BUNDLE_EXTRACTION_FAILED '+json.dumps(diag,ensure_ascii=False,separators=(',',':')))

print('FORMATION_PTR_V2_EXTRACT',f'mode={selection_mode}',f'closure={len(full_closure)}',f'selected={len(selected)}',f'extracted={len(bundle_files)}',f'unresolvedBundles={len(unresolved_extract)}')
for x in extract_log[:8]:print('FORMATION_PTR_V2_BUNDLE',x['bundleId'],x['source'],x['bytes'])

# ---------------- exact serialized PPtr graph ----------------
env=UnityPy.load(*[str(p) for _,p in bundle_files])
container=getattr(env,'container',{}) or {}
root=container.get(target_asset)
if root is None:
    matches=[v for k,v in container.items() if str(k).lower()==target_asset.lower()]
    if len(matches)==1:root=matches[0]
if root is None:
    nearby=[str(k) for k in container if 'uiheropvpformationpanel' in str(k).lower()]
    raise SystemExit('TARGET_PREFAB_CONTAINER_ENTRY_NOT_FOUND exactPathRequired=true nearby='+repr(nearby[:20]))
# Some UnityPy versions expose a PPtr in container rather than ObjectReader.
if not hasattr(root,'assets_file'):
    for meth in ('get_obj','deref'):
        fn=getattr(root,meth,None)
        if callable(fn):
            try:
                rr=fn()
                if rr is not None:root=rr;break
            except:pass
if not hasattr(root,'assets_file'):raise SystemExit('TARGET_CONTAINER_VALUE_NOT_OBJECT_READER')

def af_name(af):
    for k in ('name','path'):
        v=getattr(af,k,None)
        if v:return str(v)
    return '<serialized-file>'
def af_clean(s):
    s=str(s).replace('\\','/').strip();s=re.sub(r'^archive:/+','',s,flags=re.I)
    return s.lower()
def ext_info(reader,file_id):
    if file_id<=0:return None
    exts=getattr(reader.assets_file,'externals',[]) or [];i=file_id-1
    if not (0<=i<len(exts)):return {'fileID':file_id,'invalidExternalIndex':True}
    ex=exts[i]
    return {'fileID':file_id,'path':str(getattr(ex,'path','')),'guid':str(getattr(ex,'guid','')) if getattr(ex,'guid',None) is not None else None,'type':getattr(ex,'type',None)}
def otype(r):
    t=getattr(r,'type',None);return getattr(t,'name',str(t) if t is not None else 'Unknown')
def oname(r):
    try:return str(r.peek_name()) if r.peek_name() is not None else None
    except:return None
def okey(r):return f"{af_name(r.assets_file)}#{int(r.path_id)}"

# Build exact loaded serialized-file index from actual ObjectReaders, not asset names.
loaded_files={}
file_keys=defaultdict(set)
for r in list(getattr(env,'objects',[]) or []):
    af=r.assets_file;fid=id(af);loaded_files[fid]=af
    nm=af_name(af);clean=af_clean(nm);file_keys[clean].add(fid);file_keys[Path(clean).name].add(fid)

def read_tree(r):
    try:return r.read_typetree(),None
    except Exception as e:
        try:return r.read_typetree(check_read=False),f'check_read_false_after:{type(e).__name__}'
        except Exception as e2:return None,f'{type(e).__name__}:{e} | fallback {type(e2).__name__}:{e2}'
def is_pp(v):return isinstance(v,dict) and isinstance(v.get('m_FileID'),int) and isinstance(v.get('m_PathID'),int)
def walk(v,path='$'):
    if is_pp(v):yield path,int(v['m_FileID']),int(v['m_PathID']);return
    if isinstance(v,dict):
        for k,x in v.items():yield from walk(x,path+'.'+str(k))
    elif isinstance(v,(list,tuple)):
        for i,x in enumerate(v):yield from walk(x,f'{path}[{i}]')

def deref(r,file_id,path_id):
    if path_id==0:return None,None
    if file_id==0:
        d=getattr(r.assets_file,'objects',{}).get(path_id);return d,(None if d is not None else 'local_pathid_not_found')
    ei=ext_info(r,file_id)
    ep=(ei or {}).get('path') or ''
    if not ep:return None,'external_path_empty'
    clean=af_clean(ep);ids=set(file_keys.get(clean,set()))|set(file_keys.get(Path(clean).name,set()))
    if len(ids)!=1:return None,('external_serialized_file_not_loaded' if not ids else f'external_serialized_file_ambiguous count={len(ids)}')
    af=loaded_files[next(iter(ids))];d=getattr(af,'objects',{}).get(path_id)
    return d,(None if d is not None else 'external_pathid_not_found')

def rel_for(src,path):
    p=path.lower()
    if src=='GameObject' and 'm_component' in p:return 'component_ref',True
    if src in ('Transform','RectTransform') and ('m_father' in p or 'm_children' in p):return 'hierarchy_ref',True
    if 'm_material' in p:return 'material_ref',True
    if 'm_mesh' in p:return 'mesh_ref',True
    if 'm_sprite' in p:return 'sprite_ref',True
    if 'm_texture' in p or 'texenv' in p:return 'texture_ref',True
    if 'm_shader' in p:return 'shader_ref',True
    if 'm_gameobject' in p:return 'gameobject_ref',True
    if 'm_script' in p:return 'script_ref',False
    return 'serialized_ref',False

STATE_TYPES={'GameObject','Transform','RectTransform','MeshRenderer','SkinnedMeshRenderer','MeshFilter','Renderer','CanvasRenderer','Canvas','Camera','Light','Material','Texture2D','Sprite','Animator','Animation','ParticleSystem','ParticleSystemRenderer'}
SKIP_KEYS={'m_VertexData','m_IndexBuffer','m_StreamData','image data','m_ImageData','m_AudioData','m_Shapes'}
def scalar(v,path='$',omitted=None,depth=0):
    if omitted is None:omitted=[]
    if depth>24:omitted.append(path+':depth_limit');return None
    if v is None or isinstance(v,(bool,int,float,str)):return v
    if is_pp(v):return {'m_FileID':v['m_FileID'],'m_PathID':v['m_PathID']}
    if isinstance(v,(bytes,bytearray,memoryview)):omitted.append(path+f':binary_bytes={len(v)}');return {'_omittedBinaryBytes':len(v)}
    if isinstance(v,dict):
        z={}
        for k,x in v.items():
            kp=path+'.'+str(k)
            if str(k) in SKIP_KEYS:
                try:n=len(x)
                except:n=None
                omitted.append(kp+(f':len={n}' if n is not None else ''));continue
            z[str(k)]=scalar(x,kp,omitted,depth+1)
        return z
    if isinstance(v,(list,tuple)):
        if len(v)>512:omitted.append(path+f':array_len={len(v)}');return {'_omittedArrayLength':len(v)}
        return [scalar(x,f'{path}[{i}]',omitted,depth+1) for i,x in enumerate(v)]
    d=getattr(v,'__dict__',None)
    if isinstance(d,dict):return scalar({k:x for k,x in d.items() if not k.startswith('_')},path,omitted,depth+1)
    return str(v)

nodes={};edges=[];unresolved=[];parse_errors=[];q=deque([root]);seen=set();MAX_OBJECTS=120000
while q:
    r=q.popleft();k=okey(r)
    if k in seen:continue
    if len(seen)>=MAX_OBJECTS:raise SystemExit('PPTR_GRAPH_OBJECT_LIMIT_EXCEEDED')
    seen.add(k);typ=otype(r);tree,warn=read_tree(r);node={'id':k,'serializedFile':af_name(r.assets_file),'pathID':int(r.path_id),'type':typ,'name':oname(r)}
    if warn:node['typetreeWarning']=warn
    if typ in STATE_TYPES and tree is not None:
        om=[];node['renderState']=scalar(tree,omitted=om)
        if om:node['renderStateOmitted']=om
    nodes[k]=node
    if tree is None:parse_errors.append({'object':k,'type':typ,'error':warn});continue
    for fp,fid,pid in walk(tree):
        if pid==0:continue
        d,derr=deref(r,fid,pid);ei=ext_info(r,fid);rel,eligible=rel_for(typ,fp)
        if d is not None:
            dk=okey(d);edges.append({'from':k,'to':dk,'relation':rel,'fieldPath':fp,'fileID':fid,'pathID':pid,'proof':'serialized_pptr','confidence':'serialized_exact','renderEligible':eligible,'external':ei})
            if dk not in seen:q.append(d)
        else:
            ep=(ei or {}).get('path') or af_name(r.assets_file);uk=f"unresolved:{ep}#{pid}"
            edges.append({'from':k,'to':uk,'relation':rel,'fieldPath':fp,'fileID':fid,'pathID':pid,'proof':'serialized_pptr_value','confidence':'serialized_exact_target_unresolved','renderEligible':eligible,'external':ei,'resolutionError':derr})
            unresolved.append({'from':k,'sourceType':typ,'fieldPath':fp,'fileID':fid,'pathID':pid,'external':ei,'resolutionError':derr})

# Deduplicate identical edges from typetree aliases.
uniq={}
for e in edges:uniq[(e['from'],e['to'],e['fieldPath'],e['fileID'],e['pathID'])]=e
edges=list(uniq.values())
rels=Counter(e['relation'] for e in edges);confs=Counter(e['confidence'] for e in edges);types=Counter(n['type'] for n in nodes.values())
render_exact=[e for e in edges if e['renderEligible'] and e['confidence']=='serialized_exact']
render_unresolved=[e for e in edges if e['renderEligible'] and e['confidence']!='serialized_exact']
result={'format':'WFGG_LASTWAR_FORMATION_PPTR_EXACT_V2','target':{'assetPath':target_asset,'bundleId':target_bid,'rootObject':okey(root),'rootType':otype(root),'rootName':oname(root)},'catalogSource':{'gameres':str(gameres),'gameresSha256':hashlib.sha256(gameres.read_bytes()).hexdigest()},'dependencySelection':{'mode':selection_mode,'fullClosureCount':len(full_closure),'selectedCount':len(selected),'fullClosureBundleIds':full_closure,'selectedBundleIds':selected},'extraction':{'bundles':extract_log,'unresolvedBundles':unresolved_extract},'counts':{'objects':len(nodes),'edges':len(edges),'renderExactEdges':len(render_exact),'renderUnresolvedEdges':len(render_unresolved),'unresolvedRefs':len(unresolved),'parseErrors':len(parse_errors),'objectTypes':dict(types),'relations':dict(rels),'confidence':dict(confs)},'fidelityPolicy':{'noGuessing':True,'bundleLocationFromCurrentApkTables':True,'logicalAliasConcordanceRequiredWhenAliasTableEntryExists':True,'unityFSSignatureRequired':True,'bundleDependencyIsNotVisualProof':True,'certificationBlockedIfRenderUnresolved':bool(render_unresolved),'certificationBlockedIfRenderStateOmitted':any(n.get('renderStateOmitted') for n in nodes.values())},'nodes':list(nodes.values()),'edges':edges,'unresolvedRefs':unresolved,'parseErrors':parse_errors,'guardrails':{'globalBundleScan':False,'candidateNameMatching':False,'installedGameReadOnly':True,'mainUntouched':True},'elapsedSeconds':round(time.time()-t0,3)}
out.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n','utf-8')
lines=['WfGg Last War — FORMATION EXACT PPtr AUDIT V2','',f'targetAsset={target_asset}',f'targetBundle={target_bid}',f'root={result["target"]["rootObject"]}',f'dependencyMode={selection_mode} fullClosure={len(full_closure)} selected={len(selected)} extracted={len(bundle_files)} unresolvedBundles={len(unresolved_extract)}',f'objects={len(nodes)} edges={len(edges)} renderExact={len(render_exact)} renderUnresolved={len(render_unresolved)} unresolvedRefs={len(unresolved)} parseErrors={len(parse_errors)} elapsed={result["elapsedSeconds"]}','relations='+json.dumps(dict(rels),ensure_ascii=False),'confidence='+json.dumps(dict(confs),ensure_ascii=False),'','RULE: only current-APK offset-table coordinates and serialized PPtr values are facts.','RULE: unresolved target remains unresolved; no substitute is selected.','']
for e in render_exact[:160]:lines.append(f"EXACT {e['from']} --{e['relation']} {e['fieldPath']} fileID={e['fileID']} pathID={e['pathID']}--> {e['to']}")
for e in render_unresolved[:160]:lines.append(f"UNRESOLVED_RENDER {e['from']} --{e['relation']} {e['fieldPath']} fileID={e['fileID']} pathID={e['pathID']}--> {e['to']} error={e.get('resolutionError')}")
report.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_PTR_EXACT_V2_OK',f'objects={len(nodes)}',f'edges={len(edges)}',f'renderExact={len(render_exact)}',f'renderUnresolved={len(render_unresolved)}',f'unresolved={len(unresolved)}',f'elapsed={result["elapsedSeconds"]}')
print('FORMATION_PTR_V2_TARGET',target_asset,'bundle='+str(target_bid),'root='+okey(root))
print('FORMATION_PTR_V2_DEPENDENCIES',f'mode={selection_mode}',f'full={len(full_closure)}',f'selected={len(selected)}',f'extracted={len(bundle_files)}')
for e in render_exact[:24]:print('FORMATION_PTR_V2_EXACT',e['relation'],e['fieldPath'],'->',e['to'])
for e in render_unresolved[:24]:print('FORMATION_PTR_V2_UNRESOLVED_RENDER',e['relation'],e['fieldPath'],'->',e['to'])
print('FORMATION_PTR_V2_JSON',out)
print('FORMATION_PTR_V2_REPORT',report)
PYEOF

python "$PY" "$GAMERES" "$TARGET_ASSET" "$EXPECTED_BUNDLE" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" "${APKS[@]}"

size="$(wc -c < "$OUT" | tr -d ' ')"
if [[ "$size" -ge 90000000 ]]; then fail "audit JSON trop gros pour GitHub (${size} bytes); empaquetage requis"; fi
git add "$OUT"
if ! git diff --cached --quiet; then git commit -m "lab: map exact Formation PPtr graph from live APK tables"; fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION EXACT PPtr AUDIT V2 TERMINE ===' "JSON: $OUT" "Rapport: $REPORT" 'Aucune liaison candidate promue.'
