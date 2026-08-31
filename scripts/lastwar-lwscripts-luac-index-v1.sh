#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
RAW="$ROOT/frontend/lab/master-assets-v2/runtime-lua/raw/LWScripts.data"
META="$ROOT/frontend/lab/master-assets-v2/meta/lwscripts-luac-index-v1.json"
VIEW="$ROOT/frontend/lab/formation-lua-trace-viewer-data/lwscripts-luac-index.json"
CARVED="$ROOT/frontend/lab/master-assets-v2/runtime-lua/carved-relevant"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LWSCRIPTS_LUAC_INDEX_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$RAW" ]] || fail "LWScripts.data absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$META")" "$(dirname "$VIEW")" "$CARVED" "$(dirname "$REPORT")"
python - "$RAW" "$META" "$VIEW" "$CARVED" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
import collections, hashlib, json, re, statistics, sys
raw,meta,view,carved,report=map(Path,sys.argv[1:])
b=raw.read_bytes(); n=len(b)
SIG=b'\x1bLua'; LUAC_DATA=b'\x19\x93\r\n\x1a\n'
# Exact/high-value anchors only. Broad keywords are used for ranking, not proof edges.
ANCHORS=[
 'UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent','SlotAreas','HeroInfoBars',
 'RenderTexture','targetTexture','RawImage','Camera','A_Hero_Audie_01','Murphy','Audie'
]
BROAD=['formation','pvpformation','uihero','hero','rendertexture','targettexture','rawimage','camera','audie','murphy','assetbundle','loadasset','instantiate']

def all_offsets(pat:bytes):
    pos=0
    while True:
        j=b.find(pat,pos)
        if j<0:return
        yield j; pos=j+1

def valid_header(o:int):
    if o+12>n:return False
    # Lua 5.1..5.4, canonical format 0. Lua 5.2+ carries LUAC_DATA immediately after format.
    ver=b[o+4]; fmt=b[o+5]
    if ver not in (0x51,0x52,0x53,0x54) or fmt!=0:return False
    if ver>=0x52 and b[o+6:o+12]!=LUAC_DATA:return False
    return True

raw_offsets=list(all_offsets(SIG))
valid=[o for o in raw_offsets if valid_header(o)]
# If every marker validates, this is strong evidence of a top-level chunk concatenation.
versions=collections.Counter(f'{b[o+4]>>4}.{b[o+4]&0x0f}' for o in valid)
string_rx=re.compile(rb'[\x20-\x7e]{4,}')

def strings_for(chunk:bytes,limit=600):
    out=[]
    for m in string_rx.finditer(chunk):
        try:s=m.group().decode('ascii','replace')
        except:continue
        if s not in out:out.append(s)
        if len(out)>=limit:break
    return out

def module_guess(strings):
    candidates=[]
    for s in strings:
        t=s.strip().lstrip('@')
        low=t.lower()
        score=0
        if low.endswith('.lua'):score+=100
        if '/' in t or '\\' in t:score+=45
        if low.startswith(('lua/','scripts/','script/','game/','ui/','module/')):score+=30
        if 3<=len(t)<=220 and re.fullmatch(r'[A-Za-z0-9_@./\\:-]+',s):score+=10
        if score:candidates.append((score,-len(t),t))
    if not candidates:return None
    candidates.sort(reverse=True)
    return candidates[0][2]

def safe_name(s):
    s=re.sub(r'[^A-Za-z0-9_.-]+','_',s or '')[:90].strip('_.')
    return s or 'chunk'

chunks=[]; relevant=[]; sizes=[]
for i,o in enumerate(valid):
    end=valid[i+1] if i+1<len(valid) else n
    if end<=o:continue
    c=b[o:end]; size=len(c); sizes.append(size)
    low=c.lower()
    hits=[]
    for a in ANCHORS:
        if a.lower().encode() in low:hits.append(a)
    # Extract strings only once per chunk. Keep all strings only for relevant/high-scoring chunks.
    ss=strings_for(c)
    source=module_guess(ss)
    broad=[]
    textlow='\n'.join(ss).lower()
    for k in BROAD:
        if k in textlow:broad.append(k)
    score=len(hits)*100 + len(set(broad))*8
    if source and any(k in source.lower() for k in ('formation','hero','pvp','render','camera','audie','murphy')):score+=35
    row={'index':i,'offset':o,'end':end,'size':size,'version':f'{b[o+4]>>4}.{b[o+4]&0x0f}','moduleGuess':source,'anchorHits':hits,'keywordHits':broad,'score':score}
    chunks.append(row)
    if score>0 or hits:
        detail=dict(row)
        # Preserve only useful printable constants; enough for visual inspection without multi-MB JSON per chunk.
        useful=[s for s in ss if any(k in s.lower() for k in ('formation','hero','pvp','render','camera','texture','asset','load','instantiate','audie','murphy','ui'))]
        detail['strings']=useful[:180]
        relevant.append(detail)

relevant.sort(key=lambda r:(-r['score'],r['offset']))
# Carve only exact-anchor chunks to keep filesystem small and evidence reproducible.
carved_rows=[]
for r in [x for x in relevant if x['anchorHits']][:160]:
    name=f"{r['offset']:09d}_{safe_name(r.get('moduleGuess'))}.luac"
    p=carved/name
    p.write_bytes(b[r['offset']:r['end']])
    carved_rows.append({'offset':r['offset'],'path':str(p),'name':name,'bytes':r['size'],'anchorHits':r['anchorHits']})

summary={
 'rawMarkers':len(raw_offsets),'validChunks':len(valid),'invalidMarkers':len(raw_offsets)-len(valid),
 'versions':dict(versions),'bytes':n,'relevantChunks':len(relevant),'exactAnchorChunks':sum(1 for r in relevant if r['anchorHits']),
 'sizeMin':min(sizes) if sizes else None,'sizeMedian':int(statistics.median(sizes)) if sizes else None,'sizeMax':max(sizes) if sizes else None,
}
result={
 'format':'WFGG_LASTWAR_LWSCRIPTS_LUAC_INDEX_V1','summary':summary,
 'chunks':chunks,'relevant':relevant[:1200],'carved':carved_rows,
 'anchors':ANCHORS,
 'verdict':'VALID_CONCATENATED_LUA_CHUNKS' if len(valid)>1000 and len(valid)>=int(len(raw_offsets)*0.98) else 'MIXED_LUA_MARKERS',
 'nextHint':'Use exact string constants inside validated chunks to connect Formation UI to runtime hero/render modules; avoid generic hero-only edges.',
 'guardrails':{'validatedLuaHeaders':True,'markerBoundaryCarving':True,'exactAnchorProofOnly':True,'mainUntouched':True}
}
js=json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n';meta.write_text(js,'utf-8');view.write_text(js,'utf-8')
lines=['LWSCRIPTS_LUAC_INDEX_V1_READY',
       f"rawMarkers={summary['rawMarkers']} validChunks={summary['validChunks']} invalid={summary['invalidMarkers']} relevant={summary['relevantChunks']} exactAnchorChunks={summary['exactAnchorChunks']}",
       f"versions={summary['versions']} sizeMedian={summary['sizeMedian']} verdict={result['verdict']}",
       '--- TOP RELEVANT CHUNKS ---']
for r in relevant[:80]:
    lines.append(f"score={r['score']} off={r['offset']} size={r['size']} module={r.get('moduleGuess') or '-'} anchors={','.join(r['anchorHits']) or '-'} keys={','.join(r['keywordHits'][:12]) or '-'}")
if not relevant:lines.append('NONE')
lines.append('--- EXACT ANCHOR CHUNKS ---')
for r in [x for x in relevant if x['anchorHits']][:80]:lines.append(f"off={r['offset']} module={r.get('moduleGuess') or '-'} anchors={','.join(r['anchorHits'])}")
if not any(x['anchorHits'] for x in relevant):lines.append('NONE')
lines.append(f'JSON={meta}');lines.append(f'CARVED={carved}')
text='\n'.join(lines)+'\n';report.write_text(text,'utf-8');print(text,end='')
PY
