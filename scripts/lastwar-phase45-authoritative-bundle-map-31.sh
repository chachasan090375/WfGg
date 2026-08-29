#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 45
# AUTHORITATIVE GAMERES -> BUNDLE ID -> INSTALLED FRAGMENT OFFSET MAP (31/31)
# CODE ONLY · OFFLINE ONLY · no Last War network.
#
# Phase 44 exposed the real index format.  This phase stops scanning bundles by
# content similarity and uses the game's own manifest graph:
#   HeroAppearance.queue_model_path -> gameres [Paths] -> gameres [Bundles]
#   -> BundleOffsetTable/AliasOffsetTable -> exact installed Fragment offset.
#
# Important distinction recorded here:
# - "manifestMapped" means the game manifest knows the exact queue prefab.
# - "installedExact" means that exact bundle is physically present in the APK
#   BundleFragment0 currently installed on the phone.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
MAP="$ROOT/frontend/lab/lastwar-hero-formation-unit-authoritative-map.js"
P40="$ROOT/frontend/lab/master-assets-v2/meta/formation-unit-bundle-set-31.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-authoritative-bundle-map-31.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE45_AUTHORITATIVE_BUNDLE_MAP_31.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase45-authoritative-bundle-map.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$MAP" ]] || fail "référentiel 31/31 absent: $MAP"
[[ -s "$P40" ]] || fail "Phase40 absente: $P40"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "installation Last War introuvable ($PKG)"

mkdir -p "$(dirname "$OUT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import defaultdict
import hashlib, io, json, os, re, struct, sys, zipfile

mapp=Path(sys.argv[1]); p40p=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); pkg=sys.argv[5]; apks=sys.argv[6:]

# ---------- authoritative hero/unit map ----------
js=mapp.read_text(encoding='utf-8')
try:
    hero_data=json.loads(js.split('=',1)[1].rsplit(';',1)[0])
except Exception as e:
    raise SystemExit(f'cannot parse authoritative map: {e}')
entries=hero_data.get('entries') or []
if len(entries)!=31: raise SystemExit(f'expected 31 authoritative entries, got {len(entries)}')
p40=json.loads(p40p.read_text(encoding='utf-8'))
p40_by_id={int(x['heroId']):x for x in p40.get('rows',[])}

# ---------- read exact installed index files ----------
WANTED={
 'gameres':'assets/AssetBundles/gameres',
 'bundleOffsets':'assets/AssetBundles/BundleOffsetTable.bytes',
 'aliasOffsets':'assets/AssetBundles/AliasOffsetTable.bytes',
 'fragment':'assets/AssetBundles/BundleFragment0.bytes',
}
raw={}; src={}
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            names=set(z.namelist())
            for key,entry in WANTED.items():
                if key in raw or entry not in names: continue
                info=z.getinfo(entry)
                if key=='fragment':
                    # Fragment is intentionally not read into RAM; only size/source are needed.
                    raw[key]=None
                    src[key]={'apk':apk,'apkBase':os.path.basename(apk),'entry':entry,'bytes':info.file_size}
                else:
                    b=z.read(entry);raw[key]=b
                    src[key]={'apk':apk,'apkBase':os.path.basename(apk),'entry':entry,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    except Exception:
        pass
for k in WANTED:
    if k not in raw: raise SystemExit(f'missing installed index component: {k}')

# ---------- parse gameres text manifest ----------
text=raw['gameres'].decode('utf-8','strict')
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m: return []
    start=m.end(); n=re.search(r'^\[[^\]]+\]\s*$',text[start:],re.M)
    end=start+n.start() if n else len(text)
    return [x for x in text[start:end].splitlines() if x.strip()]

directories={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);directories[int(i)]=p
    except Exception:pass

paths={}; path_id_by_full={}
for ln in section('Paths'):
    try:
        pid,did,name=ln.split(',',2);pid=int(pid);did=int(did)
        full=directories[did].rstrip('/')+'/'+name
        row={'pathId':pid,'directoryId':did,'name':name,'fullPath':full}
        paths[pid]=row;path_id_by_full[full.lower()]=pid
    except Exception:pass

bundles={}; bundle_ids_by_path=defaultdict(list)
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8: continue
    try:
        bid=int(p[0]); size=int(p[3])
        asset_ids=[int(x) for x in p[4].split('|') if x]
        dep_ids=[int(x) for x in p[5].split('|') if x]
    except Exception: continue
    row={
      'bundleId':bid,'logicalName':p[1],'crc':p[2],'declaredBytes':size,
      'assetPathIds':asset_ids,'dependencyBundleIds':dep_ids,
      'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]
    }
    bundles[bid]=row
    for pid in asset_ids: bundle_ids_by_path[pid].append(bid)

# ---------- parse BundleOffsetTable/AliasOffsetTable ----------
def read7(buf,pos):
    result=0;shift=0
    while True:
        if pos>=len(buf): raise ValueError('7-bit int eof')
        x=buf[pos];pos+=1;result|=(x&0x7f)<<shift
        if not (x&0x80): return result,pos
        shift+=7
        if shift>35: raise ValueError('7-bit int overflow')

def parse_offset_table(buf):
    pos=0
    if len(buf)<4: raise ValueError('offset table short')
    fragment_count=struct.unpack_from('<I',buf,pos)[0];pos+=4
    result=[]
    for _ in range(fragment_count):
        ln,pos=read7(buf,pos); frag=buf[pos:pos+ln].decode('utf-8');pos+=ln
        payload_len=struct.unpack_from('<I',buf,pos)[0];pos+=4
        count=struct.unpack_from('<I',buf,pos)[0];pos+=4
        rec=[]
        for _ in range(count):
            ln,pos=read7(buf,pos); name=buf[pos:pos+ln].decode('utf-8');pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8
            rec.append({'name':name,'offset':off})
        result.append({'fragment':frag,'payloadBytes':payload_len,'count':count,'records':rec})
    if pos!=len(buf): raise ValueError(f'offset table trailing bytes={len(buf)-pos}')
    return result

bo=parse_offset_table(raw['bundleOffsets']); ao=parse_offset_table(raw['aliasOffsets'])
if len(bo)!=1 or len(ao)!=1: raise SystemExit(f'unexpected fragments: bundle={len(bo)} alias={len(ao)}')
if bo[0]['fragment']!='BundleFragment0.bytes' or ao[0]['fragment']!='BundleFragment0.bytes': raise SystemExit('unexpected fragment name')
if bo[0]['count']!=ao[0]['count']: raise SystemExit('bundle/alias table record count mismatch')

installed_by_logical={x['name']:x['offset'] for x in bo[0]['records']}
installed_by_alias={x['name']:x['offset'] for x in ao[0]['records']}
logical_by_offset={x['offset']:x['name'] for x in bo[0]['records']}
alias_by_offset={x['offset']:x['name'] for x in ao[0]['records']}
fragment_bytes=int(src['fragment']['bytes'])
ordered=sorted((x['offset'],x['name']) for x in bo[0]['records'])
size_by_offset={}
for i,(off,name) in enumerate(ordered):
    nxt=ordered[i+1][0] if i+1<len(ordered) else fragment_bytes
    size_by_offset[off]=nxt-off

# Strong invariant: logical and alias tables refer to the same exact physical offsets.
bo_offsets=[x['offset'] for x in bo[0]['records']]; ao_offsets=[x['offset'] for x in ao[0]['records']]
offset_tables_aligned=(bo_offsets==ao_offsets)

# ---------- helper identity logic only for labelling direct dependencies ----------
def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')
def identity_tokens(entry):
    toks=[]
    for seg in re.split(r'[/\\]',entry['queueModelPath']):
        x=re.sub(r'\.(?:prefab|fbx)$','',seg,flags=re.I)
        if x.lower().startswith('a_hero_'):
            toks.append(norm(x))
    m=re.search(r'/Soldier/([^/]+)/',entry['queueModelPath'],re.I)
    if m:toks.extend([norm(m.group(1)),'a_hero_'+norm(m.group(1))])
    p40row=p40_by_id.get(int(entry['heroId'])) or {}
    toks.extend(norm(x) for x in p40row.get('identityTokens',[]) if x)
    # General cores are only labels; they never select the main queue bundle.
    cores=[]
    for t in toks:
        s=re.sub(r'^a_hero_','',t)
        s=re.sub(r'_(?:0?1|0?2|0?3|0?4|city|world|battle|pve|pbr|zhanshi)$','',s)
        if len(s)>=4: cores.append(s)
    return sorted(set(toks),key=len,reverse=True),sorted(set(cores),key=len,reverse=True)

def classify_name(name):
    low=name.lower()
    for k in ('prefab','animation','animator','material','matetial','materail','mesh','texture'):
        if f'_{k}_' in low or low.endswith(f'_{k}.bundle'): return 'material' if k in ('matetial','materail') else k
    return 'other'

CURRENT15={50006,50007,50008,50009,50010,50019,50021,50018,50020,50013,50022,50015,50016,50014,50017}
rows=[]
for e in entries:
    hid=int(e['heroId']); q=e['queueModelPath']; qlow=q.lower()
    pid=path_id_by_full.get(qlow)
    bundle_ids=bundle_ids_by_path.get(pid,[]) if pid is not None else []
    # An exact queue path should have exactly one owner bundle in gameres.
    main=[]
    for bid in bundle_ids:
        b=bundles[bid]
        off=installed_by_logical.get(b['logicalName'])
        alias_off=installed_by_alias.get(b['aliasName'])
        installed=(off is not None and alias_off==off)
        main.append({
          **b,'installedExact':installed,'fragmentOffset':off,
          'fragmentBytes':size_by_offset.get(off) if off is not None else None,
          'aliasOffset':alias_off
        })
    exact_main=main[0] if len(main)==1 else None

    toks,cores=identity_tokens(e)
    dep_rows=[]
    if exact_main:
        for did in exact_main['dependencyBundleIds']:
            db=bundles.get(did)
            if not db: continue
            off=installed_by_logical.get(db['logicalName']); aoff=installed_by_alias.get(db['aliasName'])
            low=norm(db['logicalName'])
            owned=any(t in low for t in toks) or any(c in low for c in cores)
            dep_rows.append({
              'bundleId':did,'logicalName':db['logicalName'],'aliasName':db['aliasName'],
              'declaredBytes':db['declaredBytes'],'kind':classify_name(db['logicalName']),
              'installedExact':off is not None and aoff==off,'fragmentOffset':off,
              'fragmentBytes':size_by_offset.get(off) if off is not None else None,
              'sameModelFamily':owned
            })

    owned=[x for x in dep_rows if x['sameModelFamily']]
    owned_inst=[x for x in owned if x['installedExact']]
    installed_deps=[x for x in dep_rows if x['installedExact']]
    row={
      'heroId':hid,'name':e['name'],'appearance':e['appearance'],'formationKind':e['formationKind'],
      'queueModelPath':q,'queuePathId':pid,'manifestMapped':pid is not None and len(main)==1,
      'manifestBundleCount':len(main),'queueBundle':exact_main,
      'installedExact':bool(exact_main and exact_main['installedExact']),
      'directDependencyCount':len(dep_rows),'installedDirectDependencyCount':len(installed_deps),
      'sameModelDependencyCount':len(owned),'installedSameModelDependencyCount':len(owned_inst),
      'installedSameModelDependencies':owned_inst,
      'missingSameModelDependencies':[x for x in owned if not x['installedExact']],
      'current15':hid in CURRENT15
    }
    rows.append(row)

manifest_mapped=sum(x['manifestMapped'] for x in rows)
installed_exact=sum(x['installedExact'] for x in rows)
cur=[x for x in rows if x['current15']]
cur_inst=sum(x['installedExact'] for x in cur)
missing_current=[x['heroId'] for x in cur if not x['installedExact']]
missing_all=[x['heroId'] for x in rows if not x['installedExact']]

# ---------- non-invasive external-cache visibility probe ----------
# No root, no run-as, no bypass. Merely records whether Android exposes standard
# external game directories to Termux. The next phase can use them only if readable.
cache_roots=[]
for p in (
    f'/storage/emulated/0/Android/data/{pkg}/files',
    f'/sdcard/Android/data/{pkg}/files',
    f'/storage/emulated/0/Android/obb/{pkg}',
    f'/sdcard/Android/obb/{pkg}',
):
    row={
      'path':p,
      'exists':None,
      'readable':False,
      'permissionDenied':False,
      'sampleFiles':[]
    }
    # Android 11+ scoped storage can raise PermissionError even for stat()/exists().
    # Never let visibility probing abort the authoritative manifest mapping.
    try:
        st=os.stat(p)
        row['exists']=True
    except FileNotFoundError:
        row['exists']=False
    except PermissionError as e:
        row['exists']=None
        row['permissionDenied']=True
        row['probeError']=repr(e)
    except OSError as e:
        row['exists']=None
        row['probeError']=repr(e)

    if row['exists'] is True and not row['permissionDenied']:
        try:
            row['readable']=bool(os.access(p,os.R_OK))
        except Exception as e:
            row['readable']=False
            row['probeError']=repr(e)

    if row['exists'] is True and row['readable']:
        try:
            count=0
            for root,dirs,files in os.walk(p,topdown=True):
                # Bound the probe: metadata only, no large file reads.
                for fn in files:
                    low=fn.lower()
                    if any(x in low for x in ('bundle','gameres','fragment','asset')) or low.endswith(('.bytes','.dat','.data')):
                        full=os.path.join(root,fn)
                        try: sz=os.path.getsize(full)
                        except PermissionError:
                            sz=None
                        except OSError:
                            sz=None
                        row['sampleFiles'].append({'path':full,'bytes':sz});count+=1
                        if count>=80:break
                if count>=80:break
        except PermissionError as e:
            row['permissionDenied']=True
            row['readable']=False
            row['probeError']=repr(e)
        except Exception as e:
            row['probeError']=repr(e)
    cache_roots.append(row)

out={
 'format':'WFGG_LASTWAR_AUTHORITATIVE_BUNDLE_MAP_31_V1','networkUsed':False,
 'basis':'HeroAppearance.queue_model_path -> gameres Paths/Bundles -> exact installed BundleOffset/AliasOffset tables',
 'source':src,
 'gameresStats':{'directories':len(directories),'paths':len(paths),'bundles':len(bundles)},
 'installedIndexStats':{'fragment':'BundleFragment0.bytes','records':bo[0]['count'],'fragmentBytes':fragment_bytes,'offsetTablesAligned':offset_tables_aligned},
 'heroCount':31,'manifestMappedCount':manifest_mapped,'installedExactCount':installed_exact,
 'current15Count':len(cur),'current15InstalledExactCount':cur_inst,
 'missingCurrent15HeroIds':missing_current,'missingAllHeroIds':missing_all,
 'externalCacheProbe':cache_roots,'rows':rows
}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 45 AUTHORITATIVE BUNDLE MAP 31',
 'OFFLINE ONLY · no heuristic bundle selection',
 f"gameres directories={len(directories)} paths={len(paths)} bundles={len(bundles)}",
 f"installed fragment=BundleFragment0.bytes records={bo[0]['count']} bytes={fragment_bytes} offsetTablesAligned={offset_tables_aligned}",
 f"manifestMapped={manifest_mapped}/31 installedExact={installed_exact}/31 current15InstalledExact={cur_inst}/15",
 'missingCurrent15HeroIds='+','.join(map(str,missing_current)),
 'missingAllHeroIds='+','.join(map(str,missing_all)),
 ''
]
for x in rows:
    qb=x['queueBundle'] or {}
    lines.append(f"HERO {x['heroId']} {x['name']} current15={x['current15']} manifestMapped={x['manifestMapped']} installedExact={x['installedExact']}")
    lines.append('  queue_model_path='+x['queueModelPath'])
    lines.append(f"  pathId={x['queuePathId']} bundleId={qb.get('bundleId','-')} bundle={qb.get('logicalName','-')}")
    if qb:
        lines.append(f"  declaredBytes={qb.get('declaredBytes')} offset={qb.get('fragmentOffset')} physicalBytes={qb.get('fragmentBytes')} aliasAligned={qb.get('aliasOffset')==qb.get('fragmentOffset') if qb.get('fragmentOffset') is not None else False}")
        lines.append(f"  deps={x['directDependencyCount']} installedDeps={x['installedDirectDependencyCount']} sameModelDeps={x['sameModelDependencyCount']} installedSameModelDeps={x['installedSameModelDependencyCount']}")
        for d in x['installedSameModelDependencies']:
            lines.append(f"    INSTALLED_DEP kind={d['kind']} id={d['bundleId']} offset={d['fragmentOffset']} bytes={d['fragmentBytes']} name={d['logicalName']}")
        for d in x['missingSameModelDependencies'][:12]:
            lines.append(f"    MISSING_DEP kind={d['kind']} id={d['bundleId']} declaredBytes={d['declaredBytes']} name={d['logicalName']}")
    lines.append('')
lines.append('EXTERNAL_CACHE_PROBE')
for c in cache_roots:
    lines.append(f"  path={c['path']} exists={c['exists']} readable={c['readable']} samples={len(c.get('sampleFiles',[]))}")
    for f in c.get('sampleFiles',[])[:20]: lines.append(f"    FILE bytes={f['bytes']} path={f['path']}")
lines += [
 '', 'GUARDRAILS',
 '  exact_queue_bundle_is_never_replaced_by_similarity=true',
 '  manifest_only_is_not_reported_as_installed=true',
 '  bundle_and_alias_offsets_must_match=true',
 '  no_root_no_run_as_no_network=true',
]
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('PHASE45_OK',f'manifestMapped={manifest_mapped}/31',f'installedExact={installed_exact}/31',f'current15InstalledExact={cur_inst}/15',f'installedIndex={bo[0]["count"]}/{len(bundles)}')
print('PHASE45_MISSING_CURRENT15',','.join(map(str,missing_current)) or '-')
for c in cache_roots:
    print('CACHE',f"exists={c['exists']}",f"readable={c['readable']}",c['path'])
PYEOF

python "$PY" "$MAP" "$P40" "$OUT" "$REPORT" "$PKG" "${APK_PATHS[@]}"
rm -f "$PY"

git add -f frontend/lab/master-assets-v2/meta/formation-authoritative-bundle-map-31.json scripts/lastwar-phase45-authoritative-bundle-map-31.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/formation-authoritative-bundle-map-31.json scripts/lastwar-phase45-authoritative-bundle-map-31.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: map authoritative formation bundles to installed offsets"
fi
git push origin "$BRANCH"

echo "=== PHASE 45 TERMINEE ==="
echo "Rapport: $REPORT"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
