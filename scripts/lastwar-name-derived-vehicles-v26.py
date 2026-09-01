#!/usr/bin/env python3
import csv, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv"
OUT = ROOT / "frontend/lab/asset-name-derived-vehicles-v26"
OUT.mkdir(parents=True, exist_ok=True)

STRUCTURAL_RE = re.compile(r"(?i)(?:^|/)models/(?:new/)?cars/")
CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
IMAGE_EXTS = {'.png','.jpg','.jpeg','.tga','.psd','.exr','.bmp','.tif','.tiff','.dds','.ktx','.ktx2'}


def toks(text):
    text = CAMEL_RE.sub(r"\1 \2", str(text or ""))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower()
    return [x for x in text.split() if len(x) >= 3 and not x.isdigit()]


def feats(text):
    ts = toks(text)
    out = set(ts)
    out.update(ts[i]+'_'+ts[i+1] for i in range(len(ts)-1))
    return out


def structural_info(asset_path):
    p = str(asset_path or "").replace('\\','/')
    m = STRUCTURAL_RE.search(p)
    if not m:
        return None
    rel = p[m.end():]
    parts = [x for x in rel.split('/') if x]
    root = parts[0] if parts else ''
    return {'root':root,'relative':rel,'prefix':p[:m.end()]}


def row_iter():
    with SOURCE.open('r',encoding='utf-8',errors='replace',newline='') as f:
        yield from csv.DictReader(f, delimiter='\t')

if not SOURCE.exists():
    raise SystemExit(f'Missing source: {SOURCE}')

# PASS 1: global feature document frequencies and certain vehicle seed rows.
global_df=Counter(); seed_df=Counter(); seed_roots=defaultdict(set); seed_examples=defaultdict(list)
rows_total=0; seed_rows=0; roots=set()
for r in row_iter():
    rows_total += 1
    path=r.get('assetPath','')
    rf=feats(path)
    global_df.update(rf)
    si=structural_info(path)
    if not si: continue
    seed_rows += 1; roots.add(si['root'])
    # Remove hero/model identity itself: learn only the wording around the model.
    rel=si['relative']
    root=si['root']
    tail=rel[len(root):] if root else rel
    sf=feats(tail)
    rootf=feats(root)
    sf -= rootf
    for f in sf:
        seed_df[f]+=1; seed_roots[f].add(root)
        if len(seed_examples[f])<5: seed_examples[f].append(path)

root_count=max(1,len(roots))
learned=[]
for f,sn in seed_df.items():
    rn=len(seed_roots[f]); gn=global_df.get(f,0)
    sp=sn/max(1,seed_rows); gp=gn/max(1,rows_total)
    lift=(sp+1e-9)/(gp+1e-9)
    # No semantic stop-word list: keep only features that recur across independent
    # vehicle roots and are statistically concentrated in the Cars seed set.
    if rn < 2: continue
    if lift < 3.5: continue
    if gp > 0.08: continue
    score=math.log2(max(lift,1.000001))*math.log1p(rn)*math.log1p(sn)
    learned.append({'feature':f,'seedRows':sn,'seedRoots':rn,'globalRows':gn,'lift':round(lift,3),'score':round(score,3),'examples':seed_examples[f]})
learned.sort(key=lambda x:(-x['score'],-x['seedRoots'],x['feature']))
fm={x['feature']:x for x in learned}
strong={x['feature'] for x in learned if x['seedRoots']>=3 and x['lift']>=5.0}

# PASS 2: candidates outside Cars. Require multiple independently learned signatures,
# or one exceptionally vehicle-specific signature seen across many vehicle roots.
candidates=[]; bundles=set(); ext_counts=Counter(); two_d=0
for r in row_iter():
    path=r.get('assetPath','')
    if structural_info(path): continue
    fs=feats(path)
    ms=[fm[f] for f in (fs & strong)]
    if not ms: continue
    exceptional=[m for m in ms if m['seedRoots']>=5 and m['lift']>=15]
    if len(ms)<2 and not exceptional: continue
    score=sum(m['score'] for m in ms)
    ext=Path(path).suffix.lower()
    is2d=ext in IMAGE_EXTS
    if is2d: two_d += 1
    ext_counts[ext or '(none)'] += 1
    logical=r.get('logicalName','')
    if logical: bundles.add(logical)
    candidates.append({
        'assetPath':path,'bundleId':r.get('bundleId',''),'logicalName':logical,'aliasName':r.get('aliasName',''),
        'declaredBytes':r.get('declaredBytes',''),'ext':ext,'is2D':is2d,'score':round(score,3),
        'confidence':'forte' if len(ms)>=3 or exceptional else 'a-verifier',
        'matches':[{'feature':m['feature'],'seedRoots':m['seedRoots'],'seedRows':m['seedRows'],'globalRows':m['globalRows'],'lift':m['lift'],'score':m['score']} for m in sorted(ms,key=lambda x:-x['score'])[:12]]
    })

candidates.sort(key=lambda x:(0 if x['is2D'] else 1, -x['score'], x['assetPath']))
manifest={
    'version':26,'method':'statistical-name-signatures-no-predefined-vehicle-vocabulary',
    'sourceRows':rows_total,'seedRows':seed_rows,'seedRoots':len(roots),
    'learnedSignatureCount':len(learned),'strongSignatureCount':len(strong),
    'candidateCount':len(candidates),'twoDCandidateCount':two_d,'bundleCount':len(bundles),
    'extensionCounts':dict(ext_counts.most_common()),'learnedSignatures':learned,'candidates':candidates
}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'selected-bundles.txt').write_text('\n'.join(sorted(bundles))+'\n',encoding='utf-8')
print(f'V26 sourceRows={rows_total} seedRows={seed_rows} seedRoots={len(roots)} learned={len(learned)} strong={len(strong)} candidates={len(candidates)} twoD={two_d} bundles={len(bundles)}')
print(OUT/'manifest.json')
