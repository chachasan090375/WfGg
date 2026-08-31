#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BUNDLE="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles/bundle-6933.bundle"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-rt-trace-v1.json"
UNITY_VERSION="2019.4.41f1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$BUNDLE" ]] || fail "bundle 6933 absent: $BUNDLE"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")"
PYTHONUNBUFFERED=1 python - "$BUNDLE" "$OUT" "$UNITY_VERSION" <<'PY'
import json,sys,re
from pathlib import Path
import UnityPy
bundle=Path(sys.argv[1]); out=Path(sys.argv[2]); version=sys.argv[3]
UnityPy.config.FALLBACK_UNITY_VERSION=version
env=UnityPy.load(str(bundle))
objs=list(getattr(env,'objects',[]) or [])

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def sf(o): return str(getattr(getattr(o,'assets_file',None),'name','') or '')
def name(o):
    try:return str(o.peek_name() or '')
    except:return ''
def tree(o):
    try:return o.read_typetree()
    except Exception as e:return {'__typetree_error__':f'{type(e).__name__}:{e}'}

def collect_ptrs(v,prefix='$'):
    out=[]
    def rec(x,path):
        if isinstance(x,dict):
            fk=next((k for k in ('m_FileID','fileID','fileId','m_FileId') if k in x),None)
            pk=next((k for k in ('m_PathID','pathID','pathId','m_PathId') if k in x),None)
            if fk is not None and pk is not None:
                try: out.append({'path':path,'fileID':int(x[fk]),'pathID':int(x[pk])})
                except Exception: pass
            for k,y in x.items(): rec(y,f'{path}.{k}')
        elif isinstance(x,(list,tuple)):
            for i,y in enumerate(x): rec(y,f'{path}[{i}]')
    rec(v,prefix); return out

by_pid={pid(o):o for o in objs}
formation=[o for o in objs if name(o).lower()=='formationrt']
if not formation:
    raise SystemExit('FORMATIONRT_NOT_FOUND')
f=formation[0]; fpid=pid(f); fsf=sf(f); ftree=tree(f); fptrs=collect_ptrs(ftree)

def resolve(ptr,source_obj=None):
    r={'fileID':ptr['fileID'],'pathID':ptr['pathID']}
    if ptr['fileID']==0 and ptr['pathID'] in by_pid:
        t=by_pid[ptr['pathID']]
        r.update({'resolved':True,'type':typ(t),'name':name(t),'serializedFile':sf(t)})
    else:
        r['resolved']=False
        if source_obj is not None and ptr['fileID']>0:
            try:
                exts=list(getattr(getattr(source_obj,'assets_file',None),'externals',[]) or [])
                if ptr['fileID']-1 < len(exts):
                    ex=exts[ptr['fileID']-1]
                    r['externalPath']=str(getattr(ex,'path','') or getattr(ex,'name','') or ex)
            except Exception: pass
    return r

components=[]
for p in fptrs:
    rr=resolve(p,f); rr['fieldPath']=p['path']; components.append(rr)

component_details=[]
seen=set()
for c in components:
    if not c.get('resolved') or c['pathID'] in seen: continue
    seen.add(c['pathID']); o=by_pid[c['pathID']]; ot=tree(o); ptrs=collect_ptrs(ot)
    component_details.append({
        'pathID':pid(o),'type':typ(o),'name':name(o),'serializedFile':sf(o),
        'pointers':[dict(resolve(p,o),fieldPath=p['path']) for p in ptrs],
        'typetree':ot
    })

referrers=[]
for i,o in enumerate(objs,1):
    if pid(o)==fpid: continue
    ot=tree(o)
    hits=[]
    for p in collect_ptrs(ot):
        if p['fileID']==0 and p['pathID']==fpid: hits.append(p['path'])
    if hits:
        referrers.append({'pathID':pid(o),'type':typ(o),'name':name(o),'serializedFile':sf(o),'fields':hits,'ptrCount':len(collect_ptrs(ot))})

keywords=['formationrt','formationcontent','uiheropvpformationpanel','rawimage','rendertexture','camera','hero']
matches=[]
for o in objs:
    hay=f'{typ(o)} {name(o)}'.lower()
    ks=[k for k in keywords if k in hay]
    if ks:
        matches.append({'pathID':pid(o),'type':typ(o),'name':name(o),'serializedFile':sf(o),'keywords':ks,'ptrCount':len(collect_ptrs(tree(o)))})

report={
 'format':'WFGG_LASTWAR_FORMATION_RT_TRACE_V1',
 'bundleId':6933,
 'formationRT':{'pathID':fpid,'type':typ(f),'name':name(f),'serializedFile':fsf,'ptrCount':len(fptrs),'components':components},
 'componentDetails':component_details,
 'referrers':referrers,
 'keywordMatches':matches,
 'objectCount':len(objs),
 'guardrails':{'labOnly':True,'mainUntouched':True,'actualGameAssetsOnly':True}
}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_RT_TRACE_V1_READY')
print(f'FormationRT pathID={fpid} serializedFile={fsf} ptrs={len(fptrs)}')
print('--- COMPONENT POINTERS ---')
for c in components:
    print(f"{c['fieldPath']} -> fileID={c['fileID']} pathID={c['pathID']} resolved={c.get('resolved')} type={c.get('type','?')} name={c.get('name','?')} external={c.get('externalPath','')}")
print('--- COMPONENT DETAILS ---')
for d in component_details:
    print(f"component pathID={d['pathID']} type={d['type']} name={d['name'] or '—'} ptrs={len(d['pointers'])}")
    for p in d['pointers']:
        print(f"  {p['fieldPath']} -> fileID={p['fileID']} pathID={p['pathID']} resolved={p.get('resolved')} type={p.get('type','?')} name={p.get('name','?')} external={p.get('externalPath','')}")
print('--- REFERRERS TO FormationRT ---')
if referrers:
    for r in referrers: print(f"{r['type']} {r['name'] or '—'} pathID={r['pathID']} fields={','.join(r['fields'])}")
else: print('NONE')
print('--- KEYWORD MATCHES (compact) ---')
for m in matches[:120]: print(f"{','.join(m['keywords'])}: {m['type']} {m['name'] or '—'} pathID={m['pathID']} ptrs={m['ptrCount']}")
print(f'JSON={out}')
PY
