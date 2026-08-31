#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BUNDLE="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles/bundle-6933.bundle"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-rt-owner-trace-v1.json"
UNITY_VERSION="2019.4.41f1"
REFERRER_PID=-3755011431292375246
PANEL_GO_PID=869585497998244933
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$BUNDLE" ]] || fail "bundle 6933 absent: $BUNDLE"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")"
PYTHONUNBUFFERED=1 python - "$BUNDLE" "$OUT" "$UNITY_VERSION" "$REFERRER_PID" "$PANEL_GO_PID" <<'PY'
import json,sys
from pathlib import Path
import UnityPy
bundle=Path(sys.argv[1]); out=Path(sys.argv[2]); version=sys.argv[3]; refpid=int(sys.argv[4]); panelpid=int(sys.argv[5])
UnityPy.config.FALLBACK_UNITY_VERSION=version
env=UnityPy.load(str(bundle)); objs=list(getattr(env,'objects',[]) or [])

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def sf(o): return str(getattr(getattr(o,'assets_file',None),'name','') or '')
def name(o):
    try:return str(o.peek_name() or '')
    except:return ''
def tree(o):
    try:return o.read_typetree()
    except Exception as e:return {'__typetree_error__':f'{type(e).__name__}:{e}'}
def ptrs(v,prefix='$'):
    z=[]
    def rec(x,p):
        if isinstance(x,dict):
            fk=next((k for k in ('m_FileID','fileID','fileId','m_FileId') if k in x),None)
            pk=next((k for k in ('m_PathID','pathID','pathId','m_PathId') if k in x),None)
            if fk is not None and pk is not None:
                try:z.append({'field':p,'fileID':int(x[fk]),'pathID':int(x[pk])})
                except:pass
            for k,y in x.items():rec(y,f'{p}.{k}')
        elif isinstance(x,(list,tuple)):
            for i,y in enumerate(x):rec(y,f'{p}[{i}]')
    rec(v,prefix); return z

def scalars(v,prefix='$'):
    z=[]
    def rec(x,p):
        if isinstance(x,dict):
            for k,y in x.items():rec(y,f'{p}.{k}')
        elif isinstance(x,(list,tuple)):
            for i,y in enumerate(x):rec(y,f'{p}[{i}]')
        elif isinstance(x,(str,int,float,bool)) and x not in ('',0,False): z.append({'field':p,'value':x})
    rec(v,prefix); return z

by={pid(o):o for o in objs}
def resolve(p,src=None):
    r=dict(p)
    if p['fileID']==0 and p['pathID'] in by:
        o=by[p['pathID']]; r.update(resolved=True,type=typ(o),name=name(o),serializedFile=sf(o))
        if typ(o)=='MonoScript': r['scriptName']=name(o)
    else:
        r['resolved']=False
        if src is not None and p['fileID']>0:
            try:
                exts=list(getattr(getattr(src,'assets_file',None),'externals',[]) or [])
                if p['fileID']-1 < len(exts):
                    ex=exts[p['fileID']-1]; r['externalPath']=str(getattr(ex,'path','') or getattr(ex,'name','') or ex)
            except:pass
    return r

def describe(o):
    t=tree(o); pp=[resolve(p,o) for p in ptrs(t)]
    script=next((p for p in pp if p['field'].endswith('.m_Script') and p.get('resolved')),None)
    go=next((p for p in pp if p['field'].endswith('.m_GameObject') and p.get('resolved')),None)
    ss=[x for x in scalars(t) if any(k in x['field'].lower() for k in ('formation','render','camera','hero','model','mirror','asset','prefab','texture','raw','ui')) or (isinstance(x['value'],str) and any(k in x['value'].lower() for k in ('formation','render','camera','hero','model','mirror','asset','prefab','texture','raw','ui')))]
    return {'pathID':pid(o),'type':typ(o),'name':name(o),'serializedFile':sf(o),'script':script,'gameObject':go,'pointers':pp,'interestingScalars':ss[:250]}

def components_of_go(go):
    t=tree(go); outc=[]
    for p in ptrs(t):
        if '.m_Component[' in p['field'] and p['field'].endswith('.component'):
            rr=resolve(p,go)
            if rr.get('resolved'):
                co=by[rr['pathID']]; d=describe(co); outc.append(d)
    return outc

def parent_chain(go,maxn=10):
    chain=[]; cur=go
    for _ in range(maxn):
        chain.append({'pathID':pid(cur),'name':name(cur),'components':[{'pathID':c['pathID'],'type':c['type'],'script':(c.get('script') or {}).get('name','')} for c in components_of_go(cur)]})
        tr=next((c for c in components_of_go(cur) if c['type']=='RectTransform'),None)
        if not tr: break
        father=next((p for p in tr['pointers'] if p['field'].endswith('.m_Father') and p.get('resolved')),None)
        if not father: break
        fobj=by.get(father['pathID'])
        if not fobj or typ(fobj)!='RectTransform': break
        fdesc=describe(fobj); gop=fdesc.get('gameObject')
        if not gop or not gop.get('resolved'): break
        cur=by[gop['pathID']]
    return chain

ref=by.get(refpid); panel=by.get(panelpid)
if not ref: raise SystemExit(f'REFERRER_NOT_FOUND {refpid}')
if not panel: raise SystemExit(f'PANEL_NOT_FOUND {panelpid}')
refd=describe(ref); paneld=describe(panel); panel_components=components_of_go(panel)
# all MonoBehaviours whose serialized field names contain autoMirrorCullObjects or which point at FormationRT
special=[]
for o in objs:
    if typ(o)!='MonoBehaviour': continue
    t=tree(o); pps=ptrs(t); text=json.dumps(t,ensure_ascii=False)
    if '_autoMirrorCullObjects' in text or any(p['fileID']==0 and p['pathID']==3519289692077381591 for p in pps):
        special.append(describe(o))
report={'format':'WFGG_LASTWAR_FORMATION_RT_OWNER_TRACE_V1','referrer':refd,'panel':paneld,'panelComponents':panel_components,'panelParentChain':parent_chain(panel),'specialMonoBehaviours':special,'guardrails':{'labOnly':True,'mainUntouched':True,'actualGameAssetsOnly':True}}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_RT_OWNER_TRACE_V1_READY')
print('--- FormationRT REFERRER ---')
print(f"pathID={refd['pathID']} type={refd['type']} script={(refd.get('script') or {}).get('name','?')} host={(refd.get('gameObject') or {}).get('name','?')} ptrs={len(refd['pointers'])}")
for p in refd['pointers']:
    print(f"  {p['field']} -> fileID={p['fileID']} pathID={p['pathID']} resolved={p.get('resolved')} type={p.get('type','?')} name={p.get('name','?')} external={p.get('externalPath','')}")
print('--- UIHeroPVPFormationPanel COMPONENTS ---')
for c in panel_components:
    print(f"component pathID={c['pathID']} type={c['type']} script={(c.get('script') or {}).get('name','?')} name={c['name'] or '—'} ptrs={len(c['pointers'])}")
print('--- PANEL PARENT CHAIN ---')
for i,x in enumerate(report['panelParentChain']):
    comps=', '.join(f"{c['type']}:{c['script'] or '-'}" for c in x['components'])
    print(f"{i}: {x['name']} pathID={x['pathID']} components=[{comps}]")
print('--- SPECIAL MONOBEHAVIOURS ---')
for d in special:
    print(f"pathID={d['pathID']} script={(d.get('script') or {}).get('name','?')} host={(d.get('gameObject') or {}).get('name','?')} ptrs={len(d['pointers'])}")
    for p in d['pointers']:
        if 'autoMirrorCullObjects' in p['field'] or p['field'].endswith('.m_Script') or p['field'].endswith('.m_GameObject') or p['pathID']==3519289692077381591:
            print(f"  {p['field']} -> fileID={p['fileID']} pathID={p['pathID']} resolved={p.get('resolved')} type={p.get('type','?')} name={p.get('name','?')}")
print(f'JSON={out}')
PY
