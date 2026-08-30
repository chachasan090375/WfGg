#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — targeted audit of assets/Assemblies/Assembly-CSharp.mdl
# Read-only APK analysis. No game network. No preview mutation. main untouched.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/assembly-csharp-mdl-audit-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_ASSEMBLY_CSHARP_MDL_AUDIT.txt"
TMP="${TMPDIR:-$HOME/.cache}/wfgg-assembly-csharp-mdl-audit"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$TMP" "$(dirname "$OUT")" "$(dirname "$REPORT")"
rm -rf "$TMP"/*

mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"

python - "$TMP" "$OUT" "$REPORT" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
import sys,zipfile,json,hashlib,math,re,collections,struct

tmp=Path(sys.argv[1]); out=Path(sys.argv[2]); report=Path(sys.argv[3]); apks=[Path(x) for x in sys.argv[4:]]
entries=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for n in z.namelist():
                if n.lower().endswith('assets/assemblies/assembly-csharp.mdl'):
                    data=z.read(n); p=tmp/'Assembly-CSharp.mdl'; p.write_bytes(data)
                    entries.append({'apk':str(apk),'entry':n,'bytes':len(data),'path':str(p)})
    except Exception as e:
        entries.append({'apk':str(apk),'error':repr(e)})

files=[e for e in entries if e.get('path')]
if not files:
    report.write_text('Assembly-CSharp.mdl introuvable\n','utf-8')
    out.write_text(json.dumps({'format':'WFGG_LASTWAR_ASSEMBLY_CSHARP_MDL_AUDIT_V1','found':False,'entries':entries},indent=2)+'\n','utf-8')
    print('ASSEMBLY_CSHARP_MDL_NOT_FOUND'); raise SystemExit(0)

p=Path(files[0]['path']); data=p.read_bytes()
def entropy(buf:bytes):
    if not buf:return 0.0
    c=collections.Counter(buf); n=len(buf)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def offsets(sig:bytes,limit=50):
    out=[]; pos=0
    while len(out)<limit:
        i=data.find(sig,pos)
        if i<0:break
        out.append(i); pos=i+1
    return out

sigs={
 'MZ':b'MZ','PE':b'PE\x00\x00','BSJB':b'BSJB','ELF':b'\x7fELF','UnityFS':b'UnityFS',
 'ZIP':b'PK\x03\x04','GZIP':b'\x1f\x8b','ZSTD':b'\x28\xb5\x2f\xfd','LZ4':b'\x04\x22\x4d\x18',
 'IL2CPP_META':b'\xaf\x1b\xb1\xfa'
}
sig_hits={k:offsets(v) for k,v in sigs.items()}

terms=['UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent','HeroShowBlend','HeroShow','ArabicMirror','PVPFormation','RenderTexture','A_build_formation','WorldCityGrass','Assembly-CSharp','UnityEngine']
term_hits=[]
for term in terms:
    b=term.encode('utf-8'); u=term.encode('utf-16le')
    aa=offsets(b,100); uu=offsets(u,100)
    if aa or uu: term_hits.append({'term':term,'asciiOffsets':aa,'utf16leOffsets':uu})

# Printable strings, but only retain formation/hero/camera/render-related lines.
strings=[]
for m in re.finditer(rb'[\x20-\x7e]{4,}',data):
    s=m.group().decode('ascii','ignore')
    if re.search(r'formation|hero.?show|rendertexture|camera|arabicmirror|assembly-csharp|unityengine',s,re.I):
        strings.append({'offset':m.start(),'text':s[:500]})
        if len(strings)>=500:break

# Simple structural probes for a normal PE/.NET assembly.
pe_candidates=[]
for mz in sig_hits['MZ'][:20]:
    try:
        if mz+0x40<=len(data):
            peoff=struct.unpack_from('<I',data,mz+0x3c)[0]
            abspe=mz+peoff
            if 0<=peoff<32*1024*1024 and data[abspe:abspe+4]==b'PE\x00\x00':
                pe_candidates.append({'mzOffset':mz,'peOffset':abspe,'relativePE':peoff})
    except:pass

blocks=[]
step=1024*1024
for i in range(0,len(data),step):
    chunk=data[i:i+step]; blocks.append({'offset':i,'bytes':len(chunk),'entropy':round(entropy(chunk),5)})

summary={
 'format':'WFGG_LASTWAR_ASSEMBLY_CSHARP_MDL_AUDIT_V1','found':True,'networkUsed':False,'generatedArtwork':False,
 'source':files[0],'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
 'headerHex':data[:128].hex(),'headerAscii':''.join(chr(x) if 32<=x<127 else '.' for x in data[:128]),
 'entropy':round(entropy(data),5),'entropyBlocks1MiB':blocks,'signatureHits':sig_hits,'peCandidates':pe_candidates,
 'termHits':term_hits,'interestingStrings':strings,
 'guardrails':{'apkReadOnly':True,'binaryNotCommitted':True,'previewUntouched':True,'mainUntouched':True}
}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — ASSEMBLY-CSHARP.MDL AUDIT','',f"bytes={len(data)} sha256={summary['sha256']}",f"entropy={summary['entropy']}",f"headerHex={summary['headerHex']}",f"headerAscii={summary['headerAscii']}",'','SIGNATURES']
for k,v in sig_hits.items(): lines.append(f"  {k}: {v[:20] if v else '-'}")
lines+=['',f'PE candidates: {pe_candidates if pe_candidates else "-"}','','TARGET TERM HITS']
if term_hits:
    for h in term_hits:lines.append(f"  {h['term']} ascii={h['asciiOffsets'][:20]} utf16={h['utf16leOffsets'][:20]}")
else: lines.append('  -')
lines+=['','INTERESTING PRINTABLE STRINGS']
for s in strings[:200]:lines.append(f"  @{s['offset']} {s['text']}")
lines+=['','ENTROPY BY 1 MiB BLOCK']
for b in blocks:lines.append(f"  @{b['offset']:08x} bytes={b['bytes']} H={b['entropy']}")
report.write_text('\n'.join(lines)+'\n','utf-8')

print('ASSEMBLY_CSHARP_MDL_AUDIT_OK',f'bytes={len(data)}',f'entropy={summary["entropy"]}',f'pe={len(pe_candidates)}',f'termHits={len(term_hits)}',f'strings={len(strings)}')
for h in term_hits[:20]: print('MDL_TERM',h['term'],f"ascii={len(h['asciiOffsets'])}",f"utf16={len(h['utf16leOffsets'])}")
for k,v in sig_hits.items():
    if v: print('MDL_SIGNATURE',k,','.join(map(str,v[:8])))
print('ASSEMBLY_CSHARP_MDL_JSON',out)
print('ASSEMBLY_CSHARP_MDL_REPORT',report)
PY

git add scripts/lastwar-assembly-csharp-mdl-audit.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: audit Assembly-CSharp mdl payload"
  git push origin "$BRANCH"
fi

echo "=== ASSEMBLY-CSHARP.MDL AUDIT TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Binaire non commité. Preview inchangée. main non modifiée."
