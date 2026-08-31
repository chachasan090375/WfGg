#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
RAW="$ROOT/frontend/lab/master-assets-v2/runtime-lua/raw/LWScripts.data"
META="$ROOT/frontend/lab/master-assets-v2/meta/lwscripts-lua-marker-context-v1.json"
VIEW="$ROOT/frontend/lab/formation-lua-trace-viewer-data/lwscripts-lua-marker-context.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LUA_MARKER_CONTEXT_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$RAW" ]] || fail "LWScripts.data absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$META")" "$(dirname "$VIEW")" "$(dirname "$REPORT")"
python - "$RAW" "$META" "$VIEW" "$REPORT" <<'PY'
from pathlib import Path
from collections import Counter
import json,statistics,struct,sys
raw,meta,view,report=map(Path,sys.argv[1:])
b=raw.read_bytes(); n=len(b); sig=b'\x1bLua'
offs=[]; p=0
while True:
    j=b.find(sig,p)
    if j<0:break
    offs.append(j);p=j+1

def topbytes(rel):
    c=Counter(b[o+rel] for o in offs if 0<=o+rel<n)
    return {'relative':rel,'unique':len(c),'top':[{'hex':f'{v:02x}','dec':v,'count':cnt,'pct':round(cnt*100/max(1,len(offs)),3)} for v,cnt in c.most_common(12)]}
post=[topbytes(r) for r in range(4,33)]
pre=[topbytes(r) for r in range(-12,0)]
patterns=Counter()
for o in offs:
    patterns[b[o+4:o+20].hex()]+=1
postPatterns=[{'hex':h,'count':c,'pct':round(c*100/max(1,len(offs)),3)} for h,c in patterns.most_common(24)]

# Standard-header families. 5.2 has its endian/size fields before LUAC_TAIL;
# 5.3/5.4 carry LUAC_DATA directly after version+format.
def classify(o):
    x=b[o:o+40]
    if len(x)<12:return 'SHORT'
    if x[:4]!=sig:return 'NO_MAGIC'
    ver=x[4];fmt=x[5]
    if fmt!=0:return f'VER_{ver:02x}_FMT_{fmt:02x}'
    if ver==0x51:
        # canonical Lua 5.1: endian,size_int,size_t,Instruction,lua_Number,integral
        if len(x)>=12 and x[6] in (0,1) and x[7] in (4,8) and x[8] in (4,8) and x[9] in (4,8) and x[10] in (4,8): return 'LUA51_PLAUSIBLE'
        return 'LUA51_CUSTOM_HEADER'
    if ver==0x52:
        # Lua 5.2 classic header has endianness/sizes before LUAC_TAIL.
        if len(x)>=18 and x[6] in (0,1) and x[7] in (4,8) and x[8] in (4,8) and x[9] in (4,8) and x[10] in (4,8) and x[12:18]==b'\x19\x93\r\n\x1a\n': return 'LUA52_CLASSIC'
        if x[6:12]==b'\x19\x93\r\n\x1a\n': return 'LUA52_TAIL_EARLY'
        return 'LUA52_CUSTOM_HEADER'
    if ver in (0x53,0x54):
        if x[6:12]==b'\x19\x93\r\n\x1a\n': return f'LUA{ver&0x0f}_STANDARD'
        return f'LUA{ver&0x0f}_CUSTOM_HEADER'
    return f'UNKNOWN_VERSION_{ver:02x}'
classes=Counter(classify(o) for o in offs)

# Position of LUAC tail near each marker.
tail=b'\x19\x93\r\n\x1a\n'; tailRel=Counter()
for o in offs:
    j=b.find(tail,o+4,min(n,o+80))
    tailRel[(j-o) if j>=0 else -1]+=1

# Framing candidates from bytes before magic, compared to gap to next marker.
frameStats=Counter(); frameSamples=[]
for i,o in enumerate(offs[:-1]):
    gap=offs[i+1]-o
    for width in (2,4,8):
        if o<width:continue
        rawp=b[o-width:o]
        for endian in ('little','big'):
            val=int.from_bytes(rawp,endian)
            delta=val-gap
            if abs(delta)<=64:
                key=f'{width*8}{"le" if endian=="little" else "be"}:delta={delta}'
                frameStats[key]+=1
                if len(frameSamples)<80:frameSamples.append({'offset':o,'gap':gap,'width':width,'endian':endian,'value':val,'delta':delta,'prefixHex':b[max(0,o-16):o].hex()})

# Context samples: first 12 + quantiles.
idxs=list(range(min(12,len(offs))))
if offs:
    for q in (0.1,0.25,0.5,0.75,0.9,0.99): idxs.append(min(len(offs)-1,int((len(offs)-1)*q)))
idxs=sorted(set(idxs))
samples=[]
for i in idxs:
    o=offs[i]; lo=max(0,o-32); hi=min(n,o+96); blob=b[lo:hi]
    asc=''.join(chr(x) if 32<=x<127 else '.' for x in blob)
    samples.append({'index':i,'offset':o,'class':classify(o),'beforeHex':b[max(0,o-32):o].hex(),'afterHex':b[o:o+64].hex(),'ascii':asc,'gapNext':(offs[i+1]-o if i+1<len(offs) else None)})

# Dominant interpretation.
verCounter=Counter(b[o+4] for o in offs if o+5<n)
fmtCounter=Counter(b[o+5] for o in offs if o+6<n)
domVer,domVerCount=verCounter.most_common(1)[0] if verCounter else (None,0)
domClass,domClassCount=classes.most_common(1)[0] if classes else ('NONE',0)
if domClass.startswith('LUA52_') and domClassCount>len(offs)*0.8:
    verdict='LUA52_HEADER_LAYOUT'
    hint='The previous validator was too strict for Lua 5.2. Update carving to accept the observed 5.2 layout and derive chunk boundaries.'
elif 'STANDARD' in domClass or domClass=='LUA51_PLAUSIBLE':
    verdict='STANDARD_LUA_HEADER_FAMILY'
    hint='Use the observed header family, not the previous generic validator, then carve chunks.'
elif domVerCount>len(offs)*0.8:
    verdict='CONSISTENT_CUSTOM_LUA_HEADER'
    hint='All markers share a stable version/header pattern. Derive the custom transformation/layout from the dominant bytes before carving.'
else:
    verdict='MIXED_MARKER_CONTEXTS'
    hint='Markers are heterogeneous; inspect context clusters and framing candidates before carving.'
res={'format':'WFGG_LASTWAR_LUA_MARKER_CONTEXT_V1','bytes':n,'markers':len(offs),'versionCounts':{f'{k:02x}':v for k,v in verCounter.items()},'formatCounts':{f'{k:02x}':v for k,v in fmtCounter.items()},'classes':dict(classes),'tailRelativeOffsets':{str(k):v for k,v in sorted(tailRel.items())},'postByteDistributions':post,'preByteDistributions':pre,'postPatterns':postPatterns,'frameMatches':dict(frameStats),'frameSamples':frameSamples,'samples':samples,'verdict':verdict,'nextHint':hint}
js=json.dumps(res,ensure_ascii=False,indent=2)+'\n';meta.write_text(js,'utf-8');view.write_text(js,'utf-8')
lines=['LUA_MARKER_CONTEXT_V1_READY',f'markers={len(offs)} verdict={verdict}',f'versions={dict(verCounter)} formats={dict(fmtCounter)}',f'classes={dict(classes)}',f'tailRel={dict(tailRel)}','--- TOP POST PATTERNS ---']
for x in postPatterns[:12]:lines.append(f"{x['count']} ({x['pct']}%) {x['hex']}")
lines.append('--- FRAME MATCHES ---')
for k,v in frameStats.most_common(20):lines.append(f'{k} -> {v}')
if not frameStats:lines.append('NONE')
lines.append('--- SAMPLES ---')
for s in samples[:20]:lines.append(f"idx={s['index']} off={s['offset']} class={s['class']} gap={s['gapNext']} after={s['afterHex'][:80]}")
lines+=['--- VERDICT ---',verdict,hint,f'JSON={meta}']
text='\n'.join(lines)+'\n';report.write_text(text,'utf-8');print(text,end='')
PY
