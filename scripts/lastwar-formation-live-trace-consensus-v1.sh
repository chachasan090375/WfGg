#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/frontend/lab/master-assets-v2/live-trace-v2/sessions"
OUT="$ROOT/frontend/lab/formation-live-trace-data/consensus.json"
PORT=8788
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-live-trace-consensus.html?v=1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -d "$BASE" ]] || fail "aucune session live-trace-v2"
python - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import json,re,sys,collections
base,out=map(Path,sys.argv[1:])
rows=[]
for d in sorted(base.iterdir()):
    if not d.is_dir(): continue
    lp=d/'label.txt'; log=d/'logcat.txt'
    if not (lp.exists() and log.exists()): continue
    label=lp.read_text('utf-8','replace').strip()
    rows.append({'id':d.name,'dir':d,'label':label,'lines':log.read_text('utf-8','replace').splitlines()})
if not rows: raise SystemExit('aucune session lisible')

def low(x): return x.lower().replace('→','->')
def pick(pred):
    m=[r for r in rows if pred(low(r['label']))]
    return m[-1] if m else None
baseline=pick(lambda s:'baseline' in s or 'témoin' in s or 'temoin' in s or 'sans changement' in s)
reverse=pick(lambda s:('-> murphy' in s or 'vers murphy' in s or 'retour murphy' in s) and 'baseline' not in s)
forward=pick(lambda s:('murphy ->' in s or 'murphy vers' in s) and 'baseline' not in s and 'sans changement' not in s)
if not forward: raise SystemExit('capture aller Murphy -> autre héros introuvable')
if not baseline: raise SystemExit('capture baseline introuvable')
if not reverse:
    print('CONSENSUS_WAIT_REVERSE')
    print('NEXT=bash scripts/lastwar-formation-live-trace-v2.sh start "autre héros -> Murphy"')
    raise SystemExit(4)

# Normalize volatile logcat fields while preserving semantic numbers likely to be IDs.
def norm(s):
    s=s.strip()
    s=re.sub(r'^\d+(?:\.\d+)?\s+','',s)
    s=re.sub(r'\b(?:pid|tid)[=: ]\d+\b',lambda m:re.sub(r'\d+','*',m.group()),s,flags=re.I)
    s=re.sub(r'\b0x[0-9a-fA-F]{6,}\b','0x*',s)
    s=re.sub(r'\b[0-9a-fA-F]{12,}\b','HEX*',s)
    s=re.sub(r'\s+',' ',s)
    return s

def counter(r): return collections.Counter(norm(x) for x in r['lines'] if x.strip())
cf,cr,cb=counter(forward),counter(reverse),counter(baseline)
common=[]
for k in set(cf)&set(cr):
    support=min(cf[k],cr[k]); noise=cb.get(k,0)
    excess=min(max(cf[k]-noise,0),max(cr[k]-noise,0))
    if excess<=0: continue
    common.append({'template':k,'forward':cf[k],'reverse':cr[k],'baseline':noise,'excess':excess})
common.sort(key=lambda x:(-x['excess'],-min(x['forward'],x['reverse']),x['template']))
kw=re.compile(r'(?i)formation|hero|squad|team|asset|bundle|load|instantiate|lua|render|camera|slot|rpc|request|response|proto|pb|socket|network|http|ws|tcp|audie|murphy')
strong_re=re.compile(r'(?i)A_Hero_|UIHeroPVPFormationPanel|FormationRT|AssetBundle|LoadAsset|Instantiate|RenderTexture|targetTexture|RawImage|LWLuaFile|XLua|\bbundle\b|\brpc\b|protobuf|request|response')
signals=[x for x in common if kw.search(x['template'])]
strong=[x for x in common if strong_re.search(x['template'])]
# Extract numeric/token deltas from signal templates to help spot hero/form IDs.
tokens=collections.Counter()
for x in signals:
    for t in re.findall(r'\b(?:[A-Za-z_][A-Za-z0-9_./-]{3,}|\d{3,9})\b',x['template']):
        if t.lower() not in {'android','unity','debug','error','warning','thread','system','native','frame','message'}:
            tokens[t]+=x['excess']
# sockets unique to both change captures, absent baseline

def sockset(r):
    p=r['dir']/'sockets-after.txt'
    return set(x.strip() for x in p.read_text('utf-8','replace').splitlines() if x.strip()) if p.exists() else set()
sf,sr,sb=sockset(forward),sockset(reverse),sockset(baseline)
sock_common=sorted((sf&sr)-sb)
verdict='CONSENSUS_STRONG_RUNTIME_EVIDENCE' if strong else ('CONSENSUS_CHANGE_SIGNALS' if signals else 'NO_STABLE_CHANGE_SIGNAL')
result={
 'format':'WFGG_FORMATION_LIVE_TRACE_CONSENSUS_V1','verdict':verdict,
 'sessions':{'forward':{'id':forward['id'],'label':forward['label']},'reverse':{'id':reverse['id'],'label':reverse['label']},'baseline':{'id':baseline['id'],'label':baseline['label']}},
 'summary':{'commonChangeTemplates':len(common),'signals':len(signals),'strong':len(strong),'commonUniqueSockets':len(sock_common)},
 'strong':strong[:300],'signals':signals[:600],'common':common[:1200],
 'tokens':[{'value':k,'score':v} for k,v in tokens.most_common(200)],
 'commonUniqueSockets':sock_common[:300],
 'method':'Intersection aller/retour après soustraction du témoin. Une ligne doit être excédentaire dans les deux changements pour survivre.'
}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_LIVE_TRACE_CONSENSUS_V1_READY forward={forward['id']} reverse={reverse['id']} baseline={baseline['id']} common={len(common)} signals={len(signals)} strong={len(strong)} sockets={len(sock_common)} verdict={verdict}")
print('--- TOP STRONG ---')
for x in strong[:30]: print(f"+{x['excess']} F{x['forward']} R{x['reverse']} B{x['baseline']} :: {x['template']}")
print('--- TOP SIGNALS ---')
for x in signals[:30]: print(f"+{x['excess']} F{x['forward']} R{x['reverse']} B{x['baseline']} :: {x['template']}")
print('JSON='+str(out))
PY
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then :; else
  (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &)
  sleep 1
fi
printf 'VIEWER=%s\n' "$VIEWER"
