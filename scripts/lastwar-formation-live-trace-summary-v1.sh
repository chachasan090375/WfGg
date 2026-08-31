#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
LATEST="$ROOT/frontend/lab/formation-live-trace-data/latest.json"
BASE="$ROOT/frontend/lab/master-assets-v2/live-trace-v2/sessions"
OUT="$ROOT/frontend/lab/formation-live-trace-data/summary.json"
REPORT="$HOME/storage/downloads/WFGG_FORMATION_LIVE_TRACE_SUMMARY_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$LATEST" ]] || fail "aucune capture live analysée"
python - "$LATEST" "$BASE" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import json,re,sys,collections
latest,base,out,report=map(Path,sys.argv[1:])
d=json.loads(latest.read_text('utf-8'))
sid=str(d.get('sessionId') or '')
sess=base/sid
logp=sess/'logcat.txt'
lines=logp.read_text('utf-8','replace').splitlines() if logp.exists() else []
direct=sorted(d.get('directEvidence') or [],key=lambda r:r.get('line') or 0)
relevant=sorted(d.get('relevant') or [],key=lambda r:r.get('line') or 0)

patterns={
 'prefabOrAsset':re.compile(r'\b(?:A_Hero_[A-Za-z0-9_]+|UIHero[A-Za-z0-9_]+|Formation[A-Za-z0-9_]+|[A-Za-z0-9_./-]+\.bundle)\b'),
 'calls':re.compile(r'\b(?:AssetBundle(?:\.[A-Za-z0-9_]+)?|LoadAsset(?:Async)?|Instantiate|RenderTexture|targetTexture|RawImage|Camera|XLua|LWLuaFile)\b',re.I),
 'bundleNumbers':re.compile(r'(?i)(?:bundle(?:id)?\s*[=: ]\s*|bundle[^0-9]{0,12})(\d{3,7})\b'),
 'paths':re.compile(r'(?:(?:assets?|gamers?)[A-Za-z0-9_./\\-]{3,}|[A-Za-z0-9_./\\-]+\.(?:bundle|asset|prefab|lua|bytes))',re.I),
}
known_heroes=['Murphy','Audie']
idents=collections.Counter(); calls=collections.Counter(); bundles=collections.Counter(); paths=collections.Counter(); heroes=collections.Counter()

def mine(text):
    for x in patterns['prefabOrAsset'].findall(text): idents[x]+=1
    for x in patterns['calls'].findall(text): calls[x]+=1
    for x in patterns['bundleNumbers'].findall(text): bundles[x]+=1
    for x in patterns['paths'].findall(text): paths[x]+=1
    lo=text.lower()
    for h in known_heroes:
        if h.lower() in lo: heroes[h]+=1

timeline=[]
for r in direct:
    ln=int(r.get('line') or 0); text=str(r.get('text') or '')
    mine(text)
    ctx=[]
    if lines and ln>0:
        a=max(0,ln-4); b=min(len(lines),ln+3)
        ctx=[{'line':i+1,'text':lines[i][:2400],'isEvidence':(i+1==ln)} for i in range(a,b)]
        for c in ctx: mine(c['text'])
    timeline.append({'line':ln,'text':text,'hits':r.get('hits') or [],'score':r.get('score'),'context':ctx})

# Also mine nearby relevant lines, but keep them separate from direct proof.
for r in relevant:
    if int(r.get('line') or 0) not in {x['line'] for x in timeline}: mine(str(r.get('text') or ''))

# Collapse repeated direct log messages for readability.
groups=[]
bytext=collections.OrderedDict()
for t in timeline:
    key=re.sub(r'^\d+(?:\.\d+)?\s+','',t['text'])
    key=re.sub(r'\bpid[=: ]\d+\b','pid=*',key,flags=re.I)
    if key not in bytext: bytext[key]={'count':0,'lines':[],'example':t['text'],'hits':set()}
    g=bytext[key]; g['count']+=1; g['lines'].append(t['line']); g['hits'].update(t['hits'])
for g in bytext.values(): groups.append({'count':g['count'],'lines':g['lines'],'example':g['example'],'hits':sorted(g['hits'])})

result={
 'format':'WFGG_FORMATION_LIVE_TRACE_SUMMARY_V1','sessionId':sid,'label':d.get('label'),'verdict':d.get('verdict'),
 'sourceSummary':d.get('summary') or {},
 'extracted':{
   'identifiers':[{'value':k,'count':v} for k,v in idents.most_common(80)],
   'calls':[{'value':k,'count':v} for k,v in calls.most_common(80)],
   'bundleNumbers':[{'value':k,'count':v} for k,v in bundles.most_common(80)],
   'paths':[{'value':k,'count':v} for k,v in paths.most_common(80)],
   'knownHeroes':[{'value':k,'count':v} for k,v in heroes.most_common(30)],
 },
 'directTimeline':timeline,
 'directGroups':groups,
 'socketAdded':d.get('socketAdded') or [],
 'knownStaticMap':d.get('knownStaticMap') or {},
 'note':'Les identifiants extraits sont des tokens observés dans les logs/contexte; seules les lignes de directTimeline marquées comme preuves viennent de directEvidence.'
}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
L=[]
L.append('FORMATION_LIVE_TRACE_SUMMARY_V1_READY')
L.append(f"session={sid} verdict={result['verdict']} direct={len(timeline)} groups={len(groups)}")
L.append('--- IDENTIFIERS ---')
for x in result['extracted']['identifiers'][:40]:L.append(f"{x['count']}x {x['value']}")
L.append('--- CALLS ---')
for x in result['extracted']['calls'][:40]:L.append(f"{x['count']}x {x['value']}")
L.append('--- BUNDLE NUMBERS ---')
for x in result['extracted']['bundleNumbers'][:40]:L.append(f"{x['count']}x {x['value']}")
L.append('--- DIRECT TIMELINE ---')
for t in timeline:
    L.append(f"L{t['line']} hits={','.join(t['hits'])}: {t['text']}")
L.append(f'JSON={out}')
text='\n'.join(L)+'\n';report.write_text(text,'utf-8');print(text,end='')
PY
