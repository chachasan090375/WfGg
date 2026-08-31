#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/frontend/lab/master-assets-v2/live-trace-v2/sessions"
OUT="$ROOT/frontend/lab/formation-live-trace-data/differential.json"
REPORT="$HOME/storage/downloads/WFGG_FORMATION_LIVE_TRACE_DIFFERENTIAL_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -d "$BASE" ]] || fail "aucune session V2"
python - "$BASE" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import collections,json,re,sys
base,out,report=map(Path,sys.argv[1:])
rows=[]
for d in sorted([p for p in base.iterdir() if p.is_dir()]):
    lp=d/'label.txt'; jp=d/'analysis.json'; logp=d/'logcat.txt'
    if not logp.exists(): continue
    label=lp.read_text('utf-8','replace').strip() if lp.exists() else ''
    lines=logp.read_text('utf-8','replace').splitlines()
    rows.append({'id':d.name,'dir':d,'label':label,'lines':lines})
if len(rows)<2:
    raise SystemExit('ERREUR: il faut au moins deux captures V2 (une modification + un témoin)')
# Prefer newest explicit baseline/control and newest earlier change capture.
baselines=[r for r in rows if any(k in r['label'].lower() for k in ('baseline','temoin','témoin','control','sans changement'))]
if not baselines:
    raise SystemExit('ERREUR: aucune capture témoin trouvée; labelle-la "baseline sans changement"')
basecap=baselines[-1]
changes=[r for r in rows if r['id']!=basecap['id'] and not any(k in r['label'].lower() for k in ('baseline','temoin','témoin','control','sans changement'))]
if not changes: raise SystemExit('ERREUR: aucune capture de changement trouvée')
# Prefer closest preceding change capture.
prior=[r for r in changes if r['id']<basecap['id']]
change=prior[-1] if prior else changes[-1]

def norm(s):
    s=s.strip()
    # Drop epoch / pid / tid / volatile hex addresses / standalone long counters.
    s=re.sub(r'^\d+(?:\.\d+)?\s+','',s)
    s=re.sub(r'\b(?:pid|tid)[=: ]\d+\b',lambda m:m.group(0).split(m.group(0)[-1])[0]+'*',s,flags=re.I)
    s=re.sub(r'\b0x[0-9a-f]{6,}\b','0x*',s,flags=re.I)
    s=re.sub(r'\b\d{8,}\b','#',s)
    s=re.sub(r'\s+',' ',s)
    return s

def fingerprint(s):
    n=norm(s)
    # Normalize android log prefix if present: priority/tag(pid): msg
    n=re.sub(r'^\S+\s+\S+\s+\S+\s+[VDIWEF]\s+','',n)
    return n
bc=collections.Counter(fingerprint(x) for x in basecap['lines'] if x.strip())
cc=collections.Counter(fingerprint(x) for x in change['lines'] if x.strip())
# Lines whose normalized form occurs more often in change than baseline.
delta=[]
for k,c in cc.items():
    excess=c-bc.get(k,0)
    if excess>0 and k:
        delta.append({'text':k,'changeCount':c,'baselineCount':bc.get(k,0),'excess':excess})
# Rank by Formation/hero/runtime/network evidence; generic Lua/Unity alone is weak.
strong_terms=['FormationRT','UIHeroPVPFormationPanel','FormationBg','FormationContent','A_Hero_','LoadAsset','Instantiate','AssetBundle','RenderTexture','targetTexture','RawImage','Murphy','Audie']
medium_terms=['formation','squad','hero','prefab','bundle','camera','render','rpc','request','response','send','proto','pb','socket']
weak_terms=['lua','xlua','unity']
def score(t):
    lo=t.lower(); sc=0; hits=[]
    for x in strong_terms:
        if x.lower() in lo: sc+=100; hits.append(x)
    for x in medium_terms:
        if x.lower() in lo: sc+=20; hits.append(x)
    for x in weak_terms:
        if x.lower() in lo: sc+=2; hits.append(x)
    # bonus for structured IDs/paths
    if re.search(r'\b\d{3,7}\b',t): sc+=8
    if re.search(r'[A-Za-z0-9_./-]+\.(?:bundle|asset|prefab|lua|bytes)',t,re.I): sc+=25
    return sc,sorted(set(hits),key=str.lower)
for r in delta:
    r['score'],r['hits']=score(r['text'])
delta.sort(key=lambda r:(-r['score'],-r['excess'],r['text']))
strong=[r for r in delta if r['score']>=100]
interesting=[r for r in delta if r['score']>=20]
# Network/socket delta from saved snapshots if available.
def lset(d,name):
    p=d/name
    return set(x.strip() for x in p.read_text('utf-8','replace').splitlines() if x.strip()) if p.exists() else set()
change_sock=lset(change['dir'],'sockets-after.txt')-lset(change['dir'],'sockets-before.txt')
base_sock=lset(basecap['dir'],'sockets-after.txt')-lset(basecap['dir'],'sockets-before.txt')
socket_unique=sorted(change_sock-base_sock)
result={
 'format':'WFGG_FORMATION_LIVE_TRACE_DIFFERENTIAL_V1',
 'change':{'sessionId':change['id'],'label':change['label'],'lines':len(change['lines'])},
 'baseline':{'sessionId':basecap['id'],'label':basecap['label'],'lines':len(basecap['lines'])},
 'summary':{'deltaPatterns':len(delta),'interesting':len(interesting),'strong':len(strong),'uniqueSockets':len(socket_unique)},
 'verdict':'STRONG_CHANGE_SPECIFIC_EVIDENCE' if strong else ('CHANGE_SPECIFIC_RUNTIME_SIGNAL' if interesting else 'NO_USEFUL_LOGCAT_DELTA'),
 'strong':strong[:300], 'interesting':interesting[:800], 'topDelta':delta[:1200], 'uniqueSockets':socket_unique,
 'policy':'Only normalized log patterns more frequent in the change capture than in the baseline are promoted. Generic Lua/Unity alone is weak.'
}
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
L=['FORMATION_LIVE_TRACE_DIFFERENTIAL_V1_READY',f"change={change['id']} ({change['label']}) baseline={basecap['id']} ({basecap['label']})",f"delta={len(delta)} interesting={len(interesting)} strong={len(strong)} sockets={len(socket_unique)} verdict={result['verdict']}",'--- STRONG CHANGE-SPECIFIC ---']
for r in strong[:80]: L.append(f"score={r['score']} +{r['excess']} hits={','.join(r['hits'])}: {r['text']}")
if not strong:L.append('NONE')
L.append('--- INTERESTING CHANGE-SPECIFIC ---')
for r in interesting[:120]:L.append(f"score={r['score']} +{r['excess']} hits={','.join(r['hits'])}: {r['text']}")
if not interesting:L.append('NONE')
L.append(f'JSON={out}')
text='\n'.join(L)+'\n';report.write_text(text,'utf-8');print(text,end='')
PY
