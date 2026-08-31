#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
CLOSURE="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-external-owner-trace-v1.json"
UNITY_VERSION="2019.4.41f1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$INDEX" ]] || fail "index graphique absent"
[[ -d "$CLOSURE" ]] || fail "closure Formation absente"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")"
PYTHONUNBUFFERED=1 python - "$INDEX" "$CLOSURE" "$OUT" "$UNITY_VERSION" <<'PY'
import json,re,sys
from pathlib import Path
import UnityPy
indexp=Path(sys.argv[1]); closure=Path(sys.argv[2]); out=Path(sys.argv[3]); version=sys.argv[4]
UnityPy.config.FALLBACK_UNITY_VERSION=version
idx=json.loads(indexp.read_text('utf-8'))
byid={int(x['bundleId']):x for x in idx.get('bundles',[]) if isinstance(x,dict) and x.get('bundleId') is not None}
target=byid.get(6933,{})

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def name(o):
    try:return str(o.peek_name() or '')
    except:return ''
def tree(o):
    try:return o.read_typetree()
    except:return None

def scalars(v,prefix='$'):
    z=[]
    def rec(x,p):
        if isinstance(x,dict):
            for k,y in x.items(): rec(y,f'{p}.{k}')
        elif isinstance(x,(list,tuple)):
            for i,y in enumerate(x): rec(y,f'{p}[{i}]')
        elif isinstance(x,(str,int,float,bool)):
            z.append((p,x))
    rec(v,prefix); return z

# Serialized-file names belonging to bundle 6933.
target_file=closure/'bundle-6933.bundle'
if not target_file.is_file(): raise SystemExit('BUNDLE_6933_MISSING')
env6933=UnityPy.load(str(target_file))
target_serialized=sorted({str(getattr(getattr(o,'assets_file',None),'name','') or '') for o in getattr(env6933,'objects',[]) or [] if str(getattr(getattr(o,'assets_file',None),'name','') or '')})
needles=['formationrt','formationbg','formationcontent','uiheropvpformationpanel','slotareas','heroinfobars','rendertexture','camera','a_hero_audie_01','50006']
logical_needles=[str(target.get('logicalName','')).lower(),str(target.get('aliasName','')).lower()]
logical_needles += [str(x).lower() for x in target.get('assetPaths',[]) or []]
logical_needles=[x for x in logical_needles if x]

bundle_files=[]
for p in sorted(closure.glob('bundle-*.bundle')):
    m=re.search(r'bundle-(\d+)\.bundle$',p.name)
    if m: bundle_files.append((int(m.group(1)),p))

hits=[]; load_failures=[]
for n,(bid,p) in enumerate(bundle_files,1):
    try: env=UnityPy.load(str(p))
    except Exception as e:
        load_failures.append({'bundleId':bid,'error':f'{type(e).__name__}:{e}'})
        continue
    ext_hits=[]; obj_hits=[]; script_hits=[]
    seen_files=set()
    for o in getattr(env,'objects',[]) or []:
        af=getattr(o,'assets_file',None)
        afname=str(getattr(af,'name','') or '')
        if af is not None and afname not in seen_files:
            seen_files.add(afname)
            for i,ex in enumerate(list(getattr(af,'externals',[]) or []),1):
                ep=str(getattr(ex,'path','') or getattr(ex,'name','') or ex)
                low=ep.lower()
                if any(sf and sf.lower() in low for sf in target_serialized) or any(nd in low for nd in logical_needles):
                    ext_hits.append({'serializedFile':afname,'fileID':i,'externalPath':ep})
        on=name(o); ot=typ(o)
        lowname=f'{ot} {on}'.lower()
        if any(k in lowname for k in needles):
            script_hits.append({'type':ot,'name':on,'pathID':pid(o),'reason':'name/type'})
        if ot=='MonoBehaviour':
            t=tree(o)
            if t is not None:
                found=[]
                for fld,val in scalars(t):
                    sval=str(val).lower()
                    ks=[k for k in needles if k in fld.lower() or k in sval]
                    if ks: found.append({'field':fld,'value':val,'keywords':ks})
                if found:
                    obj_hits.append({'type':ot,'name':on,'pathID':pid(o),'matches':found[:80]})
    if ext_hits or obj_hits or script_hits:
        rec=byid.get(bid,{})
        hits.append({'bundleId':bid,'logicalName':rec.get('logicalName',''),'aliasName':rec.get('aliasName',''),'externalRefsTo6933':ext_hits,'monoBehaviourScalarHits':obj_hits,'nameTypeHits':script_hits})

report={
 'format':'WFGG_LASTWAR_FORMATION_EXTERNAL_OWNER_TRACE_V1',
 'targetBundleId':6933,
 'target':{
   'logicalName':target.get('logicalName',''),'aliasName':target.get('aliasName',''),'assetPaths':target.get('assetPaths',[]),
   'dependencyBundleIds':target.get('dependencyBundleIds',[]),'dependentBundleIds':target.get('dependentBundleIds',[]),
   'serializedFiles':target_serialized,
 },
 'scannedBundleCount':len(bundle_files),'hits':hits,'loadFailures':load_failures,
 'guardrails':{'labOnly':True,'mainUntouched':True,'actualGameAssetsOnly':True}
}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_EXTERNAL_OWNER_TRACE_V1_READY')
print('--- BUNDLE 6933 INDEX RELATIONS ---')
print('logical=',target.get('logicalName',''))
print('dependencies=',','.join(map(str,target.get('dependencyBundleIds',[]) or [])) or 'NONE')
print('dependents=',','.join(map(str,target.get('dependentBundleIds',[]) or [])) or 'NONE')
print('serializedFiles=',','.join(target_serialized) or 'NONE')
print('--- EXTERNAL / RUNTIME HITS ---')
if not hits: print('NONE')
for h in hits:
    print(f"bundle={h['bundleId']} logical={h['logicalName'] or '-'} extRefs={len(h['externalRefsTo6933'])} monoHits={len(h['monoBehaviourScalarHits'])} nameHits={len(h['nameTypeHits'])}")
    for x in h['externalRefsTo6933'][:20]: print(f"  EXT fileID={x['fileID']} path={x['externalPath']}")
    for x in h['nameTypeHits'][:30]: print(f"  NAME type={x['type']} name={x['name'] or '-'} pathID={x['pathID']}")
    for x in h['monoBehaviourScalarHits'][:20]:
        print(f"  MONO pathID={x['pathID']} name={x['name'] or '-'}")
        for m in x['matches'][:12]: print(f"    {m['field']} = {m['value']} keywords={','.join(m['keywords'])}")
print('loadFailures=',len(load_failures))
print(f'JSON={out}')
PY
