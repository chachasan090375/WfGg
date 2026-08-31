#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import defaultdict
import json,re,sys
import UnityPy

ROOT=Path(sys.argv[1]).resolve()
V11=ROOT/'frontend/lab/audie-model-variants-v11-data/manifest.json'
OUT=ROOT/'frontend/lab/audie-board-usage-v12-data'
META=ROOT/'frontend/lab/master-assets-v2/meta/audie-board-usage-v12.json'
MAN=OUT/'manifest.json'
OUT.mkdir(parents=True,exist_ok=True)
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'

if not V11.is_file():
    raise SystemExit('ERROR: run V11 first')
M=json.loads(V11.read_text('utf-8'))
main=M.get('mainVariants') or []
if not main:
    raise SystemExit('ERROR: no main variants in V11')

print('AUDIE_BOARD_USAGE_V12_START',f'mainVariants={len(main)}',flush=True)

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def sfname(o):
    af=getattr(o,'assets_file',None)
    return str(getattr(af,'name','') or getattr(af,'path','') or '')
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''

def tree(o):
    try:return o.read_typetree()
    except Exception:return {}

def pptr(x):
    if not isinstance(x,dict): return None
    fid=x.get('m_FileID',x.get('fileID',x.get('file_id')))
    path=x.get('m_PathID',x.get('pathID',x.get('path_id')))
    try:return int(fid or 0),int(path or 0)
    except:return None

def ext_name(o,file_id):
    if not file_id: return sfname(o)
    af=getattr(o,'assets_file',None)
    exts=list(getattr(af,'externals',[]) or [])
    idx=file_id-1
    if idx<0 or idx>=len(exts): return ''
    e=exts[idx]
    for k in ('path','name'):
        v=getattr(e,k,None)
        if v:return str(v)
    try:
        return str(e)
    except:return ''

def basename_serialized(s):
    s=str(s or '').replace('\\','/')
    return s.rsplit('/',1)[-1].lower()

def walk_pptrs(x,path=''):
    if isinstance(x,dict):
        pp=pptr(x)
        if pp and (('m_FileID' in x and 'm_PathID' in x) or ('fileID' in x and 'pathID' in x)):
            yield path,pp
        for k,v in x.items():
            yield from walk_pptrs(v,(path+'.'+str(k)).strip('.'))
    elif isinstance(x,list):
        for i,v in enumerate(x): yield from walk_pptrs(v,f'{path}[{i}]')

# Variant identity: exact serialized file + pathID, with OBJ hash/name as human context.
variants=[]
for i,r in enumerate(main):
    variants.append({
      'id':i,
      'name':r.get('name'),
      'bundle':r.get('bundle'),
      'serializedFile':r.get('serializedFile'),
      'serializedBase':basename_serialized(r.get('serializedFile')),
      'pathID':str(r.get('pathID')),
      'vertexCount':r.get('vertexCount'),
      'faceCount':r.get('faceCount'),
      'complexity':r.get('complexity'),
      'src':r.get('src'),
      'sha1':r.get('sha1'),
      'evidence':[],
      'score':0,
    })

# Restrict first pass to proven family bundles from V11; this keeps V12 fast.
paths=[]
seen=set()
for b in M.get('bundles',[]) or []:
    p=Path(str(b.get('path') or ''))
    if p.is_file():
        k=str(p.resolve())
        if k not in seen: seen.add(k);paths.append(p)
paths.sort(key=lambda p:p.name.lower())
print('AUDIE_BOARD_USAGE_V12_SCANSET',f'bundles={len(paths)}',flush=True)

keywords={
 'formation':9,'uiheropvpformation':12,'pvpformation':12,'formationrt':12,'formationbg':10,
 'team':5,'array':5,'board':7,'plate':5,'deploy':5,'hero':2,'battle':3,'pvp':4,'prefab':3,'uihero':5,
}
def score_text(s):
    z=str(s or '').lower()
    score=0; hits=[]
    for k,w in keywords.items():
        if k in z: score+=w;hits.append(k)
    return score,hits

scanned=0;ptrs=0;errors=[]
for bi,p in enumerate(paths,1):
    print('AUDIE_BOARD_USAGE_V12_SCAN',f'{bi}/{len(paths)}',p.name,flush=True)
    try: env=UnityPy.load(str(p));objs=list(env.objects)
    except Exception as e:
        errors.append({'bundle':p.name,'stage':'load','error':f'{type(e).__name__}:{e}'});continue
    scanned+=1
    # GameObject names by local pathID for host context.
    go_names={}
    for o in objs:
        if typ(o)=='GameObject': go_names[pid(o)]=pname(o)
    for o in objs:
        t=typ(o)
        if t not in {'MeshFilter','SkinnedMeshRenderer','MeshRenderer','GameObject','MonoBehaviour'}: continue
        tr=tree(o)
        if not tr: continue
        host=pname(o)
        # local GO pointer often lives in m_GameObject
        go=''
        gp=pptr(tr.get('m_GameObject')) if isinstance(tr,dict) else None
        if gp and gp[0]==0: go=go_names.get(gp[1],'')
        for field,(fid,mpid) in walk_pptrs(tr):
            if not mpid: continue
            ptrs+=1
            target_serial=basename_serialized(ext_name(o,fid))
            for v in variants:
                # Exact pathID + exact serialized target when available.
                if str(mpid)!=v['pathID']: continue
                same_serial=(not target_serial or not v['serializedBase'] or target_serial==v['serializedBase'])
                if not same_serial: continue
                txt=' '.join([p.name,sfname(o),t,host,go,field,target_serial])
                sc,hits=score_text(txt)
                base=20 if t in {'MeshFilter','SkinnedMeshRenderer'} and field.endswith('m_Mesh') else 8
                rec={
                  'bundle':p.name,'bundlePath':str(p),'serializedFile':sfname(o),'objectType':t,'objectPathID':str(pid(o)),
                  'objectName':host,'gameObject':go,'field':field,'fileID':fid,'meshPathID':str(mpid),
                  'targetSerialized':target_serial,'keywordHits':hits,'score':base+sc,
                }
                # de-duplicate same evidence row
                key=(rec['bundle'],rec['serializedFile'],rec['objectType'],rec['objectPathID'],rec['field'],rec['meshPathID'])
                if not any((e['bundle'],e['serializedFile'],e['objectType'],e['objectPathID'],e['field'],e['meshPathID'])==key for e in v['evidence']):
                    v['evidence'].append(rec);v['score']+=rec['score']

for v in variants:
    v['evidence'].sort(key=lambda e:(-e['score'],e['bundle'],e['objectName']))
    # confidence is evidence-based only
    if any(e['objectType'] in {'MeshFilter','SkinnedMeshRenderer'} and e['field'].endswith('m_Mesh') for e in v['evidence']):
        v['confidence']='DIRECT_RENDERER_MESH_PTR'
    elif v['evidence']: v['confidence']='INDIRECT_PTR'
    else: v['confidence']='NO_USAGE_IN_FAMILY_PASS'

ranked=sorted(variants,key=lambda v:(-v['score'],-len(v['evidence']),v['vertexCount'] or 0))
if ranked and ranked[0]['score']>0:
    verdict='BOARD_USAGE_CANDIDATE_RANKED'
else:
    verdict='NO_USAGE_LINK_IN_AUDIE_FAMILY_BUNDLES'

res={
 'format':'WFGG_LASTWAR_AUDIE_BOARD_USAGE_V12',
 'verdict':verdict,
 'scope':'Audie proven family bundles only (fast pass)',
 'counts':{'variants':len(variants),'bundlesScanned':scanned,'pptrsInspected':ptrs,'evidence':sum(len(v['evidence']) for v in variants)},
 'variants':ranked,
 'errors':errors[:100],
 'rules':[
   'V12 does not decide by polygon count alone.',
   'A direct MeshFilter/SkinnedMeshRenderer m_Mesh PPtr is stronger than a name match.',
   'Formation/UIHeroPVPFormation/FormationRT/PVP/board keywords only rank already exact mesh pointers; they never create a link by themselves.',
   'This is a fast pass over the 37 proven Audie family bundles. If no exact usage is found, a later global reverse-PPtr pass can expand to the full corpus without changing the method.'
 ]
}
META.parent.mkdir(parents=True,exist_ok=True)
META.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
MAN.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_BOARD_USAGE_V12_READY',f'verdict={verdict}',f'evidence={res["counts"]["evidence"]}',flush=True)
for v in ranked:
    print('V12_VARIANT',v['name'],f'v={v["vertexCount"]}',f'f={v["faceCount"]}',f'score={v["score"]}',f'evidence={len(v["evidence"])}',f'confidence={v["confidence"]}',flush=True)
    for e in v['evidence'][:5]:
        print('  V12_EVIDENCE',e['objectType'],e['objectName'] or '-',e['gameObject'] or '-',e['field'],e['bundle'],f'score={e["score"]}',flush=True)
print('JSON='+str(META),flush=True)
