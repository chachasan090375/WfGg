#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PREBLURRED / PREBAKED FORMATION TEXTURE CANDIDATES V1
# Existing evidence only: exact V4 Formation closure + graphics master index + V002→0012 history.
# NO APK read, NO bundle scan/extraction, NO candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
INDEXDIR="$ROOT/frontend/lab/master-assets-v2/index"
V4="$META/formation-ptr-exact-v4.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
GINDEX="$INDEXDIR/lastwar-graphics-master-index-v1.json"
GHIST="$INDEXDIR/lastwar-graphics-history-v002-0012-v1.json"
OUT="$META/formation-preblurred-texture-candidates-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_CANDIDATES_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$V4" "$SUMMARY" "$GINDEX" "$GHIST"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$V4" "$SUMMARY" "$GINDEX" "$GHIST" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import json,re,sys

v4p,sump,indexp,histp,outp,reportp=map(Path,sys.argv[1:])
g=json.loads(v4p.read_text('utf-8'))
s=json.loads(sump.read_text('utf-8'))
idx=json.loads(indexp.read_text('utf-8'))
hist=json.loads(histp.read_text('utf-8'))

closure=[int(x) for x in ((s.get('dependencySelection') or {}).get('selectedBundleIds') or [])]
if len(closure)!=195:
    raise SystemExit(f'FORMATION_CLOSURE_COUNT_MISMATCH expected=195 actual={len(closure)}')
closure_set=set(closure)
if int(((s.get('counts') or {}).get('objects') or 0))!=3209:
    raise SystemExit('FORMATION_V4_OBJECT_COUNT_MISMATCH')

IMG_EXT=re.compile(r'\.(png|jpe?g|tga|psd|exr|hdr|webp|bmp|tiff?)$',re.I)
PATH_RX=re.compile(r'(^|/)(assets|resources|ui|texture|textures|atlas|atlases|sprite|sprites|background|bg|world|scene|map)[/\\]|\.(png|jpe?g|tga|psd|exr|hdr|webp|bmp|tiff?)$',re.I)
STRONG_RX=re.compile(r'(formation|background|\bbg\b|blur|world|map|scene|city|terrain|splat|fog|render.?texture|snapshot|capture)',re.I)
NEG_RX=re.compile(r'(heroicon|avatar|headicon|emoji|font|iconssmall|mail|button|btn_|badge|flag|country)',re.I)
TYPE_KEYS=('type','class','className','objectType','assetType','kind')
BUNDLE_KEYS=('bundleId','bundleID','bundle_id','id')
PATH_KEYS=('assetPath','assetPaths','path','paths','sourcePath','resourcePath','name','logicalName','file','filename')

# Generic recursive traversal because the graphics index is intentionally treated as an opaque registry.
def walk(obj, ctx=None, depth=0):
    if depth>40:return
    if isinstance(obj,dict):
        local=dict(ctx or {})
        for k,v in obj.items():
            lk=str(k).lower()
            if lk in ('bundleid','bundle_id') and isinstance(v,(int,str)):
                try: local['bundleId']=int(v)
                except: pass
            elif lk in ('bundlename','logicalname','aliasname') and isinstance(v,str):
                local[lk]=v
            elif lk in ('type','class','classname','objecttype','assettype','kind') and isinstance(v,str):
                local.setdefault('types',[]).append(v)
        yield obj,local
        for v in obj.values():
            if isinstance(v,(dict,list)):yield from walk(v,local,depth+1)
    elif isinstance(obj,list):
        for v in obj:
            if isinstance(v,(dict,list)):yield from walk(v,ctx,depth+1)

def strings_from_record(d):
    vals=[]
    def rec(x,k='',depth=0):
        if depth>6:return
        if isinstance(x,str):
            if len(x)<=1200:vals.append((k,x))
        elif isinstance(x,list):
            for y in x[:1000]:rec(y,k,depth+1)
        elif isinstance(x,dict):
            for kk,v in x.items():
                if isinstance(v,(str,list,dict)):rec(v,str(kk),depth+1)
    rec(d)
    return vals

def score_path(p,types):
    q=p.lower();score=0;reasons=[]
    if IMG_EXT.search(p):score+=30;reasons.append('image-extension')
    if any('texture2d' in t.lower() for t in types):score+=30;reasons.append('Texture2D-type')
    if any('sprite' in t.lower() for t in types):score+=12;reasons.append('Sprite-type')
    if STRONG_RX.search(p):score+=24;reasons.append('formation/background-world-keyword')
    if re.search(r'(background|blur|formation|render.?texture|snapshot|capture)',p,re.I):score+=18;reasons.append('strong-background-keyword')
    if NEG_RX.search(p):score-=18;reasons.append('ui-small/icon-penalty')
    if '/atlas' in q or '_atlas' in q:score-=5;reasons.append('atlas-penalty')
    return score,reasons

index_records=[]
seen=set()
for d,ctx in walk(idx):
    bid=ctx.get('bundleId')
    if bid not in closure_set:continue
    types=[str(x) for x in (ctx.get('types') or [])]
    vals=strings_from_record(d)
    for k,v in vals:
        if not (IMG_EXT.search(v) or PATH_RX.search(v) or STRONG_RX.search(v)):continue
        sc,reasons=score_path(v,types)
        key=(bid,v)
        if key in seen:continue
        seen.add(key)
        index_records.append({'bundleId':bid,'value':v,'field':k,'types':types[:8],'score':sc,'reasons':reasons,'logicalName':ctx.get('logicalname') or ctx.get('bundlename'),'aliasName':ctx.get('aliasname')})
index_records.sort(key=lambda x:(-x['score'],x['bundleId'],x['value']))

# Exact Texture2D/Sprite objects already reachable in the closed serialized graph.
graph_nodes=[]
for n in (g.get('nodes') or []):
    typ=str(n.get('type') or '')
    if typ not in ('Texture2D','Sprite'):continue
    graph_nodes.append({'id':n.get('id'),'serializedFile':n.get('serializedFile'),'pathID':n.get('pathID'),'type':typ,'name':n.get('name') or '',
                        'renderState':n.get('renderState') if typ=='Texture2D' else None})

# Historical registry is consulted for names/identity only. Physical offsets are never reused.
hist_hits=[];hseen=set()
for d,ctx in walk(hist):
    bid=ctx.get('bundleId')
    if bid not in closure_set:continue
    types=[str(x) for x in (ctx.get('types') or [])]
    for k,v in strings_from_record(d):
        if not (IMG_EXT.search(v) or STRONG_RX.search(v)):continue
        sc,reasons=score_path(v,types)
        key=(bid,v)
        if key in hseen:continue
        hseen.add(key)
        hist_hits.append({'bundleId':bid,'value':v,'field':k,'types':types[:8],'score':sc,'reasons':reasons})
hist_hits.sort(key=lambda x:(-x['score'],x['bundleId'],x['value']))

# Candidate buckets. These are scope/ranking heuristics only.
image_like=[x for x in index_records if 'image-extension' in x['reasons'] or 'Texture2D-type' in x['reasons'] or 'Sprite-type' in x['reasons']]
strong=[x for x in image_like if x['score']>=30]
preblur=[x for x in image_like if re.search(r'(background|blur|formation|render.?texture|snapshot|capture|world|map|scene|city|terrain|fog)',x['value'],re.I)]

by_bundle=Counter(x['bundleId'] for x in image_like)
result={
 'format':'WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_CANDIDATES_V1',
 'sources':{'ptrGraph':str(v4p),'ptrSummary':str(sump),'graphicsIndex':str(indexp),'graphicsHistory':str(histp)},
 'scope':{'formationClosureBundleCount':len(closure),'formationClosureBundleIds':closure,'v4ObjectCount':3209},
 'counts':{'indexClosureRecords':len(index_records),'imageLikeCandidates':len(image_like),'strongImageCandidates':len(strong),'preblurKeywordCandidates':len(preblur),'exactGraphTextureSpriteNodes':len(graph_nodes),'historicalClosureHits':len(hist_hits)},
 'topImageCandidates':image_like[:400],
 'preblurKeywordCandidates':preblur[:400],
 'exactGraphTextureSpriteNodes':graph_nodes[:1200],
 'historicalNameHits':hist_hits[:300],
 'imageCandidateBundles':[{'bundleId':bid,'candidateCount':cnt} for bid,cnt in by_bundle.most_common()],
 'conclusion':{
   'fixedTextureHypothesisNotEliminated':True,
   'nextStrategy':'extract_only_ranked_closure_texture_candidates_for_visual_comparison' if image_like else 'no_indexed_closure_image_candidate_expand_to_runtime_loaded_bundle_identity',
   'important':'Index/path/type scoring is scope heuristic only. A candidate becomes evidence only after exact extraction and visual/identity verification.'
 },
 'guardrails':{'graphicsIndexQueried':True,'graphicsHistoryQueried':True,'historicalPhysicalOffsetsReused':False,'apkAccess':False,'bundleScan':False,'bundleExtraction':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION PREBLURRED / PREBAKED TEXTURE CANDIDATES V1','',
 f"closureBundles={len(closure)} v4Objects=3209",
 f"indexClosureRecords={len(index_records)} imageLikeCandidates={len(image_like)} strongImageCandidates={len(strong)} preblurKeywordCandidates={len(preblur)} exactGraphTextureSpriteNodes={len(graph_nodes)} historicalClosureHits={len(hist_hits)}",
 f"nextStrategy={result['conclusion']['nextStrategy']}",'',
 'TOP PREBLUR / BACKGROUND-LIKE IMAGE CANDIDATES']
if preblur:
    for x in preblur[:120]:lines.append(f"  score={x['score']} bundle={x['bundleId']} field={x['field']} types={','.join(x['types']) or '-'} value={x['value']}")
else:lines.append('  NONE')
lines+=['','TOP IMAGE-LIKE CANDIDATES']
if image_like:
    for x in image_like[:160]:lines.append(f"  score={x['score']} bundle={x['bundleId']} field={x['field']} types={','.join(x['types']) or '-'} value={x['value']}")
else:lines.append('  NONE')
lines+=['','EXACT GRAPH Texture2D / Sprite NODES']
if graph_nodes:
    for x in graph_nodes[:160]:lines.append(f"  type={x['type']} file={x['serializedFile']} pathID={x['pathID']} name={x['name']}")
else:lines.append('  NONE')
lines+=['','HISTORICAL NAME HITS IN CURRENT CLOSURE BUNDLE IDS (IDENTITY/NAMES ONLY)']
if hist_hits:
    for x in hist_hits[:80]:lines.append(f"  score={x['score']} bundle={x['bundleId']} value={x['value']}")
else:lines.append('  NONE')
lines+=['','NEXT '+result['conclusion']['nextStrategy'],
 'RULE: ranking/path keywords are scope heuristics only; no candidate is promoted without exact extraction + verification.',
 'RULE: V002→0012 history is consulted for names/identity only; no historical physical offset is reused.',
 'RULE: no APK read, no bundle scan/extraction, main or preview modification.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_PREBLUR_CANDIDATES_OK',f'closure={len(closure)}',f'image={len(image_like)}',f'preblur={len(preblur)}',f'graphTextures={len(graph_nodes)}')
for x in preblur[:30]:print('FORMATION_PREBLUR_CANDIDATE',f"score={x['score']}",f"bundle={x['bundleId']}",x['value'])
print('FORMATION_PREBLUR_NEXT',result['conclusion']['nextStrategy'])
print('FORMATION_PREBLUR_JSON',outp)
print('FORMATION_PREBLUR_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: index preblurred Formation texture candidates"
  git push origin "$BRANCH"
fi

echo "=== FORMATION PREBLURRED TEXTURE CANDIDATES TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Aucun APK lu. Aucun candidat promu. main/preview inchangés."
