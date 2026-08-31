#!/usr/bin/env python3
import json, re, sys
from pathlib import Path
from collections import Counter, defaultdict

if len(sys.argv) < 4:
    print('Usage: lastwar-formation-omnitrace-differential-v1.py ACTION_DIR BASELINE_DIR OUTFILE')
    raise SystemExit(2)

action_dir=Path(sys.argv[1]); baseline_dir=Path(sys.argv[2]); outfile=Path(sys.argv[3])

TEXT_SUFFIX={'.log','.txt','.err','.rc','.remote'}
INFRA_RE=re.compile(r'(?i)(WFGG_|FORMATION_OMNITRACE|STRACE_DEPLOY_PROBE|wfgg-omnitrace|/data/local/tmp/wfgg-|lastwar-formation-omnitrace|ACTION_WINDOW_|REMOTE_STRACE|LOCAL_STRACE|DEPENDENCY_CLOSURE|PUSH_LIB|MISSING_REMOTE_DEP|adb\s+-s|device=\d{1,3}(?:\.\d{1,3}){3}:\d+)')
GRAPHICS_NOISE_RE=re.compile(r'(?i)(ANGLE Warn|MemoryTracking\.cpp|RenderBufferStorageImage|ImplicitMultisampledRenderToTextureImage|SurfaceVK\.cpp|PopupWindow|ViewRootImpl|ThreadedRenderer)')
ANCHOR_RE=re.compile(r'(?i)(formation|uihero|hero|murphy|audie|assetbundle|loadasset|instantiate|prefab|bundle|gamers_|xlua|lua|formationrt|rawimage|rendertexture|rpc|protobuf|message|socket|connect\(|sendto\(|recvfrom\(|openat\(|\.bundle\b|\.ab\b)')
LOW_RE=re.compile(r'(?i)(openat\(|connect\(|sendto\(|recvfrom\(|sendmsg\(|recvmsg\(|assetbundle|loadasset|instantiate|\.bundle\b|gamers_|formationrt|uiheropvpformationpanel|a_hero_)')

TOKEN_RES=[
 re.compile(r'\bA_Hero_[A-Za-z0-9_]+\b'),
 re.compile(r'\bUIHero[A-Za-z0-9_]+\b'),
 re.compile(r'\bFormation[A-Za-z0-9_]*\b'),
 re.compile(r'\b(?:gamers_[A-Za-z0-9_./-]+)\b'),
 re.compile(r'(?i)\b(?:Murphy|Audie)\b'),
 re.compile(r'(?i)(?:/[^\s\"\'<>]+(?:\.bundle|\.ab|\.asset|\.bytes|\.data|\.txt|\.json))'),
 re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b'),
 re.compile(r'\b(?:LoadAsset|Instantiate|AssetBundle|FormationRT|UIHeroPVPFormationPanel)\b'),
]

def read_text(p,limit=16_000_000):
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

def normalize(line):
    s=line.strip()
    if not s or INFRA_RE.search(s): return None
    # Remove common logcat/threadtime prefixes while keeping the actual event text.
    s=re.sub(r'^\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+\s+\d+\s+\d+\s+[VDIWEF]\s+','',s)
    s=re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+Z:-]*\s*','',s)
    s=re.sub(r'\b2026\d{4}_\d{6}\b','<SESSION>',s)
    s=re.sub(r'0x[0-9a-fA-F]+','<HEX>',s)
    s=re.sub(r'\b\d{10}\.\d{3}\b','<EPOCH>',s)
    # Normalize whitespace only. Preserve IDs/bundle numbers because they may be meaningful.
    s=re.sub(r'\s+',' ',s).strip()
    return s if len(s)>=4 else None

def collect(root):
    grouped=defaultdict(list); raw_examples=defaultdict(dict)
    for p in sorted(root.iterdir()):
        if not p.is_file(): continue
        if p.suffix not in TEXT_SUFFIX and not p.name.endswith('.log'): continue
        g=group_for(p.name)
        txt=read_text(p)
        for line in txt.splitlines():
            n=normalize(line)
            if not n: continue
            grouped[g].append(n)
            raw_examples[g].setdefault(n,line[:1000])
    return grouped,raw_examples

action,action_examples=collect(action_dir); baseline,baseline_examples=collect(baseline_dir)
all_groups=sorted(set(action)|set(baseline))
method_stats={}
line_records=[]
line_sources=defaultdict(set)
line_delta_total=Counter()

for g in all_groups:
    ac=Counter(action.get(g,[])); bc=Counter(baseline.get(g,[]))
    excess={k:max(v-bc.get(k,0),0) for k,v in ac.items()}
    excess={k:v for k,v in excess.items() if v>0}
    method_stats[g]={
        'actionLines':sum(ac.values()),'baselineLines':sum(bc.values()),
        'actionUnique':len(ac),'baselineUnique':len(bc),'excessUnique':len(excess),
        'excessOccurrences':sum(excess.values())}
    for n,d in excess.items():
        line_sources[n].add(g); line_delta_total[n]+=d
        anchor=bool(ANCHOR_RE.search(n)); low=bool(LOW_RE.search(n)); noise=bool(GRAPHICS_NOISE_RE.search(n))
        score=min(d,12)+(7 if low else 0)+(4 if anchor else 0)-(4 if noise else 0)
        line_records.append({'source':g,'text':n,'raw':action_examples[g].get(n,n),'delta':d,'actionCount':ac[n],'baselineCount':bc.get(n,0),'anchor':anchor,'lowLevel':low,'noise':noise,'score':score})

# Add cross-source bonus for the exact normalized line.
for r in line_records:
    r['sourceCount']=len(line_sources[r['text']])
    r['score'] += 5*max(0,r['sourceCount']-1)
line_records.sort(key=lambda r:(r['sourceCount'],r['score'],r['delta']),reverse=True)

# Extract semantic tokens only from ACTION-minus-baseline lines.
tokens=defaultdict(lambda:{'count':0,'sources':set(),'examples':[],'low':False,'anchor':False})
for r in line_records:
    if r['noise']: continue
    for rx in TOKEN_RES:
        for m in rx.finditer(r['text']):
            tok=m.group(0).strip(' ,;:()[]{}')
            if len(tok)<4 or INFRA_RE.search(tok): continue
            x=tokens[tok]; x['count']+=r['delta']; x['sources'].add(r['source']); x['low']=x['low'] or r['lowLevel']; x['anchor']=True
            if len(x['examples'])<4: x['examples'].append({'source':r['source'],'text':r['raw']})

ranked=[]
for tok,x in tokens.items():
    sc=len(x['sources']); score=min(x['count'],12)+(7 if x['low'] else 0)+4+(6*max(0,sc-1))
    if re.search(r'(?i)(A_Hero_|FormationRT|UIHeroPVPFormationPanel|\.bundle$|gamers_)',tok): score+=6
    confidence='FORTE' if (sc>=2 and score>=14) or (x['low'] and score>=14) else ('MOYENNE' if score>=8 else 'FAIBLE')
    ranked.append({'token':tok,'count':x['count'],'sources':sorted(x['sources']),'sourceCount':sc,'score':score,'confidence':confidence,'examples':x['examples']})
ranked.sort(key=lambda z:(z['confidence']=='FORTE',z['sourceCount'],z['score'],z['count']),reverse=True)

anchor_lines=[r for r in line_records if r['anchor'] and not r['noise']]
low_lines=[r for r in line_records if r['lowLevel'] and not r['noise']]
cross_lines=[r for r in line_records if r['sourceCount']>=2 and not r['noise']]
strong_tokens=[r for r in ranked if r['confidence']=='FORTE']
cross_tokens=[r for r in ranked if r['sourceCount']>=2]

if strong_tokens or (low_lines and cross_lines): verdict='DIFFERENTIAL_STRONG_SIGNAL'
elif cross_tokens or cross_lines: verdict='DIFFERENTIAL_CROSS_SOURCE'
elif anchor_lines: verdict='DIFFERENTIAL_ANCHOR_SIGNALS'
elif line_records: verdict='DIFFERENTIAL_RUNTIME_DELTA_ONLY'
else: verdict='NO_MEASURABLE_DIFFERENCE'

result={
 'version':1,'actionSession':action_dir.name,'baselineSession':baseline_dir.name,
 'verdict':verdict,'methodStats':method_stats,
 'methodComparedCount':sum(1 for v in method_stats.values() if v['actionLines'] or v['baselineLines']),
 'deltaLineCount':len(line_records),'anchorLineCount':len(anchor_lines),'lowLevelLineCount':len(low_lines),
 'crossLineCount':len(cross_lines),'candidateCount':len(ranked),'strongCount':len(strong_tokens),'crossTokenCount':len(cross_tokens),
 'strong':strong_tokens[:80],'crossTokens':cross_tokens[:120],'candidates':ranked[:250],
 'anchorLines':anchor_lines[:250],'lowLevelLines':low_lines[:200],'crossLines':cross_lines[:200],
 'topDelta':line_records[:350],
}
(action_dir/'differential-v1.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
outfile.parent.mkdir(parents=True,exist_ok=True); outfile.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"OMNITRACE_DIFFERENTIAL_V1_READY action={action_dir.name} baseline={baseline_dir.name} methods={result['methodComparedCount']} delta={result['deltaLineCount']} anchors={result['anchorLineCount']} low={result['lowLevelLineCount']} crossLines={result['crossLineCount']} strong={result['strongCount']}")
print(f"VERDICT={verdict}")
