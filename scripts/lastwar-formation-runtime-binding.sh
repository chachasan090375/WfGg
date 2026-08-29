#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — trace the native runtime binding behind FormationRT.
# Reads only the installed Last War APK(s) and the already-extracted gameres.
# Goal: identify the IL2CPP classes/method/string/resource names that bind
# UIHeroPVPFormationPanel / FormationRT / HeroShowBlend to the rendered scene.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-runtime-binding-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_BINDING.txt"
TMP="${TMPDIR:-$HOME/.cache}/wfgg-formation-runtime-binding"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
command -v strings >/dev/null 2>&1 || fail "commande strings absente (pkg install binutils)"
mkdir -p "$TMP" "$(dirname "$OUT")" "$(dirname "$REPORT")"
rm -rf "$TMP"/*

mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"

python - "$TMP" "$OUT" "$REPORT" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
import json,sys,zipfile,re,subprocess,os,shutil

tmp=Path(sys.argv[1]); out=Path(sys.argv[2]); report=Path(sys.argv[3]); apks=[Path(x) for x in sys.argv[4:]]

# Terms are deliberately narrow: we are looking for the runtime glue, not doing
# a broad asset scrape.
terms=[
 'UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent',
 'HeroShowBlend','HeroShow','PVPFormation','FormationPanel','FormationScene',
 'HeroShowCamera','ShowCamera','RenderTexture','FormationCamera',
 'biandui_cheku','A_build_formation','WorldCityGrass'
]
rx=re.compile('|'.join(re.escape(x) for x in terms),re.I)

entries=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for n in z.namelist():
                low=n.lower()
                if ('global-metadata.dat' in low or low.endswith('libil2cpp.so') or
                    low.endswith('resources.assets') or low.endswith('globalgamemanagers') or
                    low.endswith('level0') or low.endswith('level1')):
                    try:
                        data=z.read(n)
                    except Exception:
                        continue
                    p=tmp/(apk.name.replace('/','_')+'__'+Path(n).name)
                    p.write_bytes(data)
                    entries.append({'apk':str(apk),'entry':n,'file':str(p),'bytes':len(data)})
    except Exception:
        pass

# Extract printable strings and retain context windows around exact hits.
hits=[]
for e in entries:
    p=Path(e['file'])
    try:
        cp=subprocess.run(['strings','-a','-n','4',str(p)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,errors='replace',timeout=180)
        lines=cp.stdout.splitlines()
    except Exception as ex:
        e['stringsError']=repr(ex);continue
    indexes=[i for i,s in enumerate(lines) if rx.search(s)]
    e['hitCount']=len(indexes)
    seen=set()
    for i in indexes:
        lo=max(0,i-12); hi=min(len(lines),i+13)
        ctx=lines[lo:hi]
        key=(e['entry'],i,lines[i])
        if key in seen:continue
        seen.add(key)
        hits.append({'entry':e['entry'],'index':i,'match':lines[i],'context':ctx})

# Correlate likely runtime nouns/classes/method names from nearby contexts.
TOK=re.compile(r'^[A-Za-z_][A-Za-z0-9_.$+<>`:/-]{3,}$')
score={}
for h in hits:
    for s in h['context']:
        s=s.strip()
        if len(s)>160 or not TOK.match(s):continue
        w=0
        sl=s.lower()
        if 'formation' in sl:w+=6
        if 'hero' in sl:w+=3
        if 'camera' in sl:w+=5
        if 'render' in sl:w+=4
        if 'scene' in sl:w+=4
        if 'show' in sl:w+=2
        if 'texture' in sl:w+=2
        if w:score[s]=score.get(s,0)+w
candidates=sorted(({'text':k,'score':v} for k,v in score.items()),key=lambda x:(-x['score'],x['text']))[:250]

summary={
 'format':'WFGG_LASTWAR_FORMATION_RUNTIME_BINDING_V1',
 'networkUsed':False,'generatedArtwork':False,
 'terms':terms,'scannedEntries':entries,'hits':hits,'candidates':candidates,
 'guardrails':{'apkReadOnly':True,'mainUntouched':True,'previewUntouched':True}
}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION RUNTIME BINDING','READ-ONLY APK / IL2CPP STRING TRACE','',
       f'apkCount={len(apks)} scannedEntries={len(entries)} hits={len(hits)}','','TOP CANDIDATES']
for c in candidates[:100]:lines.append(f"  {c['score']:4d}  {c['text']}")
lines+=['','MATCH CONTEXTS']
for h in hits[:120]:
    lines.append(f"--- {h['entry']} :: {h['match']}")
    for s in h['context']:lines.append('  '+s[:500])
report.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RUNTIME_BINDING_OK',f'scanned={len(entries)}',f'hits={len(hits)}',f'candidates={len(candidates)}')
for c in candidates[:30]:print('CANDIDATE',c['score'],c['text'])
print('FORMATION_RUNTIME_BINDING_JSON',out)
print('FORMATION_RUNTIME_BINDING_REPORT',report)
PY

git add scripts/lastwar-formation-runtime-binding.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace Formation runtime binding"
  git push origin "$BRANCH"
fi

echo "=== FORMATION RUNTIME BINDING TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "main non modifiée."
