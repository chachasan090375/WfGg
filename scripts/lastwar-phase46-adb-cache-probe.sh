#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 46
# LOCAL ADB EXTERNAL CACHE PROBE
# CODE ONLY · no root · no run-as · no Last War network connection.
#
# Purpose:
# Android scoped storage blocks Termux from /Android/data. A locally paired ADB
# shell is allowed by Android's Wireless debugging feature and can inspect the
# app's external files as the shell user. This phase never touches private
# /data/user/0 content and never substitutes missing bundles by similarity.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
P45="$ROOT/frontend/lab/master-assets-v2/meta/formation-authoritative-bundle-map-31.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE46_ADB_CACHE_PROBE.txt"
FOUND_DIR="$HOME/storage/downloads/WFGG_LASTWAR_PHASE46_ADB_CACHE_FOUND"
PACK="$HOME/storage/downloads/WFGG_LASTWAR_PHASE46_ADB_CACHE_FOUND.zip"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P45" ]] || fail "Phase45 absente: $P45"

if ! command -v adb >/dev/null 2>&1; then
  echo "ADB absent: installation android-tools..."
  pkg install -y android-tools >/dev/null
fi
command -v adb >/dev/null 2>&1 || fail "adb indisponible"

adb start-server >/dev/null 2>&1 || true

connected_serial(){
  adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}'
}

SERIAL="$(connected_serial || true)"
if [[ -z "$SERIAL" ]]; then
  # If the phone is already paired, Android advertises a TLS connect endpoint.
  MDNS="$(adb mdns services 2>/dev/null || true)"
  CONNECT_EP="$(printf '%s\n' "$MDNS" | awk '/_adb-tls-connect\._tcp/ {print $NF; exit}')"
  if [[ -n "$CONNECT_EP" ]]; then
    adb connect "$CONNECT_EP" >/dev/null 2>&1 || true
    sleep 1
    SERIAL="$(connected_serial || true)"
  fi
fi

if [[ -z "$SERIAL" ]]; then
  {
    echo "WfGg Last War LAB — PHASE 46 ADB CACHE PROBE"
    echo "PHASE46_PAIR_REQUIRED"
    echo
    echo "Aucun appareil ADB local connecté."
    echo "Sur le téléphone: Paramètres > Options développeur > Débogage sans fil."
    echo "Choisir 'Associer l'appareil avec un code d'association'."
    echo "Puis dans Termux: adb pair IP:PORT  (saisir le code affiché)"
    echo "Ensuite: adb mdns services"
    echo "Puis: adb connect IP:PORT_de_connexion"
    echo
    echo "MDNS actuel:"
    adb mdns services 2>/dev/null || true
    echo
    echo "Relancer ensuite: bash scripts/lastwar-phase46-adb-cache-probe.sh"
  } | tee "$REPORT"
  exit 2
fi

mkdir -p "$FOUND_DIR"
rm -f "$PACK" "$PACK.sha256"

python - "$P45" "$REPORT" "$FOUND_DIR" "$PACK" "$PKG" "$SERIAL" <<'PY'
from pathlib import Path
import json, os, re, subprocess, sys, zipfile, hashlib, shutil

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

def adb(*args, timeout=60):
    cp=subprocess.run(['adb','-s',serial,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    return cp.returncode,cp.stdout,cp.stderr

def shell(cmd, timeout=60):
    return adb('shell',cmd,timeout=timeout)

# Verify we are talking to the Android shell user, never root/run-as.
rc,uidout,uiderr=shell('id')
identity=(uidout or uiderr).strip()

root_rows=[]
readable=[]
for root in ROOTS:
    # ADB shell test avoids Termux scoped-storage restrictions.
    rc,out,err=shell(f'test -d "{root}" && test -r "{root}" && echo READABLE || echo NO')
    ok='READABLE' in out
    row={'path':root,'readable':ok,'probe':(out+err).strip()[:500]}
    if ok:
        readable.append(root)
        # Find likely index/cache/fragment files and record sizes.
        cmd=(f'find "{root}" -type f 2>/dev/null | '
             "grep -Ei 'BundleFragment|BundleOffsetTable|AliasOffsetTable|(^|/)gameres($|\\.)|assetbundle|\\.bundle$|\\.bytes$|\\.data$|\\.dat$' | head -n 1200")
        rc,paths,err=shell(cmd,timeout=120)
        cand=[]
        for p in paths.splitlines():
            p=p.strip()
            if not p: continue
            rc2,sz,er2=shell(f'stat -c %s "{p}" 2>/dev/null || wc -c < "{p}"',timeout=20)
            try:n=int(sz.strip().splitlines()[-1])
            except Exception:n=None
            cand.append({'path':p,'bytes':n})
        row['candidateFiles']=cand
    root_rows.append(row)

# Exact filenames demanded by Phase45 for the 9 missing current heroes.
wanted=[]
for r in missing:
    qb=r.get('queueBundle') or {}
    for key in ('logicalName','aliasName'):
        n=qb.get(key)
        if n:wanted.append({'heroId':r['heroId'],'name':r['name'],'kind':'queue','filename':n})
    for dep in (r.get('missingSameModelDependencies') or []):
        n=dep.get('logicalName')
        if n:wanted.append({'heroId':r['heroId'],'name':r['name'],'kind':dep.get('kind') or 'dependency','filename':n})
        a=dep.get('aliasName')
        if a:wanted.append({'heroId':r['heroId'],'name':r['name'],'kind':dep.get('kind') or 'dependency','filename':a})

# dedupe by filename while retaining hero ownership list
byfile={}
for w in wanted:
    row=byfile.setdefault(w['filename'],{'filename':w['filename'],'owners':[]})
    tup={'heroId':w['heroId'],'name':w['name'],'kind':w['kind']}
    if tup not in row['owners']:row['owners'].append(tup)

found=[]
for fname,row in byfile.items():
    # Manifest bundle names are alnum/_/./- only; still reject unsafe names.
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',fname): continue
    for root in readable:
        rc,out,err=shell(f'find "{root}" -type f -name "{fname}" 2>/dev/null | head -n 5',timeout=60)
        for remote in [x.strip() for x in out.splitlines() if x.strip()]:
            local=founddir/fname
            if local.exists():
                base=local.stem; suf=local.suffix; i=2
                while local.exists():
                    local=founddir/f'{base}_{i}{suf}';i+=1
            cp=subprocess.run(['adb','-s',serial,'pull',remote,str(local)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
            if cp.returncode==0 and local.is_file():
                found.append({'filename':fname,'remotePath':remote,'localFile':local.name,'bytes':local.stat().st_size,'sha256':hashlib.sha256(local.read_bytes()).hexdigest(),'owners':row['owners']})

# Pull small authoritative index files from cache if present. Do NOT auto-pull giant fragments.
index_pulls=[]; fragment_rows=[]
for rr in root_rows:
    for x in rr.get('candidateFiles',[]):
        p=x['path']; b=x.get('bytes'); low=os.path.basename(p).lower()
        if 'bundlefragment' in low:
            fragment_rows.append(x);continue
        if any(k in low for k in ('bundleoffsettable','aliasoffsettable')) or low=='gameres' or low.startswith('gameres.'):
            if b is not None and b>35*1024*1024: continue
            dest=founddir/('cacheindex__'+re.sub(r'[^A-Za-z0-9_.-]+','_',os.path.basename(p)))
            cp=subprocess.run(['adb','-s',serial,'pull',p,str(dest)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
            if cp.returncode==0 and dest.is_file():
                index_pulls.append({'remotePath':p,'localFile':dest.name,'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})

# Build compact package only from files actually pulled.
files=sorted([p for p in founddir.iterdir() if p.is_file()]) if founddir.is_dir() else []
if files:
    with zipfile.ZipFile(packp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,p.name)
    pack_sha=hashlib.sha256(packp.read_bytes()).hexdigest()
    Path(str(packp)+'.sha256').write_text(pack_sha+'  '+packp.name+'\n',encoding='utf-8')
else:
    pack_sha=None

lines=[
 'WfGg Last War LAB — PHASE 46 LOCAL ADB CACHE PROBE',
 'NO ROOT · NO RUN-AS · NO LAST WAR NETWORK',
 f'adbSerial={serial}',
 f'adbIdentity={identity}',
 f'current15Missing={len(missing)} heroIds='+','.join(str(r['heroId']) for r in missing),
 f'exactWantedFilenames={len(byfile)} exactFilesFound={len(found)}',
 f'indexFilesPulled={len(index_pulls)} fragmentFilesSeen={len(fragment_rows)}',
 f'packFiles={len(files)} packSha256={pack_sha or "-"}',
 ''
]
for rr in root_rows:
    lines.append(f"CACHE_ROOT path={rr['path']} readable={rr['readable']}")
    for x in rr.get('candidateFiles',[])[:200]:lines.append(f"  CAND bytes={x.get('bytes')} path={x['path']}")
lines.append('')
lines.append('FRAGMENTS')
for x in fragment_rows:lines.append(f"  bytes={x.get('bytes')} path={x['path']}")
if not fragment_rows:lines.append('  none')
lines.append('')
lines.append('PULLED_INDEXES')
for x in index_pulls:lines.append(f"  bytes={x['bytes']} sha256={x['sha256']} remote={x['remotePath']} local={x['localFile']}")
if not index_pulls:lines.append('  none')
lines.append('')
lines.append('FOUND_EXACT_BUNDLES')
for x in found:
    owners=','.join(f"{o['heroId']}:{o['kind']}" for o in x['owners'])
    lines.append(f"  bytes={x['bytes']} sha256={x['sha256']} owners={owners} remote={x['remotePath']} local={x['localFile']}")
if not found:lines.append('  none')
lines.append('')
lines.append('GUARDRAILS')
lines.append('  adb_shell_only=true')
lines.append('  root_used=false')
lines.append('  run_as_used=false')
lines.append('  private_data_user_0_scanned=false')
lines.append('  exact_manifest_filename_only=true')
lines.append('  no_similarity_fallback=true')
lines.append('  no_lastwar_network=true')
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('PHASE46_OK',f'adb={serial}',f'readableRoots={len(readable)}/{len(ROOTS)}',f'exactFound={len(found)}/{len(byfile)}',f'fragments={len(fragment_rows)}',f'indexes={len(index_pulls)}')
if pack_sha:print('PHASE46_PACK',str(packp),pack_sha)
PY

git add scripts/lastwar-phase46-adb-cache-probe.sh
if git diff --cached --quiet -- scripts/lastwar-phase46-adb-cache-probe.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: add local adb cache probe"
fi
git push origin "$BRANCH"

echo "=== PHASE 46 TERMINEE ==="
echo "Rapport: $REPORT"
[[ -s "$PACK" ]] && echo "Pack: $PACK"
echo "main non modifiée."
