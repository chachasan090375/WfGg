#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 44
# EXPORT AUTHORITATIVE INSTALLED BUNDLE INDEXES
# CODE ONLY · OFFLINE ONLY · no Last War network connection.
#
# Phase43 proved geometry heuristics can still select a wrong hero bundle.
# This phase exports the game's own bundle-name/index files so the exact bundle
# filenames resolved in Phase40 can be mapped to their real UnityFS offsets.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
DOWNLOADS="$HOME/storage/downloads"
OUTDIR="${TMPDIR:-$HOME/.cache}/wfgg-phase44-bundle-index"
PACK="$DOWNLOADS/WFGG_LASTWAR_PHASE44_AUTHORITATIVE_BUNDLE_INDEX.zip"
MANIFEST="$OUTDIR/manifest.json"
REPORT="$DOWNLOADS/WFGG_LASTWAR_PHASE44_AUTHORITATIVE_BUNDLE_INDEX.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "installation Last War introuvable ($PKG)"

rm -rf "$OUTDIR"
mkdir -p "$OUTDIR" "$DOWNLOADS"
rm -f "$PACK" "$PACK.sha256" "$REPORT"

python - "$OUTDIR" "$PACK" "$REPORT" "${APK_PATHS[@]}" <<'PY'
from pathlib import Path
import hashlib, json, os, sys, zipfile

outdir=Path(sys.argv[1]); pack=Path(sys.argv[2]); report=Path(sys.argv[3]); apks=sys.argv[4:]

wanted_exact={
    'assets/AssetBundles/BundleOffsetTable.bytes',
    'assets/AssetBundles/AliasOffsetTable.bytes',
    'assets/AssetBundles/gameres',
}
# Also preserve small neighboring index/manifest files in the same directory.
# They may document the binary format/version used by the three primary files.
neighbor_tokens=('offset','alias','manifest','catalog','index','gameres')
MAX_NEIGHBOR=16*1024*1024
MAX_PRIMARY=128*1024*1024

rows=[]
seen=set()
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for zi in z.infolist():
                name=zi.filename
                if not name.startswith('assets/AssetBundles/'):
                    continue
                base=name.rsplit('/',1)[-1].lower()
                primary=name in wanted_exact
                neighbor=(not primary and any(t in base for t in neighbor_tokens) and zi.file_size<=MAX_NEIGHBOR)
                if not (primary or neighbor):
                    continue
                if primary and zi.file_size>MAX_PRIMARY:
                    raise SystemExit(f'primary index unexpectedly large: {name} bytes={zi.file_size}')
                key=(os.path.basename(apk),name)
                if key in seen:
                    continue
                seen.add(key)
                raw=z.read(zi)
                safe_apk=os.path.basename(apk).replace('.apk','')
                safe_name=name.replace('/','__')
                dst=outdir/f'{safe_apk}__{safe_name}'
                dst.write_bytes(raw)
                rows.append({
                    'apk':os.path.basename(apk),
                    'entry':name,
                    'primary':primary,
                    'bytes':len(raw),
                    'sha256':hashlib.sha256(raw).hexdigest(),
                    'file':dst.name,
                    'first32Hex':raw[:32].hex(),
                    'containsBundleLiteral':b'.bundle' in raw,
                    'containsUnityFSLiteral':b'UnityFS' in raw,
                })
    except zipfile.BadZipFile:
        continue

primary_rows=[r for r in rows if r['primary']]
found_names={r['entry'] for r in primary_rows}
missing=sorted(wanted_exact-found_names)
if missing:
    raise SystemExit('missing primary bundle indexes: '+','.join(missing))

manifest={
    'format':'WFGG_LASTWAR_AUTHORITATIVE_BUNDLE_INDEX_RAW_V1',
    'networkUsed':False,
    'package':'com.fun.lastwar.gp',
    'files':rows,
    'primaryCount':len(primary_rows),
    'missingPrimary':missing,
}
(outdir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

with zipfile.ZipFile(pack,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    z.write(outdir/'manifest.json',arcname='manifest.json')
    for r in rows:
        z.write(outdir/r['file'],arcname='raw/'+r['file'])

pack_sha=hashlib.sha256(pack.read_bytes()).hexdigest()
Path(str(pack)+'.sha256').write_text(f'{pack_sha}  {pack}\n',encoding='utf-8')

lines=[
    'WfGg Last War LAB — PHASE 44 AUTHORITATIVE BUNDLE INDEX EXPORT',
    'OFFLINE ONLY · raw installed bundle indexes · no generated graphics',
    f'files={len(rows)} primary={len(primary_rows)} packBytes={pack.stat().st_size}',
    f'packSha256={pack_sha}',
    '',
]
for r in rows:
    lines.append(f"FILE apk={r['apk']} primary={r['primary']} bytes={r['bytes']} bundleLiteral={r['containsBundleLiteral']} unityfsLiteral={r['containsUnityFSLiteral']}")
    lines.append('  entry='+r['entry'])
    lines.append('  sha256='+r['sha256'])
    lines.append('  exported='+r['file'])
    lines.append('')
report.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE44_OK',f'files={len(rows)}',f'primary={len(primary_rows)}',f'packBytes={pack.stat().st_size}')
print('PHASE44_SHA256',pack_sha)
PY

git add scripts/lastwar-phase44-export-authoritative-bundle-index.sh
if git diff --cached --quiet -- scripts/lastwar-phase44-export-authoritative-bundle-index.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: export authoritative installed bundle indexes"
fi
git push origin "$BRANCH"

echo "=== PHASE 44 TERMINEE ==="
echo "Index brut: $PACK"
echo "SHA256: $PACK.sha256"
echo "Rapport: $REPORT"
echo "Ne lance pas la page Escouades."
echo "main non modifiée."
