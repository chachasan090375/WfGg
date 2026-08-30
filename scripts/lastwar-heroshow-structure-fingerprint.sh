#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — locate the HeroShow scene/prefab by structural fingerprint.
# Strong fingerprints come from recovered CLR code:
#   GameObjects Camp_<level>
#   MonoBehaviour fields level/shadowDistance/IsAddGrabCamera/unitySHParamNames
# GrabCamera is runtime-created, so it is only a bonus if serialized anywhere.
# Read-only against installed APKs. Preview/main untouched.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-heroshow-fingerprint-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/heroshow-structure-fingerprint-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_HEROSHOW_STRUCTURE_FINGERPRINT.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-heroshow-structure-fingerprint.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$LOCAL"/*.bundle

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter
import contextlib,io,json,re,struct,sys,zipfile,time

local=Path(sys.argv[1]); gameres=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); unity=sys.argv[5]; apks=[Path(x) for x in sys.argv[6:]]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity
text=gameres.read_text('utf-8',errors='replace')

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
bundles={}; by_logical={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); b={'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
        b['assetPaths']=[paths.get(x,'') for x in b['assetPathIds'] if paths.get(x)]
        bundles[bid]=b; by_logical[b['logicalName']]=b
    except:pass

def read7(buf,pos):
    out=0;shift=0
    while True:
        if pos>=len(buf):raise ValueError('7bit EOF')
        x=buf[pos];pos+=1;out|=(x&0x7f)<<shift
        if not x&0x80:return out,pos
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

groups=[]; physical=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            ns=set(z.namelist()); entry='assets/AssetBundles/BundleOffsetTable.bytes'
            if entry in ns:
                for g in parse_offsets(z.read(entry)):groups.append({**g,'tableApk':str(apk)})
            for n in z.namelist():
                lo=n.lower()
                if 'assets/assetbundles/' in lo and 'bundlefragment' in lo and lo.endswith('.bytes'):
                    physical.append({'apk':str(apk),'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})
    except Exception as e:print('APK_WARNING',apk.name,repr(e))
if not physical:raise SystemExit('NO_BUNDLE_FRAGMENT')
print('HEROSHOW_FP_SOURCE',f'fragments={len(physical)}',f'groups={len(groups)}',f'bundles={len(bundles)}')

def match_group(p):
    ranked=[]
    nb=norm(p['base']); ns=norm(p['stem'])
    for g in groups:
        nf=norm(g['fragment']);sc=0
        if nf and (nf==nb or nf==ns):sc=100
        elif nf and (nf in nb or nb in nf or nf in ns or ns in nf):sc=80
        if re.search(rf'fragment0*{g["group"]}(?:\D|$)',p['base'],re.I):sc=max(sc,60)
        ranked.append((sc,g))
    ranked.sort(key=lambda x:-x[0])
    if ranked and ranked[0][0]>0:return ranked[0][1],ranked[0][0]
    if len(groups)==1:return groups[0],20
    return None,0

intervals=[]
for p in physical:
    g,msc=match_group(p)
    if not g:continue
    rows=sorted(g['rows'],key=lambda x:x[1])
    for i,(name,off) in enumerate(rows):
        end=rows[i+1][1] if i+1<len(rows) else p['size']
        if end<=off or end>p['size']:continue
        b=by_logical.get(name)
        blob=' '.join(([name]+(b.get('assetPaths',[]) if b else []))).lower()
        pathscore=0
        for pat,w in [('heroshow',120),('hero_show',120),('formation',100),('pvp',40),('camp',80),('hero',35),('show',25),('character',15),('role',15),('army',15),('preview',20),('display',20)]:
            if pat in blob:pathscore+=w
        intervals.append({'physical':p,'group':g['group'],'matchScore':msc,'logicalName':name,'start':off,'end':end,'bytes':end-off,'bundle':b,'pathScore':pathscore})
print('HEROSHOW_FP_INTERVALS',f'count={len(intervals)}',f'pathCandidates={sum(x["pathScore"]>0 for x in intervals)}')

fieldset={'level','shadowDistance','IsAddGrabCamera','unitySHParamNames'}
camp_rx=re.compile(r'^Camp_\d+$',re.I)
key_rx=re.compile(r'^(?:Camp_\d+|GrabCamera)$|HeroShow|Formation|Grass|Ground|Rock|Stone|Tree|Shadow',re.I)

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

def read_obj(r):
    try:return r.read()
    except:
        try:return r.parse_as_object()
        except:return None

def objname(o):return '' if o is None else str(getattr(o,'m_Name','') or getattr(o,'name','') or '')

def scan_interval(it,idx):
    n=it['bytes']
    if n<=0 or n>180_000_000:return None
    dest=local/f'candidate_{idx:05d}.bundle'
    p=it['physical']
    try:
        with zipfile.ZipFile(p['apk']) as z,z.open(p['entry']) as f:
            left=it['start']
            while left:
                c=f.read(min(left,1024*1024))
                if not c:raise RuntimeError('seek EOF')
                left-=len(c)
            blob=f.read(n)
        if len(blob)!=n:raise RuntimeError(f'short {len(blob)}/{n}')
        dest.write_bytes(blob)
        sink=io.StringIO()
        with contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
            env=UnityPy.load(str(dest)); readers=list(env.objects)
    except Exception:
        try:dest.unlink()
        except:pass
        return None
    names=[]; camps=[]; grab=[]; mono_scripts=[]; fingerprints=[]; typecounts=Counter()
    transforms=[]; gameobjects={}
    for r in readers:
        try:t=r.type.name
        except:t=str(getattr(r,'type',''))
        typecounts[t]+=1
        if t=='GameObject':
            o=read_obj(r); nm=objname(o); rid=pidof(r)
            if nm:
                names.append(nm);gameobjects[rid]=nm
                if camp_rx.match(nm):camps.append(nm)
                if nm=='GrabCamera':grab.append(nm)
        elif t=='MonoScript':
            o=read_obj(r)
            if o is not None:
                cn=str(getattr(o,'m_ClassName','') or objname(o)); ns=str(getattr(o,'m_Namespace','') or ''); asm=str(getattr(o,'m_AssemblyName','') or '')
                if cn:mono_scripts.append({'className':cn,'namespace':ns,'assembly':asm})
        elif t=='MonoBehaviour':
            keys=[]
            try:
                tree=r.read_typetree()
                if isinstance(tree,dict):keys=list(tree.keys())
            except:pass
            hit=sorted(fieldset.intersection(keys))
            if hit:fingerprints.append({'pathId':pidof(r),'matchedFields':hit,'allFields':keys[:120]})
        elif t in ('Transform','RectTransform'):
            o=read_obj(r)
            if o is not None:
                gp=getattr(o,'m_GameObject',None); pa=getattr(o,'m_Father',None)
                transforms.append({'pathId':pidof(r),'gameObjectPathId':pidof(gp),'parent':pidof(pa)})
    script_hit=[s for s in mono_scripts if s['className']=='HeroShowSetting']
    full_fp=[x for x in fingerprints if fieldset.issubset(set(x['matchedFields']))]
    score=len(set(camps))*120 + len(grab)*80 + len(script_hit)*400 + len(full_fp)*500
    if it['pathScore']>0:score+=min(it['pathScore'],100)
    if score<=0:
        try:dest.unlink()
        except:pass
        return None
    keynames=sorted({n for n in names if key_rx.search(n)})[:250]
    b=it.get('bundle') or {}
    return {'score':score,'logicalName':it['logicalName'],'bundleId':b.get('bundleId'),'assetPaths':b.get('assetPaths',[]),'bytes':n,'pathScore':it['pathScore'],'camps':sorted(set(camps)),'grabCameraSerialized':bool(grab),'heroShowScript':script_hit,'fieldFingerprints':fingerprints[:20],'keyGameObjectNames':keynames,'objectTypeCounts':dict(typecounts),'savedBundle':str(dest)}

# Phase A: plausible catalog paths first. Phase B: all remaining bundles only if no strong hit.
ordered=sorted(intervals,key=lambda x:(x['pathScore']<=0,-x['pathScore'],x['bytes']))
phaseA=[x for x in ordered if x['pathScore']>0]
phaseB=[x for x in ordered if x['pathScore']==0]
results=[]; scanned=0; t0=time.time(); strong=False

def run_phase(seq,label):
    global scanned,strong
    print('HEROSHOW_FP_PHASE',label,f'count={len(seq)}')
    for j,it in enumerate(seq,1):
        scanned+=1
        r=scan_interval(it,scanned)
        if r:
            results.append(r);results.sort(key=lambda x:-x['score'])
            print('HEROSHOW_FP_HIT',f"score={r['score']}",f"bundle={r.get('bundleId')}",f"logical={r['logicalName']}",f"camps={','.join(r['camps'][:12]) or '-'}",f"script={bool(r['heroShowScript'])}",f"fields={max((len(x['matchedFields']) for x in r['fieldFingerprints']),default=0)}")
            if r['score']>=240:
                strong=True;return
        if j%25==0:print('HEROSHOW_FP_PROGRESS',label,f'{j}/{len(seq)}',f'elapsed={int(time.time()-t0)}s')

run_phase(phaseA,'catalog')
if not strong:run_phase(phaseB,'full')
results.sort(key=lambda x:-x['score'])
summary={'format':'WFGG_LASTWAR_HEROSHOW_STRUCTURE_FINGERPRINT_V1','fragments':len(physical),'groups':len(groups),'intervals':len(intervals),'scanned':scanned,'strongHit':strong,'elapsedSeconds':round(time.time()-t0,2),'results':results[:30],'fingerprint':{'gameObject':'Camp_<level>','monoBehaviourFields':sorted(fieldset),'runtimeOnly':'GrabCamera'},'guardrails':{'apkReadOnly':True,'previewUntouched':True,'mainUntouched':True}}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — HEROSHOW STRUCTURE FINGERPRINT','',f'fragments={len(physical)} groups={len(groups)} intervals={len(intervals)} scanned={scanned} strongHit={strong} elapsed={summary["elapsedSeconds"]}s','']
for r in results[:20]:
    lines.append(f"HIT score={r['score']} bundle={r.get('bundleId')} logical={r['logicalName']}")
    if r['assetPaths']:lines.extend('  ASSET '+x for x in r['assetPaths'][:20])
    if r['camps']:lines.append('  CAMPS '+', '.join(r['camps']))
    if r['heroShowScript']:lines.append('  SCRIPT HeroShowSetting')
    for fp in r['fieldFingerprints'][:5]:lines.append('  FIELDS '+', '.join(fp['matchedFields']))
    if r['keyGameObjectNames']:lines.append('  NODES '+', '.join(r['keyGameObjectNames'][:80]))
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('HEROSHOW_STRUCTURE_FINGERPRINT_OK',f'scanned={scanned}',f'hits={len(results)}',f'strong={strong}',f'elapsed={summary["elapsedSeconds"]}')
for r in results[:10]:print('HEROSHOW_STRUCTURE_RESULT',f"score={r['score']}",f"bundle={r.get('bundleId')}",f"logical={r['logicalName']}",f"camps={','.join(r['camps'][:10]) or '-'}")
print('HEROSHOW_STRUCTURE_JSON',outp)
print('HEROSHOW_STRUCTURE_REPORT',reportp)
PYEOF

python "$PY" "$LOCAL" "$GAMERES" "$OUT" "$REPORT" "$UNITY_VERSION" "${APKS[@]}"
rm -f "$PY"

git add scripts/lastwar-heroshow-structure-fingerprint.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: fingerprint HeroShow prefab structure"
  git push origin "$BRANCH"
fi

echo "=== HEROSHOW STRUCTURE FINGERPRINT TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
