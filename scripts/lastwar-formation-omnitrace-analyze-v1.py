#!/usr/bin/env python3
import json, os, re, sys, hashlib
from pathlib import Path
from collections import Counter, defaultdict

session = Path(sys.argv[1])
outfile = Path(sys.argv[2])

def read_text(p, limit=8_000_000):
    try:
        b = p.read_bytes()[:limit]
        return b.decode('utf-8', 'replace')
    except Exception:
        return ''

def nonempty(p):
    try: return p.exists() and p.stat().st_size > 0
    except Exception: return False

files = [p for p in session.iterdir() if p.is_file()]
texts = {p.name: read_text(p) for p in files if p.suffix in {'.log','.txt','.err','.rc','.remote'} or p.name.endswith('.log')}

source_group = {}
for name in texts:
    if name.startswith('logcat-pid'): g='logcat'
    elif name.startswith('logcat-events'): g='events'
    elif name.startswith('strace'): g='strace'
    elif name.startswith('poller-runtime'): g='runtime-poller'
    elif name.startswith('poller-activity'): g='activity'
    elif name.startswith('snapshot-'): g='snapshot'
    elif name.startswith('atrace'): g='atrace'
    elif name.startswith('perfetto'): g='perfetto'
    elif name.startswith('simpleperf'): g='simpleperf'
    else: g='other'
    source_group[name]=g

anchor_re = re.compile(r'(?i)(formation|uihero|hero|murphy|audie|assetbundle|loadasset|instantiate|prefab|bundle|gamers_|xlua|lua|formationrt|rawimage|rendertexture|camera|rpc|protobuf|message|socket|connect\(|sendto\(|recvfrom\(|openat\(|\.bundle\b|\.ab\b)')
strong_low_re = re.compile(r'(?i)(openat\([^\n]*(bundle|gamers_|hero|formation)|connect\(|sendto\(|recvfrom\(|assetbundle|loadasset|instantiate|a_hero_[a-z0-9_]+|formationrt|uiheropvpformationpanel)')
noise_re = re.compile(r'(?i)(ANGLE Warn|MemoryTracking\.cpp|RenderBufferStorageImage|ImplicitMultisampledRenderToTextureImage|SurfaceVK\.cpp|PopupWindow|ViewRootImpl|ThreadedRenderer)')

# Candidate token extraction.
token_res = [
    re.compile(r'\bA_Hero_[A-Za-z0-9_]+\b'),
    re.compile(r'\bUIHero[A-Za-z0-9_]+\b'),
    re.compile(r'\bFormation[A-Za-z0-9_]*\b'),
    re.compile(r'\b(?:gamers_[A-Za-z0-9_./-]+)\b'),
    re.compile(r'(?i)\b(?:Murphy|Audie)\b'),
    re.compile(r'(?i)(?:/[^\s\"\'<>]+(?:\.bundle|\.ab|\.asset|\.bytes|\.data|\.txt|\.json))'),
    re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b'),
]

cand = defaultdict(lambda: {'count':0,'sources':set(),'examples':[],'low':False,'anchor':False})
evidence=[]
for name,text in texts.items():
    group=source_group[name]
    for ln_no,line in enumerate(text.splitlines(),1):
        if not anchor_re.search(line):
            continue
        is_noise = bool(noise_re.search(line))
        ev = {'source':group,'file':name,'line':ln_no,'text':line[:900],'noise':is_noise,'lowLevel':bool(strong_low_re.search(line))}
        evidence.append(ev)
        for rx in token_res:
            for m in rx.finditer(line):
                tok=m.group(0).strip(' ,;:()[]{}')
                if len(tok)<4: continue
                x=cand[tok]
                x['count']+=1; x['sources'].add(group)
                x['low'] = x['low'] or group=='strace' or bool(strong_low_re.search(line))
                x['anchor'] = True
                if len(x['examples'])<4: x['examples'].append({'source':group,'text':line[:600]})

# Also parse all explicit file paths from strace/openat lines.
strace = texts.get('strace.log','')
for line in strace.splitlines():
    if 'openat(' in line or 'open(' in line:
        for q in re.findall(r'"([^"\n]{3,500})"', line):
            if '/' not in q: continue
            x=cand[q]; x['count']+=1; x['sources'].add('strace'); x['low']=True
            if anchor_re.search(q): x['anchor']=True
            if len(x['examples'])<4: x['examples'].append({'source':'strace','text':line[:600]})

# Method health is intentionally evidence-based, not command-exists based.
def health(group, names):
    present=[p for p in files if any(p.name.startswith(n) for n in names)]
    total=sum((p.stat().st_size if p.exists() else 0) for p in present)
    merged='\n'.join(read_text(p,300000) for p in present if p.suffix!='.data' and p.suffix!='.trace')
    low=merged.lower()
    if not present: return {'state':'ABSENT','bytes':0}
    if any(s in low for s in ['permission denied','operation not permitted','not found','cannot link executable','no such file or directory']):
        return {'state':'BLOQUE_OU_PARTIEL','bytes':total}
    if total==0: return {'state':'VIDE','bytes':0}
    return {'state':'OK','bytes':total}

methods={
 'logcat':health('logcat',['logcat-pid','logcat-all']),
 'events':health('events',['logcat-events']),
 'procNetwork':health('poller',['poller-runtime']),
 'activity':health('activity',['poller-activity']),
 'snapshots':health('snapshot',['snapshot-before','snapshot-after']),
 'strace':health('strace',['strace.log','strace-prep']),
 'atrace':health('atrace',['atrace-start','atrace-stop']),
 'perfetto':health('perfetto',['perfetto']),
 'simpleperf':health('simpleperf',['simpleperf']),
}

ranked=[]
for tok,x in cand.items():
    sources=sorted(x['sources'])
    score=min(x['count'],8)
    if x['low']: score+=6
    if x['anchor']: score+=3
    if len(sources)>=2: score+=5*(len(sources)-1)
    if re.search(r'(?i)(A_Hero_|FormationRT|UIHeroPVPFormationPanel|\.bundle$|gamers_)',tok): score+=5
    if re.match(r'^(?:\d{1,3}\.){3}\d{1,3}:\d+$',tok): score+=2
    confidence='FORTE' if score>=12 or (x['low'] and x['anchor']) or len(sources)>=3 else ('MOYENNE' if score>=7 else 'FAIBLE')
    ranked.append({'token':tok,'count':x['count'],'sources':sources,'sourceCount':len(sources),'score':score,'confidence':confidence,'examples':x['examples']})
ranked.sort(key=lambda z:(z['confidence']=='FORTE',z['score'],z['sourceCount'],z['count']), reverse=True)

# Network endpoints and file paths.
network=[]
seen=set()
for name,text in texts.items():
    group=source_group[name]
    for ep in re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b',text):
        key=(ep,group)
        if key not in seen:
            seen.add(key); network.append({'endpoint':ep,'source':group})

paths=[]; seenp=set()
for r in ranked:
    t=r['token']
    if '/' in t or re.search(r'(?i)(\.bundle$|\.ab$|gamers_)',t):
        if t not in seenp: seenp.add(t); paths.append(r)

# Cross-source evidence only.
cross=[r for r in ranked if r['sourceCount']>=2]
strong=[r for r in ranked if r['confidence']=='FORTE']

# Syscall counts.
syscalls={}
if strace:
    for sc in ['openat','read','pread64','mmap','munmap','connect','sendto','recvfrom','sendmsg','recvmsg']:
        syscalls[sc]=len(re.findall(r'\b'+re.escape(sc)+r'\(',strace))

# Session metadata from path/name and current state remnants if present.
label='formation change'
meta_path=session.parent.parent/'current.env'
# current.env may be removed after analyzer, so parse label from nothing if unavailable.
if meta_path.exists():
    m=re.search(r"^LABEL='(.*)'$", read_text(meta_path), re.M)
    if m: label=m.group(1)

result={
 'version':1,
 'session':session.name,
 'label':label,
 'methodHealth':methods,
 'methodOkCount':sum(1 for v in methods.values() if v['state']=='OK'),
 'methodTotal':len(methods),
 'evidenceCount':len(evidence),
 'strongCount':len(strong),
 'crossSourceCount':len(cross),
 'candidateCount':len(ranked),
 'networkCount':len(network),
 'syscalls':syscalls,
 'strong':strong[:80],
 'crossSource':cross[:120],
 'candidates':ranked[:250],
 'paths':paths[:150],
 'network':network[:150],
 'evidence':[e for e in evidence if not e['noise']][:300],
 'noiseEvidence':[e for e in evidence if e['noise']][:80],
 'verdict': (
   'CROSS_SOURCE_STRONG_EVIDENCE' if strong and cross else
   'LOW_LEVEL_EVIDENCE' if any(r['confidence']=='FORTE' for r in ranked) else
   'MULTI_SOURCE_SIGNALS' if cross else
   'CAPTURED_NO_STRONG_CORRELATION'
 ),
 'files':[{'name':p.name,'bytes':p.stat().st_size} for p in sorted(files) if p.exists()],
}

session_analysis=session/'analysis.json'
session_analysis.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
outfile.parent.mkdir(parents=True,exist_ok=True)
outfile.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"OMNITRACE_ANALYSIS_READY session={session.name} methods={result['methodOkCount']}/{result['methodTotal']} strong={result['strongCount']} cross={result['crossSourceCount']} candidates={result['candidateCount']}")
print(f"VERDICT={result['verdict']}")
