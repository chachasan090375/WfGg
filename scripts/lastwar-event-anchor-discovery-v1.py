#!/usr/bin/env python3
from pathlib import Path
from collections import Counter, defaultdict
import csv, json, re, sys, unicodedata

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
TSV = ROOT / 'frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv'
OUT = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path.home() / '.cache/wfgg-lastwar-v31/event-anchor-discovery-v1.json'
OUT.parent.mkdir(parents=True, exist_ok=True)

ANCHORS = {'event','events','activity','activities','eventres','activityres'}
STOP = {'assets','asset','art','ui','icon','icons','texture','textures','prefab','prefabs','material','materials','sprite','sprites','common','main','res','resources','resource','game','gameres','lastwar','bundle','bundles'}

def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def segments(raw):
    raw = str(raw or '').replace('\\','/')
    # split both filesystem separators and Unity/package punctuation
    return [x for x in re.split(r'[/._\-\s]+', raw.lower()) if x]

anchor_next = Counter()
anchor_pair = Counter()
anchor_triplet = Counter()
season_tokens = Counter()
activity_paths = Counter()
anchor_examples = defaultdict(list)
rows = 0
matched_rows = 0

with TSV.open('r', encoding='utf-8', errors='replace', newline='') as fh:
    rd = csv.DictReader(fh, delimiter='\t')
    for r in rd:
        rows += 1
        raw = ' | '.join(str(r.get(k) or '') for k in ('assetPath','logicalName','aliasName','group'))
        seg = segments(raw)
        row_hit = False
        for i, s in enumerate(seg):
            if s not in ANCHORS:
                continue
            row_hit = True
            tail = [x for x in seg[i+1:i+5] if x not in STOP]
            if not tail:
                continue
            first = tail[0]
            anchor_next[first] += 1
            if len(tail) >= 2:
                anchor_pair[first + '/' + tail[1]] += 1
            if len(tail) >= 3:
                anchor_triplet[first + '/' + tail[1] + '/' + tail[2]] += 1
            if len(anchor_examples[first]) < 5:
                anchor_examples[first].append(raw[:600])
        if row_hit:
            matched_rows += 1
            p = str(r.get('assetPath') or '')
            if p:
                activity_paths[p[:350]] += 1
        for m in re.finditer(r'(?i)(?:season|saison|s)[_\- /]?([1-9][0-9]?)', raw):
            season_tokens[m.group(1)] += 1

# Emit enough detail to map internal codenames without dumping the whole TSV.
def top(counter, n):
    return [{'key':k,'count':v} for k,v in counter.most_common(n)]

payload = {
    'schemaVersion': 1,
    'source': str(TSV.relative_to(ROOT)),
    'rows': rows,
    'rowsWithEventActivityAnchor': matched_rows,
    'anchorNextDistinct': len(anchor_next),
    'anchorPairDistinct': len(anchor_pair),
    'seasonTokenCounts': dict(season_tokens.most_common()),
    'topAnchorNext': top(anchor_next, 500),
    'topAnchorPairs': top(anchor_pair, 1000),
    'topAnchorTriplets': top(anchor_triplet, 1000),
    'examplesByAnchorNext': dict(anchor_examples),
    'topAnchoredAssetPaths': top(activity_paths, 500)
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), 'utf-8')
print('EVENT_ANCHOR_DISCOVERY_READY', 'rows=',rows, 'anchoredRows=',matched_rows, 'distinctNext=',len(anchor_next), 'out=',OUT, flush=True)
print('TOP_EVENT_ANCHORS', json.dumps(payload['topAnchorNext'][:80], ensure_ascii=False), flush=True)
