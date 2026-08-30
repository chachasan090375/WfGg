#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — GRAPHICS MASTER INDEX
# Canonical reusable map for future visual reverse-engineering work.
# Rebuilds assetPath -> bundle -> alias/logical -> fragment/group/offset/span,
# dependencies/dependents, and links every generated metadata/audit JSON.
# Read-only against installed APKs. Commits only the generated index files.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
META="$ROOT/frontend/lab/master-assets-v2/meta"
IDX="$ROOT/frontend/lab/master-assets-v2/index"
OUT="$IDX/lastwar-graphics-master-index-v1.json"
TSV="$IDX/lastwar-graphics-asset-path-index-v1.tsv"
MD="$IDX/README_LASTWAR_GRAPHICS_INDEX.md"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_GRAPHICS_MASTER_INDEX.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$IDX" "$META" "$(dirname "$REPORT")"

python - "$GAMERES" "$META" "$OUT" "$TSV" "$MD" "$REPORT" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, Counter
import csv,hashlib,json,re,struct,sys,zipfile

gameres=Path(sys.argv[1]); meta_dir=Path(sys.argv[2]); out=Path(sys.argv[3]); tsv=Path(sys.argv[4]); md=Path(sys.argv[5]); report=Path(sys.argv[6]); apks=[Path(x) for x in sys.argv[7:]]
text=gameres.read_text('utf-8',errors='replace')

def sha256_path(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()

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
bundles={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); b={
            'bundleId':bid,
            'logicalName':p[1],
            'declaredBytes':int(p[3]),
            'assetPathIds':[int(x) for x in p[4].split('|') if x],
            'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],
            'groups':[x for x in p[6].split('|') if x],
            'aliasName':p[7],
        }
        b['assetPaths']=[paths[x] for x in b['assetPathIds'] if x in paths]
        bundles[bid]=b
    except:pass
by_logical={b['logicalName']:b for b in bundles.values()}
by_alias={b['aliasName']:b for b in bundles.values() if b['aliasName']}
asset_to_bundle={}
for b in bundles.values():
    for p in b['assetPaths']:asset_to_bundle[p]=b['bundleId']
dependents=defaultdict(list)
for b in bundles.values():
    for d in b['dependencyBundleIds']:dependents[d].append(b['bundleId'])

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
            offv=struct.unpack_from('<Q',buf,pos)[0];pos+=8; rows.append((name,int(offv)))
        groups.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return groups

def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())

tables={'logical':[],'alias':[]}; physical=[]; apk_info=[]
for apk in apks:
    ai={'basename':apk.name,'path':str(apk),'bytes':None}
    try:ai['bytes']=apk.stat().st_size
    except:pass
    apk_info.append(ai)
    try:
        with zipfile.ZipFile(apk) as z:
            names=z.namelist(); ns=set(names)
            for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
                if entry in ns:
                    try:
                        for g in parse_offsets(z.read(entry)):
                            tables[kind].append({**g,'tableApk':apk.name,'tableEntry':entry})
                    except Exception:pass
            for n in names:
                lo=n.lower()
                if 'assets/assetbundles/' in lo and 'bundlefragment' in lo and lo.endswith('.bytes'):
                    physical.append({'apk':apk.name,'apkPath':str(apk),'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})
    except Exception:pass

def physical_match(fragment,group):
    nf=norm(fragment); ranked=[]
    for p in physical:
        nb=norm(p['base']); ns=norm(p['stem']);score=0
        if nf and (nf==nb or nf==ns):score=100
        elif nf and (nf in nb or nb in nf or nf in ns or ns in nf):score=80
        if re.search(rf'fragment0*{group}(?:\D|$)',p['base'],re.I):score=max(score,60)
        ranked.append((score,p))
    ranked.sort(key=lambda x:(-x[0],x[1]['base']))
    if ranked and ranked[0][0]>0:return ranked[0][1],ranked[0][0]
    if len(physical)==1:return physical[0],20
    ps=sorted(physical,key=lambda x:x['base'])
    if 0<=group<len(ps):return ps[group],10
    return None,0

locations=defaultdict(lambda:{'logical':[],'alias':[]})
for kind,gs in tables.items():
    for g in gs:
        rows=sorted(g['rows'],key=lambda x:x[1])
        phys,psc=physical_match(g['fragment'],g['group'])
        for i,(name,start) in enumerate(rows):
            b=by_alias.get(name) if kind=='alias' else by_logical.get(name)
            if not b:continue
            end=rows[i+1][1] if i+1<len(rows) else (phys['size'] if phys else None)
            loc={
                'identity':kind,'rowName':name,'group':g['group'],'tableFragment':g['fragment'],
                'offset':start,'end':end,'spanBytes':(end-start if end is not None and end>=start else None),
                'tableApk':g['tableApk'],'tableEntry':g['tableEntry'],
                'physicalMatchConfidence':psc,
            }
            if phys:
                loc.update({'physicalApk':phys['apk'],'fragmentEntry':phys['entry'],'fragmentBytes':phys['size']})
            locations[b['bundleId']][kind].append(loc)

# Link every audit JSON to affected bundle IDs, while preserving the source file itself as canonical evidence.
def iter_dicts(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():yield from iter_dicts(v)
    elif isinstance(x,list):
        for v in x:yield from iter_dicts(v)

evidence_files=[]; evidence_by_bundle=defaultdict(list); discovery_formats=Counter()
for jf in sorted(meta_dir.glob('*.json')):
    if jf.resolve()==out.resolve():continue
    try:
        raw=jf.read_bytes(); obj=json.loads(raw.decode('utf-8','replace'))
    except:continue
    fmt=str(obj.get('format','')) if isinstance(obj,dict) else ''
    if fmt:discovery_formats[fmt]+=1
    touched=set()
    for d in iter_dicts(obj):
        bid=d.get('bundleId')
        if isinstance(bid,int) and bid in bundles:touched.add(bid)
        ln=d.get('logicalName')
        if isinstance(ln,str) and ln in by_logical:touched.add(by_logical[ln]['bundleId'])
        al=d.get('aliasName')
        if isinstance(al,str) and al in by_alias:touched.add(by_alias[al]['bundleId'])
        aps=d.get('assetPaths')
        if isinstance(aps,list):
            for ap in aps:
                if isinstance(ap,str) and ap in asset_to_bundle:touched.add(asset_to_bundle[ap])
        ap=d.get('assetPath')
        if isinstance(ap,str) and ap in asset_to_bundle:touched.add(asset_to_bundle[ap])
    rec={'file':str(jf.relative_to(meta_dir.parent.parent.parent)) if len(jf.parents)>=3 else str(jf),'basename':jf.name,'format':fmt,'sha256':hashlib.sha256(raw).hexdigest(),'bundleIds':sorted(touched)}
    evidence_files.append(rec)
    for bid in touched:evidence_by_bundle[bid].append(jf.name)

records=[]
for bid in sorted(bundles):
    b=bundles[bid]
    loc=locations.get(bid,{'logical':[],'alias':[]})
    preferred=(loc['alias'] or loc['logical'])
    records.append({
        **b,
        'dependentBundleIds':sorted(dependents.get(bid,[])),
        'locations':loc,
        'preferredExtraction':(preferred[0] if preferred else None),
        'evidenceFiles':sorted(set(evidence_by_bundle.get(bid,[]))),
    })

index={
 'format':'WFGG_LASTWAR_GRAPHICS_MASTER_INDEX_V1',
 'purpose':'Reusable canonical map for Last War visual assets and reconstruction paths.',
 'source':{'gameresPath':str(gameres),'gameresSha256':sha256_path(gameres),'installedApks':apk_info},
 'counts':{'directories':len(dirs),'assetPaths':len(paths),'bundles':len(bundles),'physicalFragments':len(physical),'logicalGroups':len(tables['logical']),'aliasGroups':len(tables['alias']),'evidenceJsonFiles':len(evidence_files)},
 'lookup':{
   'assetPathToBundleId':asset_to_bundle,
   'logicalNameToBundleId':{k:v['bundleId'] for k,v in by_logical.items()},
   'aliasNameToBundleId':{k:v['bundleId'] for k,v in by_alias.items()},
 },
 'bundles':records,
 'evidenceFiles':evidence_files,
 'discoveryFormats':dict(discovery_formats),
 'reconstructionRecipe':{
   'steps':['Resolve exact asset path in lookup.assetPathToBundleId','Open bundle record','Prefer alias location when available, otherwise logical','Use physicalApk + fragmentEntry + offset + spanBytes to extract raw AssetBundle','Load extracted bundle with UnityPy','Follow dependencyBundleIds recursively for missing meshes/materials/textures/scripts','Use evidenceFiles to reuse already-audited hierarchy/CLR/material findings instead of rescanning'],
   'identityPriority':['alias','logical'],
   'requiredFields':['bundleId','logicalName','aliasName','assetPaths','dependencyBundleIds','locations','preferredExtraction','evidenceFiles'],
 },
 'guardrails':{'installedGameReadOnly':True,'mainUntouched':True,'indexGeneratedFromCanonicalCatalog':True}
}
out.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n','utf-8')

# Flat, grep-friendly path index: one row per asset path, with preferred physical extraction coordinates.
with tsv.open('w',encoding='utf-8',newline='') as f:
    w=csv.writer(f,delimiter='\t',lineterminator='\n')
    w.writerow(['assetPath','bundleId','logicalName','aliasName','declaredBytes','dependencies','group','tableFragment','fragmentEntry','offset','spanBytes','identity','confidence','evidenceFiles'])
    for r in records:
        p=r.get('preferredExtraction') or {}
        for ap in r['assetPaths']:
            w.writerow([ap,r['bundleId'],r['logicalName'],r['aliasName'],r['declaredBytes'],'|'.join(map(str,r['dependencyBundleIds'])),p.get('group',''),p.get('tableFragment',''),p.get('fragmentEntry',''),p.get('offset',''),p.get('spanBytes',''),p.get('identity',''),p.get('physicalMatchConfidence',''),'|'.join(r['evidenceFiles'])])

md_lines=[
 '# WfGg — Last War Graphics Master Index', '',
 'Cet index est le point d’entrée canonique pour les futurs travaux graphiques Last War.', '',
 f"- Assets catalogués : **{len(paths)}**",
 f"- Bundles : **{len(bundles)}**",
 f"- Fragments physiques : **{len(physical)}**",
 f"- Rapports JSON liés : **{len(evidence_files)}**", '',
 '## Fichiers', '',
 '- `lastwar-graphics-master-index-v1.json` : index complet machine-readable.',
 '- `lastwar-graphics-asset-path-index-v1.tsv` : lookup rapide/grep par chemin.', '',
 '## Chemin de reconstruction', '',
 '`assetPath → bundleId → logical/alias → fragment/groupe/offset/span → dépendances → UnityPy → hiérarchie/meshes/matériaux/textures`', '',
 'Pour chaque futur audit, conserver le JSON source dans `master-assets-v2/meta/` puis relancer `scripts/lastwar-graphics-master-index-refresh.sh`.', '',
 '## Règle de projet', '',
 'Ne pas recommencer un scan global avant d’avoir interrogé cet index et les `evidenceFiles` du bundle concerné.', ''
]
md.write_text('\n'.join(md_lines),'utf-8')

rep=[
 'WfGg Last War — GRAPHICS MASTER INDEX','',
 f'gameresSha256={index["source"]["gameresSha256"]}',
 f'assetPaths={len(paths)} bundles={len(bundles)} fragments={len(physical)} evidence={len(evidence_files)}',
 f'json={out}',f'tsv={tsv}',f'md={md}','',
 'RECONSTRUCTION: assetPath -> bundleId -> alias/logical -> fragment/group/offset/span -> dependencies -> UnityPy'
]
report.write_text('\n'.join(rep)+'\n','utf-8')
print('LASTWAR_GRAPHICS_MASTER_INDEX_OK',f'assets={len(paths)}',f'bundles={len(bundles)}',f'fragments={len(physical)}',f'evidence={len(evidence_files)}')
print('LASTWAR_GRAPHICS_MASTER_INDEX_JSON',out)
print('LASTWAR_GRAPHICS_MASTER_INDEX_TSV',tsv)
print('LASTWAR_GRAPHICS_MASTER_INDEX_MD',md)
print('LASTWAR_GRAPHICS_MASTER_INDEX_REPORT',report)
PY

git add scripts/lastwar-graphics-master-index-refresh.sh "$OUT" "$TSV" "$MD"
if ! git diff --cached --quiet; then
  git commit -m "lab: refresh Last War graphics master index"
  git push origin "$BRANCH"
fi

echo "=== LAST WAR GRAPHICS MASTER INDEX TERMINE ==="
echo "JSON: $OUT"
echo "TSV : $TSV"
echo "Doc : $MD"
echo "Rapport: $REPORT"
echo "main non modifie."
