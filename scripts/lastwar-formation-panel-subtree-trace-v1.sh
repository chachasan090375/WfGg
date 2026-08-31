#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BUNDLE="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles/bundle-6933.bundle"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-panel-subtree-trace-v1.json"
UNITY_VERSION="2019.4.41f1"
ROOT_GO=8695854979998244933
KEY_GOS=(-9077317091161456364 516890780748345296 2726074644948953871 3519289692077381591)
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$BUNDLE" ]] || fail "bundle 6933 absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")"
PYTHONUNBUFFERED=1 python - "$BUNDLE" "$OUT" "$UNITY_VERSION" "$ROOT_GO" "${KEY_GOS[@]}" <<'PY'
import json,sys
from pathlib import Path
import UnityPy
bundle=Path(sys.argv[1]); out=Path(sys.argv[2]); version=sys.argv[3]; root_go=int(sys.argv[4]); key_gos=[int(x) for x in sys.argv[5:]]
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
    except:return {}
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
by={pid(o):o for o in objs}

def resolved(p): return p['fileID']==0 and p['pathID'] in by

def script_name(o):
    if typ(o)!='MonoBehaviour': return ''
    for p in ptrs(tree(o)):
        if p['field'].endswith('.m_Script') and resolved(p): return name(by[p['pathID']])
    return ''

def go_of_component(o):
    for p in ptrs(tree(o)):
        if p['field'].endswith('.m_GameObject') and resolved(p): return p['pathID']
    return None

def components(go_pid):
    go=by.get(go_pid); z=[]
    if not go:return z
    for p in ptrs(tree(go)):
        if '.m_Component[' in p['field'] and p['field'].endswith('.component') and resolved(p):
            c=by[p['pathID']]; z.append({'pathID':pid(c),'type':typ(c),'name':name(c),'script':script_name(c)})
    return z
# map GO -> RectTransform and parent GO
parent={}; rect_of={}
for o in objs:
    if typ(o) not in ('RectTransform','Transform'): continue
    go=go_of_component(o)
    if go is None: continue
    rect_of[go]=pid(o)
    father=None
    for p in ptrs(tree(o)):
        if p['field'].endswith('.m_Father') and resolved(p):
            ft=by[p['pathID']]; fgo=go_of_component(ft); father=fgo; break
    parent[go]=father

def under_root(go):
    seen=set(); cur=go
    while cur is not None and cur not in seen:
        if cur==root_go:return True
        seen.add(cur); cur=parent.get(cur)
    return False
subtree=[]
for o in objs:
    if typ(o)!='GameObject':continue
    g=pid(o)
    if under_root(g): subtree.append({'pathID':g,'name':name(o),'parent':parent.get(g),'components':components(g)})
sub_ids={x['pathID'] for x in subtree}
# inbound refs from objects outside subtree/components to key GOs and subtree
key_names={k:name(by[k]) if k in by else '?' for k in key_gos}
inbound=[]
for o in objs:
    hits=[]
    for p in ptrs(tree(o)):
        if p['fileID']==0 and p['pathID'] in key_gos:
            hits.append({'field':p['field'],'targetPathID':p['pathID'],'targetName':key_names.get(p['pathID'],'?')})
    if hits:
        inbound.append({'pathID':pid(o),'type':typ(o),'name':name(o),'script':script_name(o),'host':name(by[go_of_component(o)]) if go_of_component(o) in by else '', 'hits':hits})
# MonoScript inventory relevant to formation/pvp/hero/render/camera/model
scripts=[]
for o in objs:
    if typ(o)=='MonoScript':
        n=name(o); low=n.lower()
        if any(k in low for k in ('formation','pvp','hero','render','camera','model','mirror','rawimage')):
            scripts.append({'pathID':pid(o),'name':n,'serializedFile':sf(o)})
# exact object type inventory
special_types={t:[] for t in ('Camera','RenderTexture','MeshRenderer','SkinnedMeshRenderer')}
for o in objs:
    if typ(o) in special_types:special_types[typ(o)].append({'pathID':pid(o),'name':name(o)})
report={'format':'WFGG_LASTWAR_FORMATION_PANEL_SUBTREE_TRACE_V1','root':{'pathID':root_go,'name':name(by[root_go]) if root_go in by else '?'},'subtree':subtree,'inboundToKeyObjects':inbound,'relevantMonoScripts':scripts,'specialTypes':special_types,'keyObjects':key_names,'guardrails':{'labOnly':True,'mainUntouched':True,'actualGameAssetsOnly':True}}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_PANEL_SUBTREE_TRACE_V1_READY')
print(f"root={report['root']['name']} subtreeGameObjects={len(subtree)}")
print('--- SPECIAL TYPES ---')
for t,z in special_types.items(): print(f'{t}: {len(z)} ' + ', '.join(f"{x['name'] or '—'}@{x['pathID']}" for x in z[:20]))
print('--- RELEVANT MONOSCRIPTS ---')
for s in scripts: print(f"{s['name']} pathID={s['pathID']}")
print('--- SUBTREE MONOBEHAVIOURS ---')
for g in sorted(subtree,key=lambda x:(x['name'].lower(),x['pathID'])):
    m=[c for c in g['components'] if c['type']=='MonoBehaviour']
    if m: print(f"GO {g['name']} pathID={g['pathID']} :: " + ' | '.join(f"{c['script'] or '?'}@{c['pathID']}" for c in m))
print('--- INBOUND TO KEY OBJECTS ---')
for r in inbound:
    print(f"{r['type']} script={r['script'] or '-'} host={r['host'] or '-'} name={r['name'] or '—'} pathID={r['pathID']}")
    for h in r['hits']: print(f"  {h['field']} -> {h['targetName']}@{h['targetPathID']}")
print(f'JSON={out}')
PY
