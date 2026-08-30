#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — locate the real IL2CPP / metadata payload.
# Read-only scan of installed APK splits. No game network. No preview mutation.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-il2cpp-payload-locator-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_IL2CPP_PAYLOAD_LOCATOR.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-il2cpp-payload-locator.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"

python - "$OUT" "$REPORT" "${APKS[@]}" <<'PY'
from pathlib import Path
import json,sys,zipfile,re

out=Path(sys.argv[1]); report=Path(sys.argv[2]); apks=[Path(x) for x in sys.argv[3:]]
MAGIC=b'\xaf\x1b\xb1\xfa'
TOKENS=[
 b'il2cpp_init', b'il2cpp_domain_get', b'il2cpp_codegen_register', b'MetadataCache',
 b'global-metadata.dat', b'Assembly-CSharp', b'UIHeroPVPFormationPanel', b'FormationRT',
 b'HeroShowBlend'
]
name_rx=re.compile(r'(global.?metadata|metadata|assembly.?csharp|il2cpp|managed|scriptassembl)',re.I)
results=[]; magic_hits=[]; named=[]; libs=[]; suspicious=[]

for apk in apks:
    try:
        z=zipfile.ZipFile(apk)
    except Exception as e:
        results.append({'apk':str(apk),'error':repr(e)}); continue
    entry_count=0
    for info in z.infolist():
        if info.is_dir(): continue
        entry_count+=1
        n=info.filename; low=n.lower(); size=info.file_size
        if name_rx.search(n):
            named.append({'apk':str(apk),'entry':n,'bytes':size})
        # Metadata magic can be hidden under an arbitrary filename. Read only the header first.
        try:
            with z.open(info) as f: head=f.read(64)
        except Exception:
            head=b''
        if head.startswith(MAGIC):
            magic_hits.append({'apk':str(apk),'entry':n,'bytes':size,'magic':'AF1BB1FA'})
        is_so=low.endswith('.so')
        candidate_asset=(size>=256*1024 and size<=96*1024*1024 and (low.endswith(('.dat','.bin','.bytes')) or '/assets/bin/data/' in '/'+low or '/assets/' in '/'+low))
        if not (is_so or candidate_asset):
            continue
        # Sequential read: inspect one candidate at a time to keep RAM bounded.
        try:
            data=z.read(info)
        except Exception as e:
            continue
        hits=[t.decode('ascii') for t in TOKENS if t in data]
        row={'apk':str(apk),'entry':n,'bytes':size,'tokenHits':hits,'metadataMagic':data[:4]==MAGIC}
        if is_so:
            score=len(hits)*100 + min(80,int(size/1024/1024*4))
            if 'libil2cpp' in low: score+=60
            if any(k in low for k in ('unity','game','main','logic','core')): score+=15
            row['score']=score; libs.append(row)
        elif hits or row['metadataMagic'] or name_rx.search(n):
            suspicious.append(row)
    results.append({'apk':str(apk),'entryCount':entry_count})

libs.sort(key=lambda r:(-r['score'],-r['bytes'],r['entry']))
suspicious.sort(key=lambda r:(not r['metadataMagic'],-len(r['tokenHits']),-r['bytes']))
summary={
 'format':'WFGG_LASTWAR_IL2CPP_PAYLOAD_LOCATOR_V1',
 'networkUsed':False,'generatedArtwork':False,
 'apks':results,'namedEntries':named,'metadataMagicHits':magic_hits,
 'nativeLibraries':libs,'suspiciousAssets':suspicious,
 'guardrails':{'apkReadOnly':True,'previewUntouched':True,'mainUntouched':True}
}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — IL2CPP PAYLOAD LOCATOR','',f'apks={len(apks)} named={len(named)} magicHits={len(magic_hits)} libs={len(libs)} suspiciousAssets={len(suspicious)}','','METADATA MAGIC HITS']
for r in magic_hits[:50]: lines.append(f"  {r['bytes']:>10}  {r['entry']}")
lines+=['','NAMED METADATA / IL2CPP ENTRIES']
for r in named[:100]: lines.append(f"  {r['bytes']:>10}  {r['entry']}")
lines+=['','NATIVE LIBRARIES (ranked)']
for r in libs[:80]: lines.append(f"  score={r['score']:>3} bytes={r['bytes']:>10} hits={','.join(r['tokenHits']) or '-'}  {r['entry']}")
lines+=['','SUSPICIOUS ASSETS']
for r in suspicious[:80]: lines.append(f"  bytes={r['bytes']:>10} magic={r['metadataMagic']} hits={','.join(r['tokenHits']) or '-'}  {r['entry']}")
report.write_text('\n'.join(lines)+'\n','utf-8')
print('IL2CPP_PAYLOAD_LOCATOR_OK',f'apks={len(apks)}',f'named={len(named)}',f'magicHits={len(magic_hits)}',f'libs={len(libs)}',f'suspicious={len(suspicious)}')
for r in magic_hits[:10]: print('METADATA_MAGIC',r['bytes'],r['entry'])
for r in libs[:12]: print('IL2CPP_LIB',f"score={r['score']}",f"bytes={r['bytes']}",f"hits={','.join(r['tokenHits']) or '-'}",r['entry'])
for r in suspicious[:12]: print('IL2CPP_ASSET',f"bytes={r['bytes']}",f"magic={r['metadataMagic']}",f"hits={','.join(r['tokenHits']) or '-'}",r['entry'])
print('IL2CPP_PAYLOAD_JSON',out)
print('IL2CPP_PAYLOAD_REPORT',report)
PY

git add scripts/lastwar-il2cpp-payload-locator.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: locate protected IL2CPP payload"
  git push origin "$BRANCH"
fi

echo "=== IL2CPP PAYLOAD LOCATOR TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
