#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BUNDLE="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles/bundle-26299.bundle"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-camera-26299-trace-v1.json"
UNITY_VERSION="2019.4.41f1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$BUNDLE" ]] || fail "bundle 26299 absent: $BUNDLE"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")"
PYTHONUNBUFFERED=1 python - "$BUNDLE" "$OUT" "$UNITY_VERSION" <<'PY'
import json,sys
from pathlib import Path
import UnityPy
bundle=Path(sys.argv[1]); out=Path(sys.argv[2]); version=sys.argv[3]
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
            for k,y in x.items(): rec(y,f'{p}.{k}')
        elif isinstance(x,(list,tuple)):
            for i,y in enumerate(x): rec(y,f'{p}[{i}]')
    rec(v,prefix); return z

def flat(v,prefix='$'):
    z=[]
    def rec(x,p):
        if isinstance(x,dict):
            for k,y in x.items(): rec(y,f'{p}.{k}')
        elif isinstance(x,(list,tuple)):
            for i,y in enumerate(x): rec(y,f'{p}[{i}]')
        elif isinstance(x,(str,int,float,bool)):
            z.append({'field':p,'value':x})
    rec(v,prefix); return z

by={pid(o):o for o in objs}
def resolve(p,src=None):
    r=dict(p)
    if p['fileID']==0 and p['pathID'] in by:
        o=by[p['pathID']]; r.update(resolved=True,type=typ(o),name=name(o),serializedFile=sf(o))
    else:
        r['resolved']=False
        if src is not None and p['fileID']>0:
            try:
                exts=list(getattr(getattr(src,'assets_file',None),'externals',[]) or [])
                if p['fileID']-1 < len(exts):
                    ex=exts[p['fileID']-1]; r['externalPath']=str(getattr(ex,'path','') or getattr(ex,'name','') or ex)
            except:pass
    return r

def comp_go(o):
    for p in ptrs(tree(o)):
        if p['field'].endswith('.m_GameObject') and p['fileID']==0 and p['pathID'] in by:
            return by[p['pathID']]
    return None

def go_components(go):
    out=[]
    for p in ptrs(tree(go)):
        if '.m_Component[' in p['field'] and p['field'].endswith('.component') and p['fileID']==0 and p['pathID'] in by:
            o=by[p['pathID']]
            d={'pathID':pid(o),'type':typ(o),'name':name(o)}
            if typ(o)=='MonoBehaviour':
                for q in ptrs(tree(o)):
                    if q['field'].endswith('.m_Script') and q['fileID']==0 and q['pathID'] in by:
                        d['script']=name(by[q['pathID']]); break
            out.append(d)
    return out

def parent_of(go):
    tr=None
    for c in go_components(go):
        if c['type'] in ('Transform','RectTransform'):
            tr=by[c['pathID']]; break
    if tr is None:return None
    for p in ptrs(tree(tr)):
        if p['field'].endswith('.m_Father') and p['fileID']==0 and p['pathID'] in by:
            father=by[p['pathID']]
            fgo=comp_go(father)
            return fgo
    return None

def chain(go,n=12):
    out=[]; cur=go; seen=set()
    while cur is not None and len(out)<n and pid(cur) not in seen:
        seen.add(pid(cur)); out.append({'pathID':pid(cur),'name':name(cur),'components':go_components(cur)})
        cur=parent_of(cur)
    return out

def inbound(targets):
    rows=[]
    for o in objs:
        hits=[]
        for p in ptrs(tree(o)):
            if p['fileID']==0 and p['pathID'] in targets: hits.append(p)
        if hits:
            rows.append({'pathID':pid(o),'type':typ(o),'name':name(o),'hits':hits})
    return rows

cams=[]
for o in objs:
    if typ(o)!='Camera':continue
    t=tree(o); pp=[resolve(p,o) for p in ptrs(t)]; host=comp_go(o)
    fields=[]
    for x in flat(t):
        low=x['field'].lower()
        if any(k in low for k in ('enabled','depth','culling','clearflags','orthographic','field of view','fieldofview','near clip','nearclip','far clip','farclip','targetdisplay','rect','backgroundcolor')):
            fields.append(x)
    target=[p for p in pp if 'targettexture' in p['field'].lower()]
    cams.append({'pathID':pid(o),'name':name(o),'serializedFile':sf(o),'host':({'pathID':pid(host),'name':name(host),'components':go_components(host)} if host else None),'targetTexture':target,'interestingFields':fields,'pointers':pp,'hierarchy':chain(host) if host else []})

target_ids=set()
for c in cams:
    target_ids.add(c['pathID'])
    if c['host']: target_ids.add(c['host']['pathID'])
refs=inbound(target_ids)

type_counts={}
for o in objs:type_counts[typ(o)]=type_counts.get(typ(o),0)+1
named=[{'pathID':pid(o),'type':typ(o),'name':name(o)} for o in objs if name(o)]
report={'format':'WFGG_LASTWAR_FORMATION_CAMERA_26299_TRACE_V1','bundleId':26299,'objectCount':len(objs),'typeCounts':type_counts,'cameras':cams,'inbound':refs,'namedObjects':named,'guardrails':{'labOnly':True,'mainUntouched':True,'actualGameAssetsOnly':True}}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_CAMERA_26299_TRACE_V1_READY')
print(f'objects={len(objs)} cameras={len(cams)} typeCounts={type_counts}')
print('--- CAMERAS ---')
for i,c in enumerate(cams,1):
    h=c.get('host') or {}
    print(f"CAMERA {i} pathID={c['pathID']} host={h.get('name','?')} hostPathID={h.get('pathID','?')}")
    print('  hostComponents=' + ', '.join(f"{x['type']}:{x.get('script','-')}@{x['pathID']}" for x in h.get('components',[])))
    if c['targetTexture']:
        for p in c['targetTexture']:
            print(f"  TARGET {p['field']} -> fileID={p['fileID']} pathID={p['pathID']} resolved={p.get('resolved')} type={p.get('type','?')} name={p.get('name','?')} external={p.get('externalPath','')}")
    else: print('  TARGET none-field')
    for x in c['interestingFields']:
        print(f"  FIELD {x['field']}={x['value']}")
    print('  HIERARCHY ' + ' > '.join((x['name'] or '?') for x in c['hierarchy']))
print('--- INBOUND TO CAMERA/HOST ---')
for r in refs:
    hs=', '.join(f"{p['field']}->{p['pathID']}" for p in r['hits'])
    print(f"{r['type']} {r['name'] or '—'} pathID={r['pathID']} :: {hs}")
print('--- NAMED OBJECTS (compact) ---')
for x in named[:200]: print(f"{x['type']} {x['name']} pathID={x['pathID']}")
print(f'JSON={out}')
PY
