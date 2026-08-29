#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 46B
# FAST LOCAL ADB CACHE SCAN
# CODE ONLY · no root · no run-as · no Last War network.
# Avoids wc -c / full reads of giant cache fragments.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
P45="$ROOT/frontend/lab/master-assets-v2/meta/formation-authoritative-bundle-map-31.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE46B_ADB_CACHE_FAST_SCAN.txt"
FOUND="$HOME/storage/downloads/WFGG_LASTWAR_PHASE46B_CACHE_INDEXES"
PACK="$HOME/storage/downloads/WFGG_LASTWAR_PHASE46B_CACHE_INDEXES.zip"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P45" ]] || fail "Phase45 absente: $P45"
command -v adb >/dev/null 2>&1 || fail "adb absent"

SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecté — exécuter adb connect 127.0.0.1:PORT"

rm -rf "$FOUND"
mkdir -p "$FOUND"
rm -f "$PACK" "$PACK.sha256"

python - "$P45" "$REPORT" "$FOUND" "$PACK" "$PKG" "$SERIAL" <<'PY'
from pathlib import Path
import hashlib, json, os, re, shlex, subprocess, sys, zipfile

p45p=Path(sys.argv[1]); reportp=Path(sys.argv[2]); founddir=Path(sys.argv[3]); packp=Path(sys.argv[4]); pkg=sys.argv[5]; serial=sys.argv[6]
data=json.loads(p45p.read_text(encoding='utf-8'))
rows=data.get('rows') or []
current=[r for r in rows if r.get('current15')]
missing=[r for r in current if not r.get('installedExact')]

ROOTS=[
 f'/sdcard/Android/data/{pkg}/files',
 f'/storage/emulated/0/Android/data/{pkg}/files',
 f'/sdcard/Android/obb/{pkg}',
]

def run(args,timeout=30):
    try:
        cp=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
        return cp.returncode,cp.stdout,cp.stderr,None
    except subprocess.TimeoutExpired as e:
        out=e.stdout.decode(errors='ignore') if isinstance(e.stdout,bytes) else (e.stdout or '')
        err=e.stderr.decode(errors='ignore') if isinstance(e.stderr,bytes) else (e.stderr or '')
        return 124,out,err,'timeout'

def shell(cmd,timeout=30):
    return run(['adb','-s',serial,'shell',cmd],timeout)

def safe_size(path):
    # IMPORTANT: stat only. Never fallback to wc/cat; those read the whole file.
    q=shlex.quote(path)
    for cmd in (f'stat -c %s {q} 2>/dev/null', f'toybox stat -c %s {q} 2>/dev/null'):
        rc,out,err,to=shell(cmd,timeout=5)
        if not to:
            m=re.search(r'(^|\n)(\d+)\s*($|\n)',out)
            if m:return int(m.group(2))
    return None

print(f'PHASE46B_ADB serial={serial}',flush=True)
rc,out,err,to=shell('id',timeout=10)
identity=(out or err).strip()
print('ADB_ID',identity[:220],flush=True)
if rc!=0 or to:
    raise SystemExit('ADB shell indisponible')

# Exact filenames required by the nine missing current heroes.
wanted={}
for r in missing:
    qb=r.get('queueBundle') or {}
    vals=[]
    for key in ('logicalName','aliasName'):
        if qb.get(key):vals.append((qb[key],'queue'))
    for dep in r.get('missingSameModelDependencies') or []:
        if dep.get('logicalName'):vals.append((dep['logicalName'],dep.get('kind') or 'dependency'))
        if dep.get('aliasName'):vals.append((dep['aliasName'],dep.get('kind') or 'dependency'))
    for fn,kind in vals:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',fn):continue
        x=wanted.setdefault(fn,[])
        owner={'heroId':r['heroId'],'name':r['name'],'kind':kind}
        if owner not in x:x.append(owner)

root_rows=[]; readable=[]; special=[]; exact=[]
for root in ROOTS:
    qroot=shlex.quote(root)
    rc,out,err,to=shell(f'test -d {qroot} && test -r {qroot} && echo READABLE || echo NO',timeout=10)
    ok=('READABLE' in out and not to)
    root_rows.append({'path':root,'readable':ok,'probe':(out+err).strip()[:300]})
    print(f'CACHE_ROOT readable={ok} {root}',flush=True)
    if not ok:continue
    readable.append(root)

    # One bounded metadata scan. No size reads here.
    cmd=(f'find {qroot} -type f 2>/dev/null | '
         "grep -Ei 'BundleFragment|BundleOffsetTable|AliasOffsetTable|(^|/)gameres($|\\.)|\\.bundle$' | head -n 5000")
    rc,paths,err,to=shell(cmd,timeout=45)
    if to:
        print(f'CACHE_LIST_TIMEOUT {root}',flush=True)
    for p in [x.strip() for x in paths.splitlines() if x.strip()]:
        base=os.path.basename(p)
        low=base.lower()
        typ=None
        if 'bundlefragment' in low:typ='fragment'
        elif 'bundleoffsettable' in low:typ='bundleOffsetTable'
        elif 'aliasoffsettable' in low:typ='aliasOffsetTable'
        elif low=='gameres' or low.startswith('gameres.'):typ='gameres'
        elif base in wanted:typ='exactBundle'
        if not typ:continue
        row={'type':typ,'path':p,'filename':base,'bytes':safe_size(p)}
        if typ=='exactBundle':
            row['owners']=wanted[base]; exact.append(row)
        else:special.append(row)

    # Exact-manifest-name search in one command, only if the broad listing did not expose them.
    found_names={x['filename'] for x in exact}
    left=[fn for fn in wanted if fn not in found_names]
    if left:
        # Build safe basename case statement; avoids N separate full-tree finds.
        alts='|'.join(re.escape(x) for x in left)
        cmd=(f'find {qroot} -type f 2>/dev/null | '
             f"grep -E '/({alts})$' | head -n 500")
        rc,paths,err,to=shell(cmd,timeout=60)
        if to:print(f'EXACT_LIST_TIMEOUT {root}',flush=True)
        for p in [x.strip() for x in paths.splitlines() if x.strip()]:
            base=os.path.basename(p)
            if base not in wanted:continue
            row={'type':'exactBundle','path':p,'filename':base,'bytes':safe_size(p),'owners':wanted[base]}
            if not any(x['path']==p for x in exact):exact.append(row)

# Dedupe special rows by path.
def dedupe(rows):
    out=[];seen=set()
    for x in rows:
        if x['path'] in seen:continue
        seen.add(x['path']);out.append(x)
    return out
special=dedupe(special);exact=dedupe(exact)

# Pull only small index files. Never pull fragments here.
pulled=[]
for x in special:
    if x['type']=='fragment':continue
    size=x.get('bytes')
    if size is not None and size>40*1024*1024:continue
    local=founddir/('cache__'+re.sub(r'[^A-Za-z0-9_.-]+','_',x['filename']))
    if local.exists():
        stem=local.stem;suf=local.suffix;i=2
        while local.exists():local=founddir/f'{stem}_{i}{suf}';i+=1
    rc,out,err,to=run(['adb','-s',serial,'pull',x['path'],str(local)],timeout=120)
    if rc==0 and local.is_file():
        pulled.append({'type':x['type'],'remotePath':x['path'],'localFile':local.name,'bytes':local.stat().st_size,'sha256':hashlib.sha256(local.read_bytes()).hexdigest()})
        print(f"PULLED_INDEX type={x['type']} bytes={local.stat().st_size} {x['path']}",flush=True)

# Pull exact standalone bundles if any are directly cached as files; reasonable size guard.
for x in exact:
    size=x.get('bytes')
    if size is not None and size>25*1024*1024:continue
    local=founddir/('exact__'+x['filename'])
    rc,out,err,to=run(['adb','-s',serial,'pull',x['path'],str(local)],timeout=120)
    if rc==0 and local.is_file():
        pulled.append({'type':'exactBundle','remotePath':x['path'],'localFile':local.name,'bytes':local.stat().st_size,'sha256':hashlib.sha256(local.read_bytes()).hexdigest(),'owners':x['owners']})
        print(f"PULLED_EXACT bytes={local.stat().st_size} {x['filename']}",flush=True)

files=sorted(p for p in founddir.iterdir() if p.is_file())
packsha=None
if files:
    with zipfile.ZipFile(packp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,p.name)
    packsha=hashlib.sha256(packp.read_bytes()).hexdigest()
    Path(str(packp)+'.sha256').write_text(packsha+'  '+packp.name+'\n',encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 46B FAST ADB CACHE SCAN',
 'NO ROOT · NO RUN-AS · NO LAST WAR NETWORK · NO FULL-FILE SIZE FALLBACK',
 f'adbSerial={serial}',f'adbIdentity={identity}',
 f'current15Missing={len(missing)} heroIds='+','.join(str(x['heroId']) for x in missing),
 f'exactWantedNames={len(wanted)} readableRoots={len(readable)}/{len(ROOTS)}',
 f'specialFiles={len(special)} exactStandaloneFiles={len(exact)} pulledFiles={len(pulled)}',
 f'packSha256={packsha or "-"}',''
]
for r in root_rows:lines.append(f"CACHE_ROOT readable={r['readable']} path={r['path']} probe={r['probe']}")
lines+=['','SPECIAL_FILES']
for x in special:lines.append(f"  type={x['type']} bytes={x.get('bytes')} path={x['path']}")
if not special:lines.append('  none')
lines+=['','EXACT_STANDALONE_FILES']
for x in exact:
    owners=','.join(f"{o['heroId']}:{o['kind']}" for o in x['owners'])
    lines.append(f"  bytes={x.get('bytes')} owners={owners} path={x['path']}")
if not exact:lines.append('  none')
lines+=['','PULLED_FILES']
for x in pulled:lines.append(f"  type={x['type']} bytes={x['bytes']} sha256={x['sha256']} remote={x['remotePath']} local={x['localFile']}")
if not pulled:lines.append('  none')
lines+=['','GUARDRAILS','  adb_shell_only=true','  root_used=false','  run_as_used=false','  wc_or_cat_for_size=false','  fragments_not_pulled=true','  exact_manifest_filename_only=true','  no_similarity_fallback=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

frags=sum(x['type']=='fragment' for x in special)
indexes=sum(x['type'] in ('bundleOffsetTable','aliasOffsetTable','gameres') for x in special)
print('PHASE46B_OK',f'readableRoots={len(readable)}/{len(ROOTS)}',f'exactStandalone={len(exact)}',f'fragments={frags}',f'indexes={indexes}',f'pulled={len(pulled)}',flush=True)
if packsha:print('PHASE46B_PACK',packp,packsha,flush=True)
PY

git add scripts/lastwar-phase46b-adb-cache-fast-scan.sh
if ! git diff --cached --quiet -- scripts/lastwar-phase46b-adb-cache-fast-scan.sh; then
  git commit -m "lab: add fast adb cache scan without full fragment reads"
fi
git push origin "$BRANCH"

echo "=== PHASE 46B TERMINEE ==="
echo "Rapport: $REPORT"
[[ -s "$PACK" ]] && echo "Pack: $PACK"
echo "main non modifiée."
