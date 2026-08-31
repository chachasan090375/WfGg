#!/usr/bin/env python3
import json, re, sys
from pathlib import Path
from collections import Counter, defaultdict

if len(sys.argv) < 4:
    print('Usage: lastwar-formation-omnitrace-differential-v2.py ACTION_DIR BASELINE_DIR OUTFILE')
    raise SystemExit(2)

action_dir=Path(sys.argv[1]); baseline_dir=Path(sys.argv[2]); outfile=Path(sys.argv[3])
TEXT_SUFFIX={'.log','.txt','.err','.rc','.remote'}
STREAM_PREFIX=('logcat-pid','logcat-all','logcat-events','poller-runtime','poller-activity')

INFRA_RE=re.compile(r'(?i)(WFGG_|FORMATION_OMNITRACE|STRACE_DEPLOY_PROBE|wfgg-omnitrace|/data/local/tmp/wfgg-|lastwar-formation-omnitrace|ACTION_WINDOW_|REMOTE_STRACE|LOCAL_STRACE|DEPENDENCY_CLOSURE|PUSH_LIB|MISSING_REMOTE_DEP|adb\s+-s|FORMATION_STRACE_DEPLOY_PROBE|REMOTE_LD_LIBRARY_PATH|REMOTE_STRACE_|TERMUX DEPENDENC)')
GRAPHICS_NOISE_RE=re.compile(r'(?i)(ANGLE Warn|MemoryTracking\.cpp|RenderBufferStorageImage|ImplicitMultisampledRenderToTextureImage|SurfaceVK\.cpp|PopupWindow|ViewRootImpl|ThreadedRenderer|Choreographer|BufferQueue|BLASTBufferQueue)')
TARGET_RE=re.compile(r'(?i)(formationrt|uiheropvpformationpanel|a_hero_[a-z0-9_]+|murphy|audie|gamers_|assetbundle|loadasset|instantiate|prefab|\.bundle\b|\.ab\b|lwscripts|xlua|lua)')
ANCHOR_RE=re.compile(r'(?i)(formation|uihero|hero|murphy|audie|assetbundle|loadasset|instantiate|prefab|bundle|gamers_|xlua|lua|formationrt|rawimage|rendertexture|rpc|protobuf|message|socket|connect\(|sendto\(|recvfrom\(|openat\(|\.bundle\b|\.ab\b)')
SYSCALL_RE=re.compile(r'(?i)\b(openat|open|connect|sendto|recvfrom|sendmsg|recvmsg|read|pread64|mmap)\(')
CONCRETE_TOKEN_RE=re.compile(r'(?i)(^A_Hero_|^UIHeroPVPFormationPanel$|^FormationRT$|^gamers_|\.bundle$|\.ab$|/.*(?:asset|bundle|gamers_|hero|formation|lwscripts)|\bMurphy\b|\bAudie\b)')
GENERIC_TOKEN_RE=re.compile(r'(?i)^(LoadAsset|Instantiate|AssetBundle|Formation|Hero|Lua|XLua)$')

TOKEN_RES=[
 re.compile(r'\bA_Hero_[A-Za-z0-9_]+\b'),
 re.compile(r'\bUIHero[A-Za-z0-9_]+\b'),
 re.compile(r'\bFormation[A-Za-z0-9_]*\b'),
 re.compile(r'\b(?:gamers_[A-Za-z0-9_./-]+)\b'),
 re.compile(r'(?i)\b(?:Murphy|Audie)\b'),
 re.compile(r'(?i)(?:/[^\s\"\'<>]+(?:\.bundle|\.ab|\.asset|\.bytes|\.data|\.txt|\.json))'),
 re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b'),
 re.compile(r'\b(?:LoadAsset|Instantiate|AssetBundle|FormationRT|UIHeroPVPFormationPanel|LWScripts(?:\.data|\.txt)?)\b'),
]

def read_text(p,limit=24_000_000):
    try: return p.read_bytes()[:limit].decode('utf-8','replace')
    except Exception: return ''

def group_for(name):
    if name.startswith(('logcat-pid','logcat-all')): return 'logcat'
    if name.startswith('logcat-events'): return 'events'
    if name.startswith('strace'): return 'strace'
    if name.startswith('poller-runtime'): return 'procNetwork'
    if name.startswith('poller-activity'): return 'activity'
    if name.startswith('snapshot-'): return 'snapshots'
    if name.startswith('atrace'): return 'atrace'
    if name.startswith('perfetto'): return 'perfetto'
    if name.startswith('simpleperf'): return 'simpleperf'
    return 'other'

def action_slice(text):
    lines=text.splitlines()
    s=next((i for i,x in enumerate(lines) if x.startswith('@@ACTION_WINDOW_START ')),None)
    e=next((i for i,x in enumerate(lines) if x.startswith('@@ACTION_WINDOW_STOP ') and (s is None or i>s)),None)
    if s is not None and e is not None: return '\n'.join(lines[s+1:e])
    if s is not None: return '\n'.join(lines[s+1:])
    return text

def infer_infra_endpoints(root):
    out=set()
    for p in root.iterdir():
        if not p.is_file() or p.suffix not in TEXT_SUFFIX: continue
        txt=read_text(p,1_000_000)
        for m in re.finditer(r'(?i)(?:device|serial)=((?:\d{1,3}\.){3}\d{1,3}:\d{2,5})',txt): out.add(m.group(1))
    return out

INFRA_ENDPOINTS=infer_infra_endpoints(action_dir)|infer_infra_endpoints(baseline_dir)

def normalize(line):
    s=line.strip()
    if not s or s.startswith('@@T ') or INFRA_RE.search(s): return None
    if any(ep in s for ep in INFRA_ENDPOINTS): return None
    s=re.sub(r'^\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+\s+\d+\s+\d+\s+[VDIWEF]\s+','',s)
    s=re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+Z:-]\S*)?\s*','',s)
    s=re.sub(r'\b2026\d{4}_\d{6}\b','<SESSION>',s)
    s=re.sub(r'0x[0-9a-fA-F]+','<HEX>',s)
    s=re.sub(r'\b[0-9a-fA-F]{16,}\b','<HEXID>',s)
    s=re.sub(r'\b\d{10}\.\d{3}\b','<EPOCH>',s)
    # Reduce volatile counters while keeping common bundle/path IDs (typically <= 5 digits).
    s=re.sub(r'(?<![A-Za-z_./-])\d{6,}(?![A-Za-z_./-])','<N>',s)
    s=re.sub(r'\s+',' ',s).strip()
    return s if len(s)>=4 else None

def collect_streams(root):
    grouped=defaultdict(list); raw_examples=defaultdict(dict)
    for p in sorted(root.iterdir()):
        if not p.is_file(): continue
        if p.suffix not in TEXT_SUFFIX and not p.name.endswith('.log'): continue
        if p.name.startswith('snapshot-'): continue
        g=group_for(p.name)
        txt=read_text(p)
        if p.name.startswith(STREAM_PREFIX): txt=action_slice(txt)
        for line in txt.splitlines():
            n=normalize(line)
            if not n: continue
            grouped[g].append(n); raw_examples[g].setdefault(n,line[:1200])
    return grouped,raw_examples

def snapshot_delta(root):
    b=root/'snapshot-before.txt'; a=root/'snapshot-after.txt'
    if not b.exists() or not a.exists(): return Counter(),{}
    def lines(p):
        c=Counter(); ex={}
        for line in read_text(p).splitlines():
            n=normalize(line)
            if not n or GRAPHICS_NOISE_RE.search(n): continue
            # Snapshot evidence is useful only if it has target/network/file semantics.
            if not (ANCHOR_RE.search(n) or re.search(r'(?i)(ESTAB|LISTEN|/data/|/storage/|\.so\b)',n)): continue
            c[n]+=1; ex.setdefault(n,line[:1200])
        return c,ex
    bc,_=lines(b); ac,aex=lines(a)
    d=Counter({k:max(v-bc.get(k,0),0) for k,v in ac.items() if v-bc.get(k,0)>0})
    return d,aex

def add_records_for_group(g,ac,bc,examples,line_records,line_sources):
    for n,av in ac.items():
        d=max(av-bc.get(n,0),0)
        if d<=0: continue
        anchor=bool(ANCHOR_RE.search(n)); target=bool(TARGET_RE.search(n)); syscall=bool(SYSCALL_RE.search(n)); noise=bool(GRAPHICS_NOISE_RE.search(n))
        score=min(d,8)+(4 if target else 0)+(2 if anchor else 0)+(5 if syscall and g=='strace' else 0)-(6 if noise else 0)
        line_sources[n].add(g)
        line_records.append({'source':g,'text':n,'raw':examples.get(n,n),'delta':d,'actionCount':av,'baselineCount':bc.get(n,0),'anchor':anchor,'target':target,'syscall':syscall,'noise':noise,'score':score})

A,Aex=collect_streams(action_dir); B,Bex=collect_streams(baseline_dir)
all_groups=sorted(set(A)|set(B))
method_stats={}; line_records=[]; line_sources=defaultdict(set)
for g in all_groups:
    ac=Counter(A.get(g,[])); bc=Counter(B.get(g,[]))
    method_stats[g]={'actionLines':sum(ac.values()),'baselineLines':sum(bc.values()),'actionUnique':len(ac),'baselineUnique':len(bc)}
    add_records_for_group(g,ac,bc,Aex.get(g,{}),line_records,line_sources)

# Snapshots are compared as within-session AFTER-minus-BEFORE changes, then ACTION-minus-BASELINE.
asnap,aex=snapshot_delta(action_dir); bsnap,bex=snapshot_delta(baseline_dir)
method_stats['snapshots']={'actionLines':sum(asnap.values()),'baselineLines':sum(bsnap.values()),'actionUnique':len(asnap),'baselineUnique':len(bsnap)}
add_records_for_group('snapshots',asnap,bsnap,aex,line_records,line_sources)

for r in line_records:
    r['sourceCount']=len(line_sources[r['text']]); r['score']+=6*max(0,r['sourceCount']-1)
line_records=[r for r in line_records if not r['noise']]
line_records.sort(key=lambda r:(r['sourceCount'],r['target'],r['score'],r['delta']),reverse=True)

# Extract semantic tokens from the strict delta.
tokens=defaultdict(lambda:{'count':0,'sources':set(),'examples':[],'target':False,'straceConcrete':False,'contextScore':0})
for r in line_records:
    if not (r['anchor'] or r['target'] or (r['source']=='strace' and r['syscall'])): continue
    for rx in TOKEN_RES:
        for m in rx.finditer(r['text']):
            tok=m.group(0).strip(' ,;:()[]{}')
            if len(tok)<4 or INFRA_RE.search(tok) or tok in INFRA_ENDPOINTS: continue
            x=tokens[tok]; x['count']+=r['delta']; x['sources'].add(r['source']); x['target']=x['target'] or bool(TARGET_RE.search(tok)); x['contextScore']=max(x['contextScore'],r['score'])
            if r['source']=='strace' and r['syscall'] and CONCRETE_TOKEN_RE.search(tok): x['straceConcrete']=True
            if len(x['examples'])<4: x['examples'].append({'source':r['source'],'text':r['raw']})

ranked=[]
for tok,x in tokens.items():
    sc=len(x['sources']); concrete=bool(CONCRETE_TOKEN_RE.search(tok)); generic=bool(GENERIC_TOKEN_RE.match(tok))
    score=min(x['count'],8)+(6*max(0,sc-1))+(5 if concrete else 0)+(3 if x['target'] else 0)+(3 if x['straceConcrete'] else 0)
    # Strong = corroborated target/concrete signal OR a concrete syscall artefact from strace.
    strong=((sc>=2 and (concrete or x['target']) and score>=14) or (x['straceConcrete'] and concrete and score>=13))
    if generic and sc<2: strong=False
    confidence='FORTE' if strong else ('MOYENNE' if score>=9 and (x['target'] or concrete) else 'FAIBLE')
    ranked.append({'token':tok,'count':x['count'],'sources':sorted(x['sources']),'sourceCount':sc,'score':score,'confidence':confidence,'concrete':concrete,'examples':x['examples']})
ranked.sort(key=lambda z:(z['confidence']=='FORTE',z['sourceCount'],z['concrete'],z['score'],z['count']),reverse=True)

anchor_lines=[r for r in line_records if r['anchor']]
target_lines=[r for r in line_records if r['target']]
low_lines=[r for r in line_records if r['source']=='strace' and r['syscall']]
cross_lines=[r for r in line_records if r['sourceCount']>=2]
strong_tokens=[r for r in ranked if r['confidence']=='FORTE']
cross_tokens=[r for r in ranked if r['sourceCount']>=2]
medium_tokens=[r for r in ranked if r['confidence']=='MOYENNE']

if strong_tokens: verdict='DIFFERENTIAL_STRICT_STRONG'
elif cross_tokens or cross_lines: verdict='DIFFERENTIAL_STRICT_CROSS_SOURCE'
elif medium_tokens or target_lines: verdict='DIFFERENTIAL_STRICT_TARGET_SIGNALS'
elif anchor_lines: verdict='DIFFERENTIAL_STRICT_ANCHORS_ONLY'
elif line_records: verdict='DIFFERENTIAL_STRICT_RUNTIME_ONLY'
else: verdict='NO_MEASURABLE_DIFFERENCE'

result={
 'version':2,'actionSession':action_dir.name,'baselineSession':baseline_dir.name,'verdict':verdict,
 'methodStats':method_stats,'methodComparedCount':sum(1 for v in method_stats.values() if v['actionLines'] or v['baselineLines']),
 'deltaLineCount':len(line_records),'anchorLineCount':len(anchor_lines),'targetLineCount':len(target_lines),'lowLevelLineCount':len(low_lines),
 'crossLineCount':len(cross_lines),'candidateCount':len(ranked),'strongCount':len(strong_tokens),'crossTokenCount':len(cross_tokens),'mediumCount':len(medium_tokens),
 'strong':strong_tokens[:60],'crossTokens':cross_tokens[:100],'medium':medium_tokens[:120],'candidates':ranked[:220],
 'targetLines':target_lines[:220],'anchorLines':anchor_lines[:220],'lowLevelLines':low_lines[:160],'crossLines':cross_lines[:160],'topDelta':line_records[:260],
 'infraEndpoints':sorted(INFRA_ENDPOINTS)
}
(action_dir/'differential-v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
outfile.parent.mkdir(parents=True,exist_ok=True); outfile.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"OMNITRACE_DIFFERENTIAL_V2_READY action={action_dir.name} baseline={baseline_dir.name} methods={result['methodComparedCount']} delta={result['deltaLineCount']} anchors={result['anchorLineCount']} target={result['targetLineCount']} strong={result['strongCount']} cross={result['crossTokenCount']} medium={result['mediumCount']}")
print(f"VERDICT={verdict}")
