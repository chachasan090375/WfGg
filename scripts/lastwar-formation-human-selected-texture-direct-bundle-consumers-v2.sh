#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
SELECT="$META/formation-visual-human-review-v2-result.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$META/formation-human-selected-texture-direct-bundle-consumers-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_HUMAN_SELECTED_TEXTURE_DIRECT_BUNDLE_CONSUMERS_V2.txt"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$SELECT" "$SUMMARY"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent: $LOCAL"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$REPORT")"

echo "DIRECT_TEXTURE_CONSUMERS_V2_START"
echo "DIRECT_TEXTURE_CONSUMERS_V2_PREFLIGHT_OK"

PYTHONUNBUFFERED=1 python - "$SELECT" "$SUMMARY" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json,re,sys,traceback
import UnityPy

selectp,sump,localp,outp,reportp=map(Path,sys.argv[1:6])
unity_version=sys.argv[6]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

print('DIRECT_TEXTURE_CONSUMERS_V2_STAGE load-selection',flush=True)
sel=json.loads(selectp.read_text('utf-8'))
sumj=json.loads(sump.read_text('utf-8'))
retained=sel.get('retainedYes')
if not isinstance(retained,list) or len(retained)!=8:
    raise SystemExit(f'SELECTION_SCHEMA_ERROR retainedYes={len(retained) if isinstance(retained,list) else -1}')
expected=set(int(x) for x in ((sumj.get('dependencySelection') or {}).get('selectedBundleIds') or []))
if len(expected)!=195:
    raise SystemExit(f'SUMMARY_CLOSURE_GUARD expected195 actual={len(expected)}')

bundle_files={}
for p in localp.glob('bundle-*.bundle'):
    m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
    if m:bundle_files[int(m.group(1))]=p
missing=sorted(expected-set(bundle_files))
if missing:raise SystemExit(f'BUNDLE_CACHE_GUARD missing={len(missing)} sample={missing[:10]}')
print('DIRECT_TEXTURE_CONSUMERS_V2_SELECTION',f'items={len(retained)}',f'bundles={len(expected)}',flush=True)

# ---------- helpers ----------
def file_name_of_obj(obj):
    af=getattr(obj,'assets_file',None)
    return str(getattr(af,'name','') or '')

def norm_file_name(s):
    s=str(s or '').replace('\\','/')
    if not s:return ''
    return s.rsplit('/',1)[-1]

def external_names(assets_file):
    out=[]
    exts=getattr(assets_file,'externals',None)
    if not exts:return out
    for ex in exts:
        vals=[]
        for a in ('path','name','file_name','fileName'):
            try:
                v=getattr(ex,a,None)
                if v:vals.append(str(v))
            except Exception:pass
        # preserve index: one record per external
        out.append(vals)
    return out

def ptr_hits(tree,path='$'):
    if isinstance(tree,dict):
        # Unity typetree PPtr canonical shape.
        file_keys=('m_FileID','fileID','fileId','m_FileId')
        path_keys=('m_PathID','pathID','pathId','m_PathId')
        fk=next((k for k in file_keys if k in tree),None)
        pk=next((k for k in path_keys if k in tree),None)
        if fk is not None and pk is not None:
            try:yield path,int(tree[fk]),int(tree[pk])
            except Exception:pass
        for k,v in tree.items():
            yield from ptr_hits(v,f'{path}.{k}')
    elif isinstance(tree,(list,tuple)):
        for i,v in enumerate(tree):yield from ptr_hits(v,f'{path}[{i}]')

def resolve_ref_name(source_af,file_id):
    if file_id==0:
        return [str(getattr(source_af,'name','') or '')]
    if file_id<0:return []
    ex=external_names(source_af)
    idx=file_id-1
    if idx<0 or idx>=len(ex):return []
    return ex[idx]

def try_name(obj):
    try:
        n=obj.peek_name()
        if n:return str(n)
    except Exception:pass
    return ''

# ---------- resolve exact target serialized files from storage bundles ----------
print('DIRECT_TEXTURE_CONSUMERS_V2_STAGE resolve-target-identities',flush=True)
targets=[]
for i,item in enumerate(retained,1):
    bid=int(item['bundleId']);pid=int(str(item['pathIDExact']));name=str(item['name'])
    p=bundle_files.get(bid)
    if not p:raise SystemExit(f'TARGET_STORAGE_BUNDLE_MISSING bundle={bid}')
    env=UnityPy.load(str(p))
    hits=[]
    for obj in list(getattr(env,'objects',[]) or []):
        if int(getattr(obj,'path_id',0) or 0)!=pid:continue
        typ=str(getattr(getattr(obj,'type',None),'name','') or '')
        if typ!='Texture2D':continue
        oname=try_name(obj)
        hits.append((obj,oname,file_name_of_obj(obj)))
    if len(hits)!=1:
        raise SystemExit(f'TARGET_RESOLUTION_ERROR name={name} bundle={bid} pid={pid} hits={len(hits)}')
    obj,oname,sf=hits[0]
    if oname and oname!=name:
        raise SystemExit(f'TARGET_NAME_MISMATCH expected={name!r} actual={oname!r} bundle={bid} pid={pid}')
    aliases={sf,norm_file_name(sf)}
    aliases={x for x in aliases if x}
    rec={**item,'pathIDExact':str(pid),'serializedFile':sf,'serializedFileAliases':sorted(aliases)}
    targets.append(rec)
    print('DIRECT_TEXTURE_CONSUMERS_V2_TARGET',f'{i}/8',f'bundle={bid}',f'pid={pid}',f'file={sf}',f'name={name}',flush=True)

# target lookup by exact/normalized serialized-file identity + pathID.
target_by_identity={}
for t in targets:
    pid=int(t['pathIDExact'])
    for alias in t['serializedFileAliases']:
        target_by_identity[(alias,pid)]=t
        target_by_identity[(norm_file_name(alias),pid)]=t

# ---------- scan every serialized object in all 195 bundles ----------
print('DIRECT_TEXTURE_CONSUMERS_V2_STAGE scan-195-bundles',flush=True)
consumers=[]
bundle_stats=[]
read_failures=[]
ptr_total=0
for pos,bid in enumerate(sorted(expected),1):
    p=bundle_files[bid]
    print('DIRECT_TEXTURE_CONSUMERS_V2_BUNDLE',f'{pos}/195',f'bundle={bid}',flush=True)
    b_objects=0;b_trees=0;b_ptrs=0;b_hits=0
    try:
        env=UnityPy.load(str(p))
    except Exception as e:
        read_failures.append({'bundleId':bid,'stage':'load','error':f'{type(e).__name__}:{e}'})
        bundle_stats.append({'bundleId':bid,'objects':0,'typetrees':0,'ptrs':0,'hits':0,'loadError':str(e)})
        continue
    for obj in list(getattr(env,'objects',[]) or []):
        b_objects+=1
        source_af=getattr(obj,'assets_file',None)
        source_sf=str(getattr(source_af,'name','') or '')
        source_type=str(getattr(getattr(obj,'type',None),'name','') or '')
        source_pid=str(getattr(obj,'path_id',''))
        source_name=try_name(obj)
        try:
            tree=obj.read_typetree()
            b_trees+=1
        except Exception as e:
            if len(read_failures)<500:
                read_failures.append({'bundleId':bid,'stage':'typetree','serializedFile':source_sf,'pathID':source_pid,'type':source_type,'name':source_name,'error':f'{type(e).__name__}:{e}'})
            continue
        for field_path,file_id,path_id in ptr_hits(tree):
            b_ptrs+=1;ptr_total+=1
            if path_id==0:continue
            ref_names=resolve_ref_name(source_af,file_id)
            match=None;resolved_name=''
            for rn in ref_names:
                for alias in (rn,norm_file_name(rn)):
                    t=target_by_identity.get((alias,path_id))
                    if t is not None:
                        match=t;resolved_name=rn;break
                if match is not None:break
            if match is None:continue
            b_hits+=1
            consumers.append({
                'targetName':match['name'],'targetStorageBundle':int(match['bundleId']),'targetPathID':str(match['pathIDExact']),
                'targetSerializedFile':match['serializedFile'],'sourceBundleId':bid,'sourceSerializedFile':source_sf,
                'sourceObjectPathID':source_pid,'sourceObjectType':source_type,'sourceObjectName':source_name,
                'fieldPath':field_path,'fileID':file_id,'resolvedExternalName':resolved_name
            })
            print('DIRECT_TEXTURE_CONSUMERS_V2_HIT',f'target={match["name"]}',f'sourceBundle={bid}',f'type={source_type}',f'name={source_name}',f'field={field_path}',flush=True)
    bundle_stats.append({'bundleId':bid,'objects':b_objects,'typetrees':b_trees,'ptrs':b_ptrs,'hits':b_hits})

# ---------- aggregates ----------
by_texture=defaultdict(list)
by_bundle=defaultdict(lambda:{'textures':set(),'objects':set(),'types':set(),'hits':0})
for c in consumers:
    by_texture[c['targetName']].append(c)
    u=by_bundle[c['sourceBundleId']];u['textures'].add(c['targetName']);u['objects'].add((c['sourceObjectType'],c['sourceObjectName'],c['sourceObjectPathID']));u['types'].add(c['sourceObjectType']);u['hits']+=1

texture_results=[]
for t in targets:
    hits=by_texture.get(t['name'],[])
    texture_results.append({
        'target':t,'directReferenceCount':len(hits),'consumerBundleIds':sorted({x['sourceBundleId'] for x in hits}),
        'consumerObjects':hits
    })

bundle_aggregate=[]
for bid,u in by_bundle.items():
    bundle_aggregate.append({
        'bundleId':bid,'hitCount':u['hits'],'textures':sorted(u['textures']),'consumerTypes':sorted(u['types']),
        'consumerObjects':[{'type':a,'name':b,'pathID':c} for a,b,c in sorted(u['objects'])]
    })
bundle_aggregate.sort(key=lambda x:(-len(x['textures']),-x['hitCount'],x['bundleId']))

out={
    'format':'WFGG_LASTWAR_FORMATION_HUMAN_SELECTED_TEXTURE_DIRECT_BUNDLE_CONSUMERS_V2',
    'method':'direct scan of all serialized objects in the exact 195 current cached closure bundles; PPtr fileID+pathID resolved to exact selected Texture2D serialized-file identities',
    'targets':targets,'textureResults':texture_results,'bundleAggregate':bundle_aggregate,
    'counts':{'closureBundles':195,'targets':8,'directHits':len(consumers),'consumerBundles':len(bundle_aggregate),'ptrsScanned':ptr_total,'readFailures':len(read_failures)},
    'bundleStats':bundle_stats,'readFailures':read_failures,
    'guardrails':{'labBranchOnly':True,'mainUntouched':True,'historicalOffsetsReused':False,'runtimeUseProof':False,'generatedVisuals':False}
}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — HUMAN SELECTED TEXTURE DIRECT BUNDLE CONSUMERS V2','',
       f"closureBundles=195 selected=8 ptrsScanned={ptr_total} directHits={len(consumers)} consumerBundles={len(bundle_aggregate)} readFailures={len(read_failures)}",'',
       'TEXTURES']
for r in texture_results:
    t=r['target'];lines.append('='*96)
    lines.append(f"TEXTURE {t['name']} storageBundle={t['bundleId']} pathID={t['pathIDExact']} serializedFile={t['serializedFile']}")
    lines.append(f"directReferenceCount={r['directReferenceCount']} consumerBundles={','.join(map(str,r['consumerBundleIds'])) or '-'}")
    for c in r['consumerObjects']:
        lines.append(f"  sourceBundle={c['sourceBundleId']} sourceFile={c['sourceSerializedFile']} objectType={c['sourceObjectType']} objectName={c['sourceObjectName'] or '-'} objectPathID={c['sourceObjectPathID']} field={c['fieldPath']} fileID={c['fileID']}")
lines+=['','BUNDLE AGGREGATE']
for b in bundle_aggregate:
    lines.append(f"bundle={b['bundleId']} textures={len(b['textures'])}/8 hits={b['hitCount']} names={' | '.join(b['textures'])}")
    lines.append(f"  consumerTypes={' | '.join(b['consumerTypes']) or '-'}")
    for o in b['consumerObjects'][:40]:lines.append(f"  object type={o['type']} name={o['name'] or '-'} pathID={o['pathID']}")
lines+=['','DIAGNOSTICS',f'readFailures={len(read_failures)}']
for e in read_failures[:80]:lines.append('  '+json.dumps(e,ensure_ascii=False))
lines+=['','RULE: consumer bundle means a direct serialized PPtr to one of the 8 exact Texture2D targets.','RULE: direct serialized reference is stronger than mere bundle co-location, but still not runtime-use proof.','RULE: current cached 195-bundle closure only; no historical physical offsets reused.','RULE: no visual generated.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('DIRECT_TEXTURE_CONSUMERS_V2_OK',f'directHits={len(consumers)}',f'consumerBundles={len(bundle_aggregate)}',f'readFailures={len(read_failures)}',flush=True)
print('DIRECT_TEXTURE_CONSUMERS_V2_REPORT',reportp,flush=True)
print('DIRECT_TEXTURE_CONSUMERS_V2_JSON',outp,flush=True)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace selected Formation texture direct bundle consumers V2"
  git push origin "$BRANCH"
fi

echo "=== DIRECT TEXTURE CONSUMERS V2 TERMINE ==="
echo "Rapport: $REPORT"
echo "main/preview inchangés. Aucun visuel généré."
