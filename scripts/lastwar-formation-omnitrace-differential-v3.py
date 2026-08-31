#!/usr/bin/env python3
import json, re, sys, time
from pathlib import Path
from collections import Counter, defaultdict

if len(sys.argv) < 4:
    print('Usage: lastwar-formation-omnitrace-differential-v3.py ACTION_DIR BASELINE_DIR OUTFILE', flush=True)
    raise SystemExit(2)

action_dir=Path(sys.argv[1]); baseline_dir=Path(sys.argv[2]); outfile=Path(sys.argv[3])
TEXT_SUFFIX={'.log','.txt','.err','.rc','.remote'}
STREAM_PREFIX=('logcat-pid','logcat-all','logcat-events','poller-runtime','poller-activity')

INFRA_RE=re.compile(r'(?i)(WFGG_|FORMATION_OMNITRACE|STRACE_DEPLOY_PROBE|wfgg-omnitrace|/data/local/tmp/wfgg-|lastwar-formation-omnitrace|ACTION_WINDOW_|REMOTE_STRACE|LOCAL_STRACE|DEPENDENCY_CLOSURE|PUSH_LIB|MISSING_REMOTE_DEP|adb\s+-s|FORMATION_STRACE_DEPLOY_PROBE|REMOTE_LD_LIBRARY_PATH|REMOTE_STRACE_|TERMUX DEPENDENC)')
GRAPHICS_NOISE_RE=re.compile(r'(?i)(ANGLE Warn|MemoryTracking\.cpp|RenderBufferStorageImage|ImplicitMultisampledRenderToTextureImage|SurfaceVK\.cpp|PopupWindow|ViewRootImpl|ThreadedRenderer|Choreographer|BufferQueue|BLASTBufferQueue)')
TARGET_RE=re.compile(r'(?i)(formationrt|uiheropvpformationpanel|a_hero_[a-z0-9_]+|murphy|audie|gamers_|assetbundle|loadasset|instantiate|prefab|\.bundle\b|\.ab\b|lwscripts|xlua|lua)')
ANCHOR_RE=re.compile(r'(?i)(formation|uihero|hero|murphy|audie|assetbundle|loadasset|instantiate|prefab|bundle|gamers_|xlua|lua|formationrt|rawimage|rendertexture|rpc|protobuf|message|socket|connect\(|sendto\(|recvfrom\(|openat\(|\.bundle\b|\.ab\b)')
SYSCALL_RE=re.compile(r'(?i)\b(openat|open|connect|sendto|recvfrom|sendmsg|recvmsg|read|pread64|mmap)\(')
IPPORT_RE=re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b')
PATHISH_RE=re.compile(r'(?i)(/data/|/storage/|/sdcard/|\.bundle\b|\.ab\b|\.asset\b|\.bytes\b|\.data\b|gamers_|lwscripts)')
CONCRETE_TOKEN_RE=re.compile(r'(?i)(^A_Hero_|^UIHeroPVPFormationPanel$|^FormationRT$|^gamers_|\.bundle$|\.ab$|/.*(?:asset|bundle|gamers_|hero|formation|lwscripts)|\bMurphy\b|\bAudie\b)')
GENERIC_TOKEN_RE=re.compile(r'(?i)^(LoadAsset|Instantiate|AssetBundle|Formation|Hero|Lua|XLua)$')

TOKEN_RES=[
 re.compile(r'\bA_Hero_[A-Za-z0-9_]+\b'),
 re.compile(r'\bUIHero[A-Za-z0-9_]+\b'),
 re.compile(r'\bFormation[A-Za-z0-9_]*\b'),
 re.compile(r'\b(?:gamers_[A-Za-z0-9_./-]+)\b'),
 re.compile(r'(?i)\b(?:Murphy|Audie)\b'),
 re.compile(r'(?i)(?:/[^\s\"\'<>]+(?:\.bundle|\.ab|\.asset|\.bytes|\.data|\.txt|\.json))'),
 IPPORT_RE,
 re.compile(r'\b(?:LoadAsset|Instantiate|AssetBundle|FormationRT|UIHeroPVPFormationPanel|LWScripts(?:\.data|\.txt)?)\b'),
]

CHEAP_WORDS=('formation','uihero','hero','murphy','audie','asset','bundle','gamers_','xlua','lua','rpc','protobuf','message','socket','connect','sendto','recvfrom','sendmsg','recvmsg','openat','/data/','/storage/','/sdcard/','lwscripts')

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

def infer_infra_endpoints(root):
    out=set()
    for p in root.iterdir():
        if not p.is_file() or p.suffix not in TEXT_SUFFIX: continue
        try:
            with p.open('r',encoding='utf-8',errors='replace') as f:
                for _ in range(5000):
                    line=f.readline()
                    if not line: break
                    for m in re.finditer(r'(?i)(?:device|serial)=((?:\d{1,3}\.){3}\d{1,3}:\d{2,5})',line): out.add(m.group(1))
        except Exception: pass
    return out

INFRA_ENDPOINTS=infer_infra_endpoints(action_dir)|infer_infra_endpoints(baseline_dir)

def normalize(s):
    s=s.strip()
    if not s or s.startswith('@@T ') or INFRA_RE.search(s): return None
    if any(ep in s for ep in INFRA_ENDPOINTS): return None
    if GRAPHICS_NOISE_RE.search(s): return None
    s=re.sub(r'^\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+\s+\d+\s+\d+\s+[VDIWEF]\s+','',s)
    s=re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+Z:-]\S*)?\s*','',s)
    s=re.sub(r'\b2026\d{4}_\d{6}\b','<SESSION>',s)
    s=re.sub(r'0x[0-9a-fA-F]+','<HEX>',s)
    s=re.sub(r'\b[0-9a-fA-F]{16,}\b','<HEXID>',s)
    s=re.sub(r'\b\d{10}\.\d{3}\b','<EPOCH>',s)
    s=re.sub(r'(?<![A-Za-z_./-])\d{6,}(?![A-Za-z_./-])','<N>',s)
    s=re.sub(r'\s+',' ',s).strip()
    return s if len(s)>=4 else None

def cheap_keep(line, group):
    lo=line.lower()
    if group=='strace':
        return any(x in lo for x in ('openat(','connect(','sendto(','recvfrom(','sendmsg(','recvmsg(','mmap(','bundle','asset','hero','formation','gamers_','lwscripts'))
    if group=='procNetwork':
        return any(x in lo for x in ('tcp','udp','estab','listen','socket','connect','send','recv','com.fun.lastwar','formation','hero','bundle','asset')) or bool(IPPORT_RE.search(line))
    if group=='activity':
        return 'com.fun.lastwar' in lo or 'formation' in lo or 'hero' in lo
    return any(w in lo for w in CHEAP_WORDS) or bool(IPPORT_RE.search(line))

def iter_action_lines(p):
    stream=p.name.startswith(STREAM_PREFIX)
    inside=not stream
    saw_marker=False
    try:
        with p.open('r',encoding='utf-8',errors='replace') as f:
            for line in f:
                if stream and line.startswith('@@ACTION_WINDOW_START '): inside=True; saw_marker=True; continue
                if stream and line.startswith('@@ACTION_WINDOW_STOP '):
                    if saw_marker: break
                    continue
                if inside: yield line
    except Exception: return

def collect(root,label):
    grouped=defaultdict(Counter); examples=defaultdict(dict); stats=defaultdict(lambda:{'scanned':0,'kept':0})
    files=[p for p in sorted(root.iterdir()) if p.is_file() and not p.name.startswith('snapshot-') and (p.suffix in TEXT_SUFFIX or p.name.endswith('.log'))]
    for idx,p in enumerate(files,1):
        g=group_for(p.name)
        if g=='other' and p.stat().st_size>2_000_000: continue
        before=time.time(); kept=0; scanned=0
        for line in iter_action_lines(p):
            scanned+=1
            if not cheap_keep(line,g): continue
            n=normalize(line)
            if not n: continue
            grouped[g][n]+=1; examples[g].setdefault(n,line[:1200]); kept+=1
        stats[g]['scanned']+=scanned; stats[g]['kept']+=kept
        print(f'[{label}] {idx}/{len(files)} {p.name} group={g} scanned={scanned} kept={kept} {time.time()-before:.1f}s',flush=True)
    return grouped,examples,stats

def snapshot_delta(root,label):
    b=root/'snapshot-before.txt'; a=root/'snapshot-after.txt'
    if not b.exists() or not a.exists(): return Counter(),{}
    def filt(p):
        c=Counter(); ex={}; scanned=0
        try:
            with p.open('r',encoding='utf-8',errors='replace') as f:
                for line in f:
                    scanned+=1
                    lo=line.lower()
                    if not (any(w in lo for w in CHEAP_WORDS) or 'estab' in lo or 'listen' in lo or '/data/' in lo or '.so' in lo or IPPORT_RE.search(line)): continue
                    n=normalize(line)
                    if not n: continue
                    c[n]+=1; ex.setdefault(n,line[:1200])
        except Exception: pass
        return c,ex,scanned
    bc,_,bs=filt(b); ac,aex,as_=filt(a)
    d=Counter({k:v-bc.get(k,0) for k,v in ac.items() if v>bc.get(k,0)})
    print(f'[{label}] snapshots before_scanned={bs} after_scanned={as_} delta={len(d)}',flush=True)
    return d,aex

print('OMNITRACE_DIFF_V3_PHASE=COLLECT_ACTION',flush=True)
A,Aex,Astats=collect(action_dir,'ACTION')
print('OMNITRACE_DIFF_V3_PHASE=COLLECT_BASELINE',flush=True)
B,Bex,Bstats=collect(baseline_dir,'BASELINE')

line_records=[]; line_sources=defaultdict(set); method_stats={}
all_groups=sorted(set(A)|set(B))
for g in all_groups:
    ac=A.get(g,Counter()); bc=B.get(g,Counter())
    method_stats[g]={'actionLines':sum(ac.values()),'baselineLines':sum(bc.values()),'actionUnique':len(ac),'baselineUnique':len(bc),'actionScanned':Astats[g]['scanned'],'baselineScanned':Bstats[g]['scanned']}
    for n,av in ac.items():
        d=av-bc.get(n,0)
        if d<=0: continue
        anchor=bool(ANCHOR_RE.search(n)); target=bool(TARGET_RE.search(n)); syscall=bool(SYSCALL_RE.search(n));
        score=min(d,8)+(5 if target else 0)+(2 if anchor else 0)+(6 if syscall and g=='strace' else 0)
        line_sources[n].add(g)
        line_records.append({'source':g,'text':n,'raw':Aex[g].get(n,n),'delta':d,'actionCount':av,'baselineCount':bc.get(n,0),'anchor':anchor,'target':target,'syscall':syscall,'noise':False,'score':score})

asnap,aex=snapshot_delta(action_dir,'ACTION'); bsnap,bex=snapshot_delta(baseline_dir,'BASELINE')
method_stats['snapshots']={'actionLines':sum(asnap.values()),'baselineLines':sum(bsnap.values()),'actionUnique':len(asnap),'baselineUnique':len(bsnap)}
for n,av in asnap.items():
    d=av-bsnap.get(n,0)
    if d<=0: continue
    anchor=bool(ANCHOR_RE.search(n)); target=bool(TARGET_RE.search(n));
    score=min(d,8)+(5 if target else 0)+(2 if anchor else 0)
    line_sources[n].add('snapshots')
    line_records.append({'source':'snapshots','text':n,'raw':aex.get(n,n),'delta':d,'actionCount':av,'baselineCount':bsnap.get(n,0),'anchor':anchor,'target':target,'syscall':False,'noise':False,'score':score})

for r in line_records:
    r['sourceCount']=len(line_sources[r['text']]); r['score']+=7*max(0,r['sourceCount']-1)
line_records.sort(key=lambda r:(r['sourceCount'],r['target'],r['score'],r['delta']),reverse=True)
print(f'OMNITRACE_DIFF_V3_PHASE=TOKENIZE delta_lines={len(line_records)}',flush=True)

tokens=defaultdict(lambda:{'count':0,'sources':set(),'examples':[],'target':False,'straceConcrete':False})
for r in line_records:
    if not (r['anchor'] or r['target'] or (r['source']=='strace' and r['syscall'])): continue
    for rx in TOKEN_RES:
        for m in rx.finditer(r['text']):
            tok=m.group(0).strip(' ,;:()[]{}')
            if len(tok)<4 or INFRA_RE.search(tok) or tok in INFRA_ENDPOINTS: continue
            x=tokens[tok]; x['count']+=r['delta']; x['sources'].add(r['source']); x['target']=x['target'] or bool(TARGET_RE.search(tok))
            if r['source']=='strace' and r['syscall'] and CONCRETE_TOKEN_RE.search(tok): x['straceConcrete']=True
            if len(x['examples'])<4: x['examples'].append({'source':r['source'],'text':r['raw']})

ranked=[]
for tok,x in tokens.items():
    sc=len(x['sources']); concrete=bool(CONCRETE_TOKEN_RE.search(tok)); generic=bool(GENERIC_TOKEN_RE.match(tok))
    score=min(x['count'],8)+(7*max(0,sc-1))+(6 if concrete else 0)+(3 if x['target'] else 0)+(4 if x['straceConcrete'] else 0)
    strong=((sc>=2 and (concrete or x['target']) and score>=15) or (x['straceConcrete'] and concrete and score>=14))
    if generic and sc<2: strong=False
    confidence='FORTE' if strong else ('MOYENNE' if score>=10 and (x['target'] or concrete) else 'FAIBLE')
    ranked.append({'token':tok,'count':x['count'],'sources':sorted(x['sources']),'sourceCount':sc,'score':score,'confidence':confidence,'concrete':concrete,'examples':x['examples']})
ranked.sort(key=lambda z:(z['confidence']=='FORTE',z['sourceCount'],z['concrete'],z['score'],z['count']),reverse=True)

anchor_lines=[r for r in line_records if r['anchor']]
target_lines=[r for r in line_records if r['target']]
low_lines=[r for r in line_records if r['source']=='strace' and r['syscall']]
cross_lines=[r for r in line_records if r['sourceCount']>=2]
strong_tokens=[r for r in ranked if r['confidence']=='FORTE']
cross_tokens=[r for r in ranked if r['sourceCount']>=2]
medium_tokens=[r for r in ranked if r['confidence']=='MOYENNE']

if strong_tokens: verdict='DIFFERENTIAL_V3_STRONG'
elif cross_tokens or cross_lines: verdict='DIFFERENTIAL_V3_CROSS_SOURCE'
elif medium_tokens or target_lines: verdict='DIFFERENTIAL_V3_TARGET_SIGNALS'
elif anchor_lines: verdict='DIFFERENTIAL_V3_ANCHORS_ONLY'
elif line_records: verdict='DIFFERENTIAL_V3_RUNTIME_ONLY'
else: verdict='NO_MEASURABLE_DIFFERENCE'

result={'version':3,'actionSession':action_dir.name,'baselineSession':baseline_dir.name,'verdict':verdict,'methodStats':method_stats,
'methodComparedCount':sum(1 for v in method_stats.values() if v['actionLines'] or v['baselineLines']),
'deltaLineCount':len(line_records),'anchorLineCount':len(anchor_lines),'targetLineCount':len(target_lines),'lowLevelLineCount':len(low_lines),
'crossLineCount':len(cross_lines),'candidateCount':len(ranked),'strongCount':len(strong_tokens),'crossTokenCount':len(cross_tokens),'mediumCount':len(medium_tokens),
'strong':strong_tokens[:60],'crossTokens':cross_tokens[:100],'medium':medium_tokens[:120],'candidates':ranked[:220],
'targetLines':target_lines[:220],'anchorLines':anchor_lines[:220],'lowLevelLines':low_lines[:160],'crossLines':cross_lines[:160],'topDelta':line_records[:260],
'infraEndpoints':sorted(INFRA_ENDPOINTS)}
(action_dir/'differential-v3.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
outfile.parent.mkdir(parents=True,exist_ok=True); outfile.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"OMNITRACE_DIFFERENTIAL_V3_READY action={action_dir.name} baseline={baseline_dir.name} methods={result['methodComparedCount']} delta={result['deltaLineCount']} anchors={result['anchorLineCount']} target={result['targetLineCount']} strong={result['strongCount']} cross={result['crossTokenCount']} medium={result['mediumCount']}",flush=True)
print(f'VERDICT={verdict}',flush=True)
