#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
SUMMARY="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v4-summary-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-selected-material-dependent-bundles-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_SELECTED_MATERIAL_DEPENDENT_BUNDLES_V2.txt"
CACHE="$HOME/.cache/wfgg-formation-selected-material-dependents-v2"
UNITY_VERSION="2019.4.41f1"
TARGET_BUNDLE=14169
TARGET_FILE="CAB-9a46429c8bac0e1cd467ec61b2a0f8a3"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$INDEX" ]] || fail "index graphique absent"
[[ -s "$SUMMARY" ]] || fail "summary V4 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$CACHE" "$(dirname "$REPORT")"

echo "MATERIAL_DEPENDENTS_V2_START"
PYTHONUNBUFFERED=1 python - "$INDEX" "$SUMMARY" "$LOCAL" "$OUT" "$REPORT" "$CACHE" "$UNITY_VERSION" "$TARGET_BUNDLE" "$TARGET_FILE" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json,re,sys,zipfile
import UnityPy

indexp,sump,localp,outp,reportp,cachep=map(Path,sys.argv[1:7])
unity_version=sys.argv[7];target_bundle=int(sys.argv[8]);target_file=sys.argv[9]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

MATERIALS={
 'Terrain_Ground':5462275938698525167,
 'O_terrain_grass02_3TextureNS1':-58427823418694077,
 'O_terrain_road_01':1806725993657708232,
 'O_terrain_road_02_nsj':-1460172297484211456,
 'O_terrain_shamo_back':142524935483900056,
}

def norm(s):
    return str(s or '').replace('\\','/').rsplit('/',1)[-1]

def ptr_hits(tree,path='$'):
    if isinstance(tree,dict):
        fk=next((k for k in ('m_FileID','fileID','fileId','m_FileId') if k in tree),None)
        pk=next((k for k in ('m_PathID','pathID','pathId','m_PathId') if k in tree),None)
        if fk is not None and pk is not None:
            try: yield path,int(tree[fk]),int(tree[pk])
            except Exception: pass
        for k,v in tree.items(): yield from ptr_hits(v,f'{path}.{k}')
    elif isinstance(tree,(list,tuple)):
        for i,v in enumerate(tree): yield from ptr_hits(v,f'{path}[{i}]')

def ext_names(af):
    out=[]
    for ex in list(getattr(af,'externals',None) or []):
        vals=[]
        for a in ('path','name','file_name','fileName'):
            try:
                v=getattr(ex,a,None)
                if v: vals.append(str(v))
            except Exception: pass
        out.append(vals)
    return out

def ref_names(af,file_id):
    if file_id==0:return [str(getattr(af,'name','') or '')]
    ex=ext_names(af);i=file_id-1
    return ex[i] if 0<=i<len(ex) else []

def obj_name(o):
    try:return str(o.peek_name() or '')
    except Exception:return ''

print('MATERIAL_DEPENDENTS_V2_STAGE load-index',flush=True)
idx=json.loads(indexp.read_text('utf-8'));summ=json.loads(sump.read_text('utf-8'))
recs=idx.get('bundles')
if not isinstance(recs,list) or not recs: raise SystemExit('INDEX_SCHEMA_ERROR bundles')
byid={int(r['bundleId']):r for r in recs if isinstance(r,dict) and r.get('bundleId') is not None}
trec=byid.get(target_bundle)
if not trec: raise SystemExit('TARGET_BUNDLE_NOT_IN_CURRENT_INDEX')

deps=sorted(set(int(x) for x in (trec.get('dependentBundleIds') or [])))
print('MATERIAL_DEPENDENTS_V2_INDEX',f'targetBundle={target_bundle}',f'dependents={len(deps)}',flush=True)

closure=set(int(x) for x in ((summ.get('dependencySelection') or {}).get('selectedBundleIds') or []))
local={}
if localp.is_dir():
    for p in localp.glob('bundle-*.bundle'):
        m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
        if m: local[int(m.group(1))]=p

# Current-index extraction only. No historical offsets.
def resolve_phys(v):
    if not v:return None
    p=Path(str(v)).expanduser();cands=[p,Path.home()/'storage/downloads'/p.name,Path.home()/'storage/shared/Download'/p.name,Path.cwd()/p]
    for q in cands:
        if q.is_file():return q
    return None

def materialize(bid):
    if bid in local:return local[bid],'cached-closure'
    rec=byid.get(bid) or {};pe=rec.get('preferredExtraction') or {};phys=resolve_phys(pe.get('physicalApk'))
    if not phys:return None,'current-source-unavailable'
    try:
        off=int(pe.get('offset') or 0);span=pe.get('spanBytes')
        if span is None and pe.get('end') is not None:span=int(pe['end'])-off
        span=int(span) if span is not None else None
        if not span or span<=0 or span>134217728:return None,'current-span-invalid'
        out=cachep/f'bundle-{bid}.bundle';entry=pe.get('fragmentEntry')
        if entry:
            with zipfile.ZipFile(phys,'r') as zf:
                with zf.open(str(entry),'r') as f:
                    try:f.seek(off)
                    except Exception:
                        if off:f.read(off)
                    data=f.read(span)
        else:
            with phys.open('rb') as f:f.seek(off);data=f.read(span)
        if len(data)!=span:return None,f'short-read-{len(data)}-of-{span}'
        out.write_bytes(data);UnityPy.load(str(out));return out,'current-index-preferredExtraction'
    except Exception as e:return None,f'extraction-error:{type(e).__name__}:{e}'

hits=[];resolution=[];ptrs=0;read_fail=[]
for pos,bid in enumerate(deps,1):
    p,how=materialize(bid);resolution.append({'bundleId':bid,'resolution':how,'inClosure':bid in closure})
    print('MATERIAL_DEPENDENTS_V2_BUNDLE',f'{pos}/{len(deps)}',f'bundle={bid}',f'resolution={how}',flush=True)
    if not p:continue
    try:env=UnityPy.load(str(p))
    except Exception as e:
        read_fail.append({'bundleId':bid,'stage':'load','error':f'{type(e).__name__}:{e}'});continue
    for o in list(getattr(env,'objects',[]) or []):
        af=getattr(o,'assets_file',None);sf=str(getattr(af,'name','') or '');typ=str(getattr(getattr(o,'type',None),'name','') or '');name=obj_name(o);pid=str(getattr(o,'path_id',''))
        try:tree=o.read_typetree()
        except Exception as e:
            if len(read_fail)<300:read_fail.append({'bundleId':bid,'stage':'typetree','type':typ,'name':name,'pathID':pid,'error':f'{type(e).__name__}:{e}'})
            continue
        for field,fid,pth in ptr_hits(tree):
            ptrs+=1
            if pth not in MATERIALS.values():continue
            names=ref_names(af,fid)
            if not any(norm(n)==norm(target_file) for n in names):continue
            mat=next((k for k,v in MATERIALS.items() if v==pth),None)
            rec={'material':mat,'materialPathID':str(pth),'sourceBundleId':bid,'sourceSerializedFile':sf,'sourceObjectType':typ,'sourceObjectName':name,'sourceObjectPathID':pid,'fieldPath':field,'fileID':fid,'inFormationClosure':bid in closure}
            hits.append(rec)
            print('MATERIAL_DEPENDENTS_V2_HIT',f'material={mat}',f'bundle={bid}',f'type={typ}',f'name={name}',f'field={field}',flush=True)

by_mat=defaultdict(list);by_bundle=defaultdict(list)
for h in hits:by_mat[h['material']].append(h);by_bundle[h['sourceBundleId']].append(h)
result={'format':'WFGG_LASTWAR_FORMATION_SELECTED_MATERIAL_DEPENDENT_BUNDLES_V2','targetBundleId':target_bundle,'targetSerializedFile':target_file,'targetBundleCurrentIndex':{'logicalName':trec.get('logicalName'),'aliasName':trec.get('aliasName'),'assetPaths':trec.get('assetPaths',[]),'dependentBundleIds':deps},'materials':[{'name':k,'pathIDExact':str(v),'hits':by_mat.get(k,[])} for k,v in MATERIALS.items()],'bundleAggregate':[{'bundleId':b,'hits':len(v),'materials':sorted(set(x['material'] for x in v)),'objects':v} for b,v in sorted(by_bundle.items())],'resolution':resolution,'counts':{'dependentBundles':len(deps),'resolvedBundles':sum(1 for x in resolution if x['resolution'] in ('cached-closure','current-index-preferredExtraction')),'ptrsScanned':ptrs,'hits':len(hits),'consumerBundles':len(by_bundle),'readFailures':len(read_fail)},'readFailures':read_fail,'guardrails':{'currentIndexOnly':True,'historicalOffsetsReused':False,'runtimeUseProof':False,'generatedVisuals':False,'labBranchOnly':True}}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — SELECTED MATERIAL DEPENDENT BUNDLES V2','',f"targetBundle={target_bundle} dependentBundles={len(deps)} resolvedBundles={result['counts']['resolvedBundles']} ptrsScanned={ptrs} hits={len(hits)} consumerBundles={len(by_bundle)} readFailures={len(read_fail)}",'',f"targetLogical={trec.get('logicalName','')}",f"targetAlias={trec.get('aliasName','')}",'targetAssets:']
for a in trec.get('assetPaths',[]):lines.append('  '+str(a))
lines+=['','MATERIALS']
for m in result['materials']:
    lines.append('='*100);lines.append(f"MATERIAL {m['name']} pathID={m['pathIDExact']} hits={len(m['hits'])}")
    for h in m['hits']:lines.append(f"  sourceBundle={h['sourceBundleId']} inClosure={h['inFormationClosure']} type={h['sourceObjectType']} name={h['sourceObjectName'] or '-'} pathID={h['sourceObjectPathID']} field={h['fieldPath']} fileID={h['fileID']}")
lines+=['','BUNDLE AGGREGATE']
for b in result['bundleAggregate']:lines.append(f"bundle={b['bundleId']} materials={len(b['materials'])}/5 hits={b['hits']} names={' | '.join(b['materials'])}")
lines+=['','RESOLUTION']
for x in resolution:lines.append(f"bundle={x['bundleId']} inClosure={x['inClosure']} resolution={x['resolution']}")
lines+=['','RULE: candidates come only from current graphics index dependentBundleIds of bundle 14169.','RULE: only exact PPtr references to CAB-9a46429c8bac0e1cd467ec61b2a0f8a3 + one of the five exact Material pathIDs count as hits.','RULE: no historical physical offset reused.','RULE: serialized reference is not runtime-use proof.','RULE: no visual generated.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('MATERIAL_DEPENDENTS_V2_OK',f'hits={len(hits)}',f'consumerBundles={len(by_bundle)}',flush=True)
print('MATERIAL_DEPENDENTS_V2_REPORT',reportp,flush=True)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record selected Formation material dependent bundle trace V2"
  git push origin "$BRANCH"
fi

echo "=== MATERIAL DEPENDENTS V2 TERMINE ==="
echo "Rapport: $REPORT"
echo "main/preview inchangés. Aucun visuel généré."
