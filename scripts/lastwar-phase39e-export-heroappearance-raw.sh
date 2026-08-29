#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

PKG="com.fun.lastwar.gp"
OUTDIR="$HOME/storage/downloads/WFGG_LASTWAR_PHASE39E_HEROAPPEARANCE_RAW"
ZIPOUT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE39E_HEROAPPEARANCE_RAW.zip"

rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"
rm -f "$ZIPOUT"

mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || { echo "ERREUR: Last War introuvable"; exit 1; }

python - "$OUTDIR" "${APKS[@]}" <<'PY'
import io, os, sys, zipfile, hashlib
outdir=sys.argv[1]
apks=sys.argv[2:]
wanted={"lw_hero_appearance","lw_hero_appearance_b","lw_hero_appearance_opt"}
container=None; source=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for zi in z.infolist():
                if not (zi.filename.startswith('assets/table/') and zi.filename.endswith('.data')):
                    continue
                try: data=z.read(zi)
                except Exception: continue
                if not data.startswith(b'PK\x03\x04'): continue
                try:
                    inner=zipfile.ZipFile(io.BytesIO(data))
                    lowers={n.strip('/').lower() for n in inner.namelist()}
                    inner.close()
                except Exception:
                    continue
                if 'lw_hero_appearance' in lowers:
                    container=data
                    source=f"{os.path.basename(apk)}:{zi.filename}"
                    break
            if container is not None: break
    except Exception:
        pass
if container is None:
    raise SystemExit('ERREUR: conteneur HeroAppearance introuvable')
inner=zipfile.ZipFile(io.BytesIO(container))
lookup={n.strip('/').lower():n for n in inner.namelist()}
rows=[]
for key in sorted(wanted):
    real=lookup.get(key)
    if not real: continue
    raw=inner.read(real)
    path=os.path.join(outdir,key+'.bin')
    with open(path,'wb') as f: f.write(raw)
    rows.append((key,len(raw),hashlib.sha256(raw).hexdigest(),raw[:32].hex()))
inner.close()
with open(os.path.join(outdir,'INDEX.txt'),'w',encoding='utf-8') as f:
    f.write('WfGg Last War PHASE 39E — RAW HeroAppearance export\n')
    f.write('OFFLINE ONLY · static game table data\n')
    f.write('source='+source+'\n')
    for name,size,sha,first in rows:
        f.write(f'{name} bytes={size} sha256={sha} first32={first}\n')
print(f'PHASE39E_EXPORT_OK members={len(rows)} source={source}')
for name,size,sha,first in rows:
    print(f'  {name} bytes={size} sha256={sha}')
PY

python - "$OUTDIR" "$ZIPOUT" <<'PY'
import os,sys,zipfile
src,out=sys.argv[1:]
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for fn in sorted(os.listdir(src)):
        p=os.path.join(src,fn)
        if os.path.isfile(p): z.write(p,fn)
print('ZIP_OK',out,os.path.getsize(out))
PY

sha256sum "$ZIPOUT" | tee "$ZIPOUT.sha256"

echo "=== PHASE 39E TERMINEE ==="
echo "Envoie-moi ce fichier :"
echo "$ZIPOUT"
